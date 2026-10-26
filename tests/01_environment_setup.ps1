# Test 1 — Clean development environment and database setup.
# Default path: inspect, create a missing target only, migrate, and verify roles.
# It does not drop a database unless -RecreateApprovedDatabases is combined with
# the exact names and the approval file. Preserved databases are never accepted.
param(
    [switch]$RecreateApprovedDatabases,
    [string[]]$ApprovedDatabaseNames
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_DevTestCommon.ps1")
Initialize-DevTest -EvidenceName "01-environment-setup.log"

$preserved = @("aadi_platform_", "aadi_crm_", "aadi_platform_test", "aadi_platform_onboarding_test")
$expectedNames = @("aadi_platform", "aadi_crm_dev")

if ($RecreateApprovedDatabases) {
    $given = @($ApprovedDatabaseNames | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
    $difference = Compare-Object -ReferenceObject $expectedNames -DifferenceObject $given
    $rejected = @($given | Where-Object { $preserved -contains $_ -or $_ -match '[*?%]' })
    if ($given.Count -ne 2 -or $difference -or $rejected.Count -gt 0) {
        Add-Check fail "database-recreation" "exact names aadi_platform and aadi_crm_dev are required"
        Add-Evidence "No database was dropped."
        Save-DevEvidence
        exit 2
    }
    if (-not (Test-Path -LiteralPath $script:ApprovalPath)) {
        Add-Check blocked "database-recreation" "approval file is missing; no database was dropped"
        Save-DevEvidence
        exit 2
    }
    $recreate = Invoke-DevNative "recreate-approved-databases" {
        & $script:CpPython (Join-Path $script:DevRoot "scripts\recreate_approved_databases.py") `
            --approval-file $script:ApprovalPath `
            --name aadi_platform `
            --name aadi_crm_dev
    }
    if ($recreate.Code -ne 0) {
        Add-Check fail "database-recreation" "exit $($recreate.Code); no further changes were made by this test"
        Save-DevEvidence
        exit $recreate.Code
    }
    Add-Check pass "database-recreation"
} else {
    Add-Check blocked "database-recreation" "not approved; aadi_platform and aadi_crm_dev were not dropped"
}

$before = @(
    (Get-RepoPorcelain $script:ControlPlane),
    (Get-RepoPorcelain $script:Crm)
) -join "`n"
Add-Evidence $before
Set-Content -LiteralPath (Join-Path $script:DevRoot "evidence\git-status-before.txt") -Value (Redact-Evidence $before) -Encoding utf8

$prereq = Invoke-DevNative "prerequisites" { & (Join-Path $script:DevRoot "scripts\Test-Prerequisites.ps1") }
if ($prereq.Code -eq 0) { Add-Check pass "prerequisites" } else { Add-Check fail "prerequisites" }

$inventory = Invoke-DevNative "database-inventory" {
    & $script:CpPython (Join-Path $script:DevRoot "scripts\databases.py") --crm-database aadi_crm_dev
}
if ($inventory.Code -eq 0 -and $inventory.Text -match "control_plane_database=aadi_platform" -and $inventory.Text -match "crm_env_database=aadi_crm_dev") {
    Add-Check pass "database-targets"
} else {
    Add-Check fail "database-targets"
}
foreach ($name in $preserved) {
    if ($inventory.Text -match ([regex]::Escape("preserved_database=$name ") + "tables=")) {
        Add-Check pass "preserved-$name" "present and not a recreation target"
    } else {
        Add-Check pass "preserved-$name" "absent on this server; it was not created or deleted"
    }
}

$create = Invoke-DevNative "create-if-missing" {
    & $script:CpPython (Join-Path $script:DevRoot "scripts\databases.py") --crm-database aadi_crm_dev --create
}
if ($create.Code -eq 0 -and $create.Text -notmatch "FAILED") {
    Add-Check pass "create-if-missing"
} else {
    Add-Check fail "create-if-missing"
}

$roleTests = Invoke-DevNative "database-role-tests" {
    Push-Location $script:DevRoot
    try {
        & $script:CpPython -m unittest tests.test_configure_database_roles
    } finally {
        Pop-Location
    }
}
if ($roleTests.Code -eq 0) { Add-Check pass "database-role-tests" } else { Add-Check fail "database-role-tests" }

$roles = Invoke-DevNative "database-roles" {
    & $script:CpPython (Join-Path $script:DevRoot "scripts\configure_database_roles.py")
}
if ($roles.Text -match "preserved_databases_opened=none") {
    Add-Check pass "legacy-databases-not-opened"
} else {
    Add-Check fail "legacy-databases-not-opened"
}
if ($roles.Code -eq 0 -and $roles.Text -match "RESULT=ok") {
    Add-Check pass "database-roles"
} else {
    Add-Check fail "database-roles"
}

$controlMigrations = Invoke-DevNative "control-plane-migrations" {
    & $script:CpPython (Join-Path $script:DevRoot "scripts\apply_control_plane_migrations.py")
}
if ($controlMigrations.Code -eq 0) { Add-Check pass "control-plane-migrations" } else { Add-Check fail "control-plane-migrations" }

$crmMigrations = Invoke-DevNative "crm-migrations" {
    & $script:CrmPython (Join-Path $script:DevRoot "scripts\apply_crm_migrations.py")
}
if ($crmMigrations.Code -eq 0 -and $crmMigrations.Text -match "database=aadi_crm_dev") {
    Add-Check pass "crm-migrations"
} else {
    Add-Check fail "crm-migrations"
}

$inspected = Get-InspectText
if ($inspected.Code -ne 0) { Add-Check fail "inspect" } else { Add-Check pass "inspect" }
Assert-OutputLine $inspected.Text "control_plane_database=aadi_platform" "control-plane-name"
Assert-OutputLine $inspected.Text "crm_database=aadi_crm_dev" "crm-name"
Assert-OutputLine $inspected.Text "databases_distinct=True" "database-separation"
Assert-OutputLine $inspected.Text "control_plane_host_loopback=True" "control-plane-loopback"
Assert-OutputLine $inspected.Text "crm_host_loopback=True" "crm-loopback"
Assert-OutputLine $inspected.Text "environment=development" "development-environment"
Assert-OutputLine $inspected.Text "control_plane_revision_match=True" "control-plane-revision"
Assert-OutputLine $inspected.Text "crm_migration_match=True" "crm-revision"
Assert-OutputLine $inspected.Text "runtime_role_control_plane=aadi_platform_app" "control-plane-runtime-role"
Assert-OutputLine $inspected.Text "migration_role_control_plane=aadi_platform_migrator" "control-plane-migration-role"
Assert-OutputLine $inspected.Text "runtime_role_crm=aadi_crm_app" "crm-runtime-role"
Assert-OutputLine $inspected.Text "migration_role_crm=aadi_crm_migrator" "crm-migration-role"
Assert-OutputLine $inspected.Text "roles_separate_control_plane=True" "control-plane-roles-separate"
Assert-OutputLine $inspected.Text "roles_separate_crm=True" "crm-roles-separate"
Assert-OutputLine $inspected.Text "role aadi_platform_app=superuser=False createdb=False createrole=False" "control-plane-runtime-least-privilege"
Assert-OutputLine $inspected.Text "role aadi_crm_app=superuser=False createdb=False createrole=False" "crm-runtime-least-privilege"
Assert-OutputLine $inspected.Text "role aadi_platform_migrator=superuser=False createdb=False createrole=False" "control-plane-migrator-least-privilege"
Assert-OutputLine $inspected.Text "role aadi_crm_migrator=superuser=False createdb=False createrole=False" "crm-migrator-least-privilege"
Assert-OutputLine $inspected.Text "table_owners database=aadi_platform match=True" "control-plane-table-owner"
Assert-OutputLine $inspected.Text "table_owners database=aadi_crm_dev match=True" "crm-table-owner"
Assert-OutputLine $inspected.Text "wildcard_cleanup=disabled" "no-wildcard-cleanup"

$after = @(
    (Get-RepoPorcelain $script:ControlPlane),
    (Get-RepoPorcelain $script:Crm)
) -join "`n"
Add-Evidence $after
Set-Content -LiteralPath (Join-Path $script:DevRoot "evidence\git-status-after-test-01.txt") -Value (Redact-Evidence $after) -Encoding utf8
if ($before -eq $after) { Add-Check pass "git-unchanged" } else { Add-Check fail "git-unchanged" "product repositories changed" }

Complete-DevTest
