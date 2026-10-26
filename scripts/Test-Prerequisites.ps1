# Validate local tools and repository paths. This script does not change databases.
$ErrorActionPreference = "Stop"
$DevRoot = Split-Path -Parent $PSScriptRoot
$Workspace = Split-Path -Parent $DevRoot
$ControlPlane = Join-Path $Workspace "MultiTenant\Aadi-MultiTenant-Platform"
$Crm = Join-Path $Workspace "Product\aadi-crm"

function Test-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Output "FAILED $Name is not on PATH."
        exit 1
    }
    $version = & $Name --version 2>&1 | Select-Object -First 1
    Write-Output "verified $Name $version"
}

if (-not (Test-Path -LiteralPath (Join-Path $ControlPlane ".git"))) {
    Write-Output "FAILED Control Plane repository was not found."
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $Crm ".git"))) {
    Write-Output "FAILED CRM repository was not found."
    exit 1
}
Write-Output "verified control-plane-path"
Write-Output "verified crm-path"

Test-Command python
Test-Command node
Test-Command npm

$cpPython = Join-Path $ControlPlane "backend\.venv\Scripts\python.exe"
$crmPython = Join-Path $Crm "backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $cpPython)) {
    Write-Output "FAILED Control Plane backend virtual environment is missing. From backend, run: python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`""
    exit 1
}
if (-not (Test-Path -LiteralPath $crmPython)) {
    Write-Output "FAILED CRM backend virtual environment is missing. From backend, run: python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`""
    exit 1
}
Write-Output "verified control-plane-venv"
Write-Output "verified crm-venv"

$cpNode = Join-Path $ControlPlane "frontend\node_modules"
$crmNode = Join-Path $Crm "frontend\node_modules"
if (-not (Test-Path -LiteralPath $cpNode)) {
    Write-Output "skipped control-plane-frontend-modules (run npm install in frontend)"
} else {
    Write-Output "verified control-plane-frontend-modules"
}
if (-not (Test-Path -LiteralPath $crmNode)) {
    Write-Output "skipped crm-frontend-modules (run npm install in frontend)"
} else {
    Write-Output "verified crm-frontend-modules"
}

Write-Output "RESULT ok"
exit 0
