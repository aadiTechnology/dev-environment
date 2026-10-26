# Test 2 — Control Plane bootstrap and seed.
# Applies the supported migrations and seed twice. It does not drop a database.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_DevTestCommon.ps1")
Initialize-DevTest -EvidenceName "02-control-plane-seed.log"

if (-not (Import-DevIdentity)) {
    Complete-DevTest
}

$migrations = Invoke-DevNative "control-plane-migrations" {
    & $script:CpPython (Join-Path $script:DevRoot "scripts\apply_control_plane_migrations.py")
}
if ($migrations.Code -eq 0) { Add-Check pass "control-plane-migrations" } else { Add-Check fail "control-plane-migrations" }

$before = Get-InspectText
if ($before.Code -eq 0) { Add-Check pass "inspect-before" } else { Add-Check fail "inspect-before" }

$prepare = Invoke-DevNative "control-plane-prepare" {
    & $script:CpPython (Join-Path $script:CpBackend "scripts\seed_development_tenant.py") prepare --state $script:State
}
if ($prepare.Code -ne 0) {
    Add-Check fail "control-plane-prepare"
    Complete-DevTest
}
if ($prepare.Text -match "RESTART_REQUIRED") {
    Add-Check fail "control-plane-prepare" "the running API must be restarted by hand before seeding"
    Complete-DevTest
}
Add-Check pass "control-plane-prepare"

$api = Invoke-DevNative "control-plane-api" {
    & $script:CpPython (Join-Path $script:DevRoot "scripts\start_api.py") `
        --app control-plane --port 8000 --health-path /health `
        --log (Join-Path $script:Logs "control-plane-api.log")
}
if ($api.Code -eq 0) { Add-Check pass "control-plane-api" } else { Add-Check fail "control-plane-api" }

$first = Invoke-DevNative "control-plane-seed-first" {
    & $script:CpPython (Join-Path $script:CpBackend "scripts\seed_development_tenant.py") apply --state $script:State
}
if ($first.Code -eq 0 -and $first.Text -match "verified control-plane-seed") {
    Add-Check pass "control-plane-seed"
} else {
    Add-Check fail "control-plane-seed"
}

$mid = Get-InspectText
if ($mid.Code -eq 0) { Add-Check pass "inspect-after-first-seed" } else { Add-Check fail "inspect-after-first-seed" }

$second = Invoke-DevNative "control-plane-seed-second" {
    & $script:CpPython (Join-Path $script:CpBackend "scripts\seed_development_tenant.py") apply --state $script:State
}
if ($second.Code -eq 0 -and $second.Text -match "verified control-plane-seed") {
    Add-Check pass "control-plane-seed-second"
} else {
    Add-Check fail "control-plane-seed-second"
}
Assert-NoCreatedRows $second.Text "control-plane-idempotent"

$after = Get-InspectText
if ($after.Code -eq 0) { Add-Check pass "inspect-after" } else { Add-Check fail "inspect-after" }
Assert-SameLines $mid.Text $after.Text "^count " "seed-counts-unchanged"
Assert-OutputLine $after.Text "organization_tables=0" "no-organization-table"
Assert-OutputLine $after.Text "workspace_tables=0" "no-workspace-table"
Assert-OutputLine $after.Text "identity_count=1" "one-development-user"
Assert-OutputLine $after.Text "tenant_count=1" "one-development-tenant"
Assert-OutputLine $after.Text "product_crm_count=1" "one-crm-product"
Assert-OutputLine $after.Text "plan_count=1" "one-development-plan"
Assert-OutputLine $after.Text "subscription_active_count=1" "one-active-subscription"
Assert-OutputLine $after.Text "membership_count=1" "one-tenant-membership"
Assert-OutputLine $after.Text "role_count=1" "one-development-role"
Assert-OutputLine $after.Text "plan_features=lead_management,project_management,records" "plan-features"
Assert-OutputLine $after.Text "permission crm.lead_management.read=present" "permission-leads"
Assert-OutputLine $after.Text "permission crm.project_management.manage=present" "permission-projects"
Assert-OutputLine $after.Text "permission roles.manage=present" "permission-roles"
Assert-OutputLine $after.Text "entitlement_tables=0" "entitlements-evaluated-from-subscription"

Complete-DevTest
