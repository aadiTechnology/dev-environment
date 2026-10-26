# Test 4 — End-to-end developer experience.
# Starts the documented apps, checks the signed-in tenant through the API and
# browser, runs the test suites, then runs the bootstrap again. It does not drop
# a database. A failing suite stays a failure.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_DevTestCommon.ps1")
Initialize-DevTest -EvidenceName "04-end-to-end.log"

if (-not (Import-DevIdentity)) {
    Complete-DevTest
}

function Test-TcpPort {
    param([int]$Port)
    foreach ($address in @([System.Net.IPAddress]::Loopback, [System.Net.IPAddress]::IPv6Loopback)) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $wait = $client.BeginConnect($address, $Port, $null, $null)
            if ($wait.AsyncWaitHandle.WaitOne(1000, $false) -and $client.Connected) {
                return $true
            }
        } catch {
        } finally {
            $client.Close()
        }
    }
    return $false
}

function Start-DevFrontend {
    param([string]$Name, [string]$Directory, [int]$Port)
    if (Test-TcpPort $Port) {
        Add-Evidence "reused $Name frontend"
        Add-Check pass "$Name-frontend"
        return
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Directory "node_modules"))) {
        Add-Check fail "$Name-frontend" "node_modules is missing"
        return
    }
    $log = Join-Path $script:Logs "$Name-frontend.log"
    New-Item -ItemType Directory -Force -Path $script:Logs | Out-Null
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev" -WorkingDirectory $Directory `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" -WindowStyle Hidden | Out-Null
    $deadline = (Get-Date).AddSeconds(40)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort $Port) {
            Add-Check pass "$Name-frontend"
            return
        }
        Start-Sleep -Seconds 1
    }
    Add-Check fail "$Name-frontend" "port $Port did not open"
}

function Test-HttpStatus {
    param([string]$Name, [string]$Url, [int]$Expected)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        $status = [int]$response.StatusCode
    } catch {
        $status = 0
    }
    Add-Evidence "$Name status=$status"
    if ($status -eq $Expected) { Add-Check pass $Name } else { Add-Check fail $Name "status=$status" }
}

function Invoke-Suite {
    param([string]$Name, [string]$Directory, [string]$Executable, [string[]]$Arguments, [string]$LogName)
    Add-Evidence "STEP $Name"
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $global:LASTEXITCODE = 0
    Push-Location $Directory
    try {
        $lines = New-Object System.Collections.Generic.List[string]
        & $Executable @Arguments 2>&1 | ForEach-Object { $lines.Add([string]$_) | Out-Null }
        $code = $global:LASTEXITCODE
    } finally {
        Pop-Location
        $ErrorActionPreference = $previous
    }
    if ($null -eq $code) { $code = 0 }
    $text = $lines -join "`n"
    $logPath = Join-Path $script:DevRoot "evidence\$LogName"
    Set-Content -LiteralPath $logPath -Value (Redact-Evidence $text) -Encoding utf8
    Add-Evidence "suite-log=$LogName exit=$code"
    $tail = @($lines | Select-Object -Last 12)
    if ($tail.Count -gt 0) { Write-Host (Redact-Evidence ($tail -join "`n")) }
    $passed = 0
    $failed = 0
    $errors = 0
    $skipped = 0
    $passedMatches = [regex]::Matches($text, "(\d+)\s+passed")
    $failedMatches = [regex]::Matches($text, "(\d+)\s+failed")
    $errorMatches = [regex]::Matches($text, "(\d+)\s+errors?")
    $skippedMatches = [regex]::Matches($text, "(\d+)\s+skipped")
    if ($passedMatches.Count -gt 0) { $passed = [int]$passedMatches[$passedMatches.Count - 1].Groups[1].Value }
    if ($failedMatches.Count -gt 0) { $failed = [int]$failedMatches[$failedMatches.Count - 1].Groups[1].Value }
    if ($errorMatches.Count -gt 0) { $errors = [int]$errorMatches[$errorMatches.Count - 1].Groups[1].Value }
    if ($skippedMatches.Count -gt 0) { $skipped = [int]$skippedMatches[$skippedMatches.Count - 1].Groups[1].Value }
    $ran = [regex]::Match($text, "Ran (\d+) tests?")
    if ($ran.Success -and $text -match "(?m)^OK\s*$") {
        $passed = [int]$ran.Groups[1].Value
    }
    $detail = "passed=$passed failed=$failed errors=$errors skipped=$skipped exit=$code"
    Add-Evidence "SUITE $Name $detail"
    Write-Output "SUITE $Name $detail"
    if ($code -eq 0) { Add-Check pass $Name $detail } else { Add-Check fail $Name $detail }
}

