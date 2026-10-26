# Shared helpers for the four development learning tests.
# Dot-source this file. It does not connect to a database and it does not print secrets.

Set-StrictMode -Version Latest
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Initialize-DevTest {
    param([Parameter(Mandatory = $true)][string]$EvidenceName)
    $script:Checks = New-Object System.Collections.Generic.List[string]
    $script:Evidence = New-Object System.Collections.Generic.List[string]
    $script:DevRoot = Split-Path -Parent $PSScriptRoot
    $script:Workspace = Split-Path -Parent $script:DevRoot
    $script:ControlPlane = Join-Path $script:Workspace "MultiTenant\Aadi-MultiTenant-Platform"
    $script:Crm = Join-Path $script:Workspace "Product\aadi-crm"
    $script:CpBackend = Join-Path $script:ControlPlane "backend"
    $script:CrmBackend = Join-Path $script:Crm "backend"
    $script:CpPython = Join-Path $script:CpBackend ".venv\Scripts\python.exe"
    $script:CrmPython = Join-Path $script:CrmBackend ".venv\Scripts\python.exe"
    $script:LocalEnv = Join-Path $script:DevRoot "config\dev.local.env"
    $script:State = Join-Path $script:DevRoot "config\seed-state.json"
    $script:Catalog = Join-Path $script:DevRoot "seeds\crm_seed.json"
    $script:Fixture = Join-Path $script:DevRoot "seeds\fixtures\preschool-dev-import.csv"
    $script:Logs = Join-Path $script:DevRoot "logs"
    $script:EvidencePath = Join-Path $script:DevRoot "evidence\$EvidenceName"
    $script:ApprovalPath = Join-Path $script:DevRoot "evidence\database-recreation-approval.txt"
    New-Item -ItemType Directory -Force -Path (Join-Path $script:DevRoot "evidence") | Out-Null
    New-Item -ItemType Directory -Force -Path $script:Logs | Out-Null
    Add-Evidence "evidence=$EvidenceName"
}

function Redact-Evidence {
    param([AllowEmptyString()][string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return "" }
    $clean = $Text
    $secret = [Environment]::GetEnvironmentVariable("IDENTITY_PASSWORD", "Process")
    if ($secret -and $secret.Length -ge 4) {
        $clean = $clean.Replace($secret, "<redacted>")
    }
    $clean = [regex]::Replace($clean, '(?i)\b[a-z][a-z0-9+.-]*://\S+', '<redacted-url>')
    $clean = [regex]::Replace($clean, '(?i)(password|secret|token|api[_-]?key)(\s*[:=]\s*|\s+)(\S+)', '$1$2<redacted>')
    $clean = [regex]::Replace($clean, '(?i)authorization:\s*\S+', 'authorization: <redacted>')
    return $clean
}

function Add-Evidence {
    param([AllowEmptyString()][string]$Text)
    $script:Evidence.Add((Redact-Evidence $Text)) | Out-Null
}

function Add-Check {
    param(
        [ValidateSet("pass", "fail", "blocked")][string]$Status,
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Detail = ""
    )
    $script:Checks.Add("$Status $Name") | Out-Null
    $line = "CHECK $Status $Name"
    if ($Detail) { $line = "$line $Detail" }
    Add-Evidence $line
    Write-Output (Redact-Evidence $line)
}

function Import-DevIdentity {
    if (-not (Test-Path -LiteralPath $script:LocalEnv)) {
        Add-Check fail "local-config" "gitignored config/dev.local.env is missing"
        return $false
    }
    $loaded = 0
    $passwordPresent = $false
    foreach ($raw in Get-Content -LiteralPath $script:LocalEnv) {
        $trimmed = $raw.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
        $parts = $trimmed.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($name -eq "IDENTITY_PASSWORD") {
            if ($value) {
                Set-Item -Path "Env:IDENTITY_PASSWORD" -Value $value
                $passwordPresent = $true
            }
            continue
        }
        if ($name -match "PASSWORD|SECRET|TOKEN|DATABASE_URL") { continue }
        if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
            Set-Item -Path "Env:$name" -Value $value
            $loaded += 1
        }
    }
    if ($passwordPresent) {
        Add-Check pass "identity-password" "present in this process only"
    } else {
        Add-Check fail "identity-password" "missing from gitignored local config"
    }
    Add-Evidence "loaded-public-keys=$loaded"
    return $passwordPresent
}

