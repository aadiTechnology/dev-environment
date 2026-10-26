# Development bootstrap for the Control Plane and Aadi CRM.
# Default: validate only. Pass -Apply to create databases, migrate, seed, and verify.
# This script does not drop databases, print passwords, or commit changes.
param(
    [switch]$Apply,
    [switch]$CreateDatabases,
    [switch]$Migrate,
    [switch]$SeedControlPlane,
    [switch]$SeedCrm,
    [switch]$Verify,
    [switch]$GenerateLocalPassword
)

$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"
$DevRoot = $PSScriptRoot
$Workspace = Split-Path -Parent $DevRoot
$ControlPlane = Join-Path $Workspace "MultiTenant\Aadi-MultiTenant-Platform"
$Crm = Join-Path $Workspace "Product\aadi-crm"
$CpBackend = Join-Path $ControlPlane "backend"
$CrmBackend = Join-Path $Crm "backend"
$CpPython = Join-Path $CpBackend ".venv\Scripts\python.exe"
$CrmPython = Join-Path $CrmBackend ".venv\Scripts\python.exe"
$LocalEnv = Join-Path $DevRoot "config\dev.local.env"
$ExampleEnv = Join-Path $DevRoot "config\dev.env.example"
$State = Join-Path $DevRoot "config\seed-state.json"
$Catalog = Join-Path $DevRoot "seeds\crm_seed.json"
$Fixture = Join-Path $DevRoot "seeds\fixtures\preschool-dev-import.csv"
$Logs = Join-Path $DevRoot "logs"

if ($Apply) {
    $CreateDatabases = $true
    $Migrate = $true
    $SeedControlPlane = $true
    $SeedCrm = $true
    $Verify = $true
    $GenerateLocalPassword = $true
}

function Invoke-Native {
    param([string]$Label, [scriptblock]$Command)
    Write-Output "STEP $Label"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Output "FAILED $Label"
        exit 1
    }
}

function Import-LocalEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($raw in Get-Content -LiteralPath $Path) {
        $trimmed = $raw.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
        $parts = $trimmed.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

New-Item -ItemType Directory -Force -Path $Logs | Out-Null
if (-not (Test-Path -LiteralPath $LocalEnv)) {
    Copy-Item -LiteralPath $ExampleEnv -Destination $LocalEnv
    Write-Output "created local-config"
} else {
    Write-Output "reused local-config"
}

Invoke-Native "prerequisites" { & (Join-Path $DevRoot "scripts\Test-Prerequisites.ps1") }
Invoke-Native "seed-catalog-tests" {
    Push-Location $DevRoot
    try {
        & $CpPython -m unittest tests.test_seed_catalog
    } finally {
        Pop-Location
    }
}
Invoke-Native "database-role-tests" {
    Push-Location $DevRoot
    try {
        & $CpPython -m unittest tests.test_configure_database_roles
    } finally {
        Pop-Location
    }
}

$databaseArgs = @(
    (Join-Path $DevRoot "scripts\databases.py"),
    "--crm-database", "aadi_crm_dev"
)
if ($GenerateLocalPassword) { $databaseArgs += @("--generate-password", "--local-env", $LocalEnv) }
if ($CreateDatabases) { $databaseArgs += @("--create", "--configure-crm-env") }
Invoke-Native "databases" { & $CpPython @databaseArgs }

Import-LocalEnv $LocalEnv

if ($Migrate) {
    Invoke-Native "databases-required" {
        & $CpPython (Join-Path $DevRoot "scripts\databases.py") --crm-database aadi_crm_dev --require-targets
    }
    Invoke-Native "database-roles" {
        & $CpPython (Join-Path $DevRoot "scripts\configure_database_roles.py")
    }
    Invoke-Native "control-plane-migrations" {
        & $CpPython (Join-Path $DevRoot "scripts\apply_control_plane_migrations.py")
    }
    Invoke-Native "crm-migrations" { & $CrmPython (Join-Path $DevRoot "scripts\apply_crm_migrations.py") }
} else {
    Write-Output "skipped migrations"
}

if ($SeedControlPlane) {
    $prepare = & $CpPython (Join-Path $CpBackend "scripts\seed_development_tenant.py") prepare --state $State 2>&1
    $prepare | ForEach-Object { Write-Output $_ }
    if ($LASTEXITCODE -ne 0) { Write-Output "FAILED control-plane-prepare"; exit 1 }
    $health = $false
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3
        $health = $response.StatusCode -eq 200
    } catch {
        $health = $false
    }
    $restart = $prepare | Out-String
    if ($health -and $restart.Contains("RESTART_REQUIRED")) {
        Write-Output "FAILED The Control Plane API is already running and the platform-admin allowlist changed. Stop that process and run the bootstrap again. The bootstrap did not stop it."
        exit 1
    }
    Invoke-Native "control-plane-api" {
        & $CpPython (Join-Path $DevRoot "scripts\start_api.py") --app control-plane --port 8000 --health-path /health --log (Join-Path $Logs "control-plane-api.log")
    }
    Invoke-Native "control-plane-seed" {
        & $CpPython (Join-Path $CpBackend "scripts\seed_development_tenant.py") apply --state $State
    }
} else {
    Write-Output "skipped control-plane-seed"
}

if ($SeedCrm) {
    Invoke-Native "crm-api" {
        & $CrmPython (Join-Path $DevRoot "scripts\start_api.py") --app crm --port 8001 --health-path /openapi.json --log (Join-Path $Logs "crm-api.log")
    }
    Invoke-Native "crm-seed" {
        & $CrmPython (Join-Path $CrmBackend "scripts\seed_development_projects.py") --catalog $Catalog --state $State --fixture $Fixture
    }
} else {
    Write-Output "skipped crm-seed"
}

if ($Verify) {
    Invoke-Native "verification" { & $CpPython (Join-Path $DevRoot "scripts\verify_bootstrap.py") }
} else {
    Write-Output "skipped verification"
}

Write-Output "RESULT ok"
exit 0