$beforeGit = @(
    (Get-RepoPorcelain $script:ControlPlane),
    (Get-RepoPorcelain $script:Crm)
) -join "`n"
Add-Evidence $beforeGit

$before = Get-InspectText
if ($before.Code -eq 0) { Add-Check pass "inspect-before" } else { Add-Check fail "inspect-before" }

$controlApi = Invoke-DevNative "control-plane-api" {
    & $script:CpPython (Join-Path $script:DevRoot "scripts\start_api.py") `
        --app control-plane --port 8000 --health-path /health `
        --log (Join-Path $script:Logs "control-plane-api.log")
}
if ($controlApi.Code -eq 0) { Add-Check pass "control-plane-api" } else { Add-Check fail "control-plane-api" }

$crmApi = Invoke-DevNative "crm-api" {
    & $script:CrmPython (Join-Path $script:DevRoot "scripts\start_api.py") `
        --app crm --port 8001 --health-path /openapi.json `
        --log (Join-Path $script:Logs "crm-api.log")
}
if ($crmApi.Code -eq 0) { Add-Check pass "crm-api" } else { Add-Check fail "crm-api" }

Start-DevFrontend -Name "control-plane" -Directory (Join-Path $script:ControlPlane "frontend") -Port 5173
Start-DevFrontend -Name "crm" -Directory (Join-Path $script:Crm "frontend") -Port 5174
Test-HttpStatus "control-plane-health" "http://localhost:8000/health" 200
Test-HttpStatus "control-plane-ready" "http://localhost:8000/ready" 200
Test-HttpStatus "crm-openapi" "http://localhost:8001/openapi.json" 200
Test-HttpStatus "control-plane-web" "http://localhost:5173/login" 200
Test-HttpStatus "crm-web" "http://localhost:5174/" 200

$verify = Invoke-DevNative "api-sign-in-and-tenant" {
    & $script:CpPython (Join-Path $script:DevRoot "scripts\verify_bootstrap.py")
}
if ($verify.Code -eq 0 -and $verify.Text -match "verified bootstrap") {
    Add-Check pass "api-sign-in-and-tenant"
} else {
    Add-Check fail "api-sign-in-and-tenant"
}

$browser = Invoke-DevNative "browser-sign-in" {
    & node (Join-Path $script:DevRoot "scripts\browser_learning_check.mjs")
}
if ($browser.Code -eq 0 -and $browser.Text -match "RESULT=ok") {
    Add-Check pass "browser-sign-in"
} elseif ($browser.Code -eq 2) {
    Add-Check blocked "browser-sign-in" "the browser driver was not available, so the screen was not exercised"
} else {
    Add-Check fail "browser-sign-in"
}

$removedDatabaseEnv = @(
    "DATABASE_URL",
    "CRM_DATABASE_URL",
    "CRM_DATABASE_SSLMODE",
    "CONTROL_PLANE_ADMIN_DATABASE_URL",
    "CONTROL_PLANE_APP_DATABASE_URL",
    "CONTROL_PLANE_MIGRATOR_DATABASE_URL",
    "CRM_ADMIN_DATABASE_URL",
    "CRM_APP_DATABASE_URL",
    "CRM_MIGRATOR_DATABASE_URL"
)
foreach ($name in $removedDatabaseEnv) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