function Invoke-DevNative {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Add-Evidence "STEP $Label"
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $global:LASTEXITCODE = 0
    $lines = New-Object System.Collections.Generic.List[string]
    try {
        & $Action 2>&1 | ForEach-Object { $lines.Add([string]$_) | Out-Null }
    } finally {
        $ErrorActionPreference = $previous
    }
    $code = $global:LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    $text = $lines -join "`n"
    Add-Evidence $text
    Add-Evidence "exit=$Label=$code"
    $tail = @($lines | Select-Object -Last 15)
    if ($tail.Count -gt 0) {
        Write-Host (Redact-Evidence ($tail -join "`n"))
    }
    return [pscustomobject]@{ Code = [int]$code; Text = $text }
}

function Get-MatchingLines {
    param([AllowEmptyString()][string]$Text, [Parameter(Mandatory = $true)][string]$Pattern)
    if ([string]::IsNullOrEmpty($Text)) { return @() }
    return @($Text -split "`r?`n" | Where-Object { $_ -match $Pattern })
}

function Assert-OutputLine {
    param(
        [AllowEmptyString()][string]$Text,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ($Text -match $Pattern) {
        Add-Check pass $Name
    } else {
        Add-Check fail $Name "missing expected result"
    }
}

function Assert-NoCreatedRows {
    param([AllowEmptyString()][string]$Text, [Parameter(Mandatory = $true)][string]$Name)
    $created = @(Get-MatchingLines $Text "^created ")
    if ($created.Count -eq 0) {
        Add-Check pass $Name
    } else {
        Add-Check fail $Name ("second run created rows: " + ($created -join "; "))
    }
}

function Assert-SameLines {
    param(
        [AllowEmptyString()][string]$Before,
        [AllowEmptyString()][string]$After,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $left = @(Get-MatchingLines $Before $Pattern)
    $right = @(Get-MatchingLines $After $Pattern)
    $diff = Compare-Object -ReferenceObject $left -DifferenceObject $right
    if ($diff) {
        $detail = (($diff | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" }) -join "; ")
        Add-Check fail $Name $detail
    } else {
        Add-Check pass $Name
    }
}

function Get-RepoPorcelain {
    param([Parameter(Mandatory = $true)][string]$Repo)
    Push-Location $Repo
    try {
        $branch = (& git status -sb | Select-Object -First 1)
        $porcelain = @(& git status --porcelain=v1)
        if (-not $branch) { $branch = "(no-status)" }
        if ($porcelain.Count -eq 0) { $body = "(clean)" } else { $body = ($porcelain -join "`n") }
        return "REPO $Repo`n$branch`n$body"
    } finally {
        Pop-Location
    }
}

function Get-InspectText {
    Add-Evidence "STEP inspect"
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $global:LASTEXITCODE = 0
    $lines = New-Object System.Collections.Generic.List[string]
    try {
        & $script:CpPython (Join-Path $script:DevRoot "scripts\inspect_development_state.py") 2>&1 |
            ForEach-Object { $lines.Add([string]$_) | Out-Null }
    } finally {
        $ErrorActionPreference = $previous
    }
    $code = $global:LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    $text = $lines -join "`n"
    Add-Evidence $text
    Add-Evidence "inspect-exit=$code"
    $interesting = @(Get-MatchingLines $text "^(control_plane_|crm_|runtime_|migration_|roles_|table_owners|database |organization_|workspace_|entitlement_|identity_|tenant_|product_|plan_|subscription_|membership_|role |role_|permission |field_order|dropdowns|record |follow_up|import_|count |seed_|development_|RESULT|FAILED|recreation_|wildcard_)")
    if ($interesting.Count -gt 0) {
        Write-Host (Redact-Evidence ($interesting -join "`n"))
    }
    return [pscustomobject]@{ Code = [int]$code; Text = $text }
}

function Save-DevEvidence {
    $directory = Split-Path -Parent $script:EvidencePath
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $content = $script:Evidence -join "`r`n"
    Set-Content -LiteralPath $script:EvidencePath -Value (Redact-Evidence $content) -Encoding utf8
}

function Complete-DevTest {
    $pass = @($script:Checks | Where-Object { $_.StartsWith("pass ") }).Count
    $fail = @($script:Checks | Where-Object { $_.StartsWith("fail ") }).Count
    $blocked = @($script:Checks | Where-Object { $_.StartsWith("blocked ") }).Count
    $summary = "SUMMARY pass=$pass fail=$fail blocked=$blocked"
    Add-Evidence $summary
    Write-Output $summary
    Save-DevEvidence
    Remove-Item Env:IDENTITY_PASSWORD -ErrorAction SilentlyContinue
    if ($fail -gt 0) { exit 1 }
    exit 0
}