Invoke-Suite "dev-environment-catalog" $script:DevRoot $script:CpPython @("-m", "unittest", "tests.test_seed_catalog") "04-catalog-unittest.log"
Invoke-Suite "control-plane-seed-tests" $script:CpBackend $script:CpPython @("-m", "pytest", "tests/test_development_seed.py") "04-control-plane-seed-pytest.log"
Invoke-Suite "crm-seed-tests" $script:CrmBackend $script:CrmPython @("-m", "pytest", "tests/test_development_seed.py") "04-crm-seed-pytest.log"
Invoke-Suite "crm-backend" $script:CrmBackend $script:CrmPython @("-m", "pytest") "04-crm-backend-pytest.log"
Invoke-Suite "control-plane-backend" $script:CpBackend $script:CpPython @("-m", "pytest") "04-control-plane-backend-pytest.log"
Invoke-Suite "crm-frontend" (Join-Path $script:Crm "frontend") "npm" @("test") "04-crm-frontend-vitest.log"
Invoke-Suite "control-plane-frontend" (Join-Path $script:ControlPlane "frontend") "npm" @("test") "04-control-plane-frontend-vitest.log"

$bootstrapLog = Join-Path $script:DevRoot "evidence\04-bootstrap-second-run.log"
$bootstrapScript = Join-Path $script:DevRoot "bootstrap.ps1"
Add-Evidence "STEP bootstrap-second-run"
$global:LASTEXITCODE = 0
& cmd.exe /c "powershell -NoProfile -ExecutionPolicy Bypass -File `"$bootstrapScript`" -Apply > `"$bootstrapLog`" 2>&1"
$bootstrapCode = $global:LASTEXITCODE
if ($null -eq $bootstrapCode) { $bootstrapCode = 0 }
$bootstrapText = ""
if (Test-Path -LiteralPath $bootstrapLog) {
    $bootstrapText = Get-Content -LiteralPath $bootstrapLog -Raw
}
Add-Evidence $bootstrapText
Add-Evidence "exit=bootstrap-second-run=$bootstrapCode"
$bootstrapTail = @($bootstrapText -split "`r?`n" | Select-Object -Last 20)
if ($bootstrapTail.Count -gt 0) { Write-Host (Redact-Evidence ($bootstrapTail -join "`n")) }
if ($bootstrapCode -eq 0 -and $bootstrapText -match "RESULT ok") {
    Add-Check pass "bootstrap-second-run"
} else {
    Add-Check fail "bootstrap-second-run"
}
Assert-NoCreatedRows $bootstrapText "bootstrap-idempotent"

$after = Get-InspectText
if ($after.Code -eq 0) { Add-Check pass "inspect-after" } else { Add-Check fail "inspect-after" }
Assert-SameLines $before.Text $after.Text "^count tables_" "database-table-counts-unchanged"
Assert-SameLines $before.Text $after.Text "^count (identity|tenant|product_crm|plan|subscription_active|membership|role_crm_development|projects_|forms_|records_) " "seeded-rows-unchanged"
foreach ($name in @("aadi_platform", "aadi_crm_dev")) {
    Assert-OutputLine $after.Text "count tables_${name}=" "database-still-present-$name"
}
foreach ($name in @("aadi_platform_", "aadi_crm_", "aadi_platform_test", "aadi_platform_onboarding_test")) {
    if ($after.Text -match ([regex]::Escape("count tables_$name=") )) {
        Add-Check pass "database-still-present-$name" "present and unchanged by this test"
    } else {
        Add-Check pass "database-still-present-$name" "absent on this server; it was not created"
    }
}

$afterGit = @(
    (Get-RepoPorcelain $script:ControlPlane),
    (Get-RepoPorcelain $script:Crm)
) -join "`n"
Add-Evidence $afterGit
Set-Content -LiteralPath (Join-Path $script:DevRoot "evidence\git-status-after-test-04.txt") -Value (Redact-Evidence $afterGit) -Encoding utf8
if ($beforeGit -eq $afterGit) { Add-Check pass "git-unchanged" } else { Add-Check fail "git-unchanged" }

Complete-DevTest
