# Test 3 — CRM projects, forms, and sample records.
# Uses the existing CRM migrations and seed script. It does not add product behavior
# and it does not drop a database.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_DevTestCommon.ps1")
Initialize-DevTest -EvidenceName "03-crm-seed.log"

if (-not (Import-DevIdentity)) {
    Complete-DevTest
}

$migrations = Invoke-DevNative "crm-migrations" {
    & $script:CrmPython (Join-Path $script:DevRoot "scripts\apply_crm_migrations.py")
}
if ($migrations.Code -eq 0 -and $migrations.Text -match "database=aadi_crm_dev") {
    Add-Check pass "crm-migrations"
} else {
    Add-Check fail "crm-migrations"
}

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

$before = Get-InspectText
if ($before.Code -eq 0) { Add-Check pass "inspect-before" } else { Add-Check fail "inspect-before" }

function Invoke-CrmSeed {
    param([string]$Label)
    return Invoke-DevNative $Label {
        & $script:CrmPython (Join-Path $script:CrmBackend "scripts\seed_development_projects.py") `
            --catalog $script:Catalog `
            --state $script:State `
            --fixture $script:Fixture
    }
}

$first = Invoke-CrmSeed "crm-seed-first"
if ($first.Code -eq 0 -and $first.Text -match "verified crm-seed") {
    Add-Check pass "crm-seed"
} else {
    Add-Check fail "crm-seed"
}

$mid = Get-InspectText
if ($mid.Code -eq 0) { Add-Check pass "inspect-after-first-seed" } else { Add-Check fail "inspect-after-first-seed" }

$second = Invoke-CrmSeed "crm-seed-second"
if ($second.Code -eq 0 -and $second.Text -match "verified crm-seed") {
    Add-Check pass "crm-seed-second"
} else {
    Add-Check fail "crm-seed-second"
}
Assert-NoCreatedRows $second.Text "crm-idempotent"

$after = Get-InspectText
if ($after.Code -eq 0) { Add-Check pass "inspect-after" } else { Add-Check fail "inspect-after" }
Assert-SameLines $mid.Text $after.Text "^count (projects_|forms_|records_|fields_|project_members_)" "crm-counts-unchanged"

foreach ($code in @("PRESCHOOL", "PANEERWALA", "SPACE-VIEW", "HIRING")) {
    Assert-OutputLine $after.Text "count projects_${code}=1" "one-project-$code"
    Assert-OutputLine $after.Text "count forms_${code}=1" "one-form-$code"
    Assert-OutputLine $after.Text "field_order code=$code match=True" "field-order-$code"
    Assert-OutputLine $after.Text "dropdowns code=$code match=True" "dropdowns-$code"
    Assert-OutputLine $after.Text "project_tenant code=$code match=True" "tenant-$code"
}
Assert-OutputLine $after.Text "count records_PRESCHOOL=4" "records-preschool"
Assert-OutputLine $after.Text "count records_PANEERWALA=3" "records-paneerwala"
Assert-OutputLine $after.Text "count records_SPACE-VIEW=3" "records-space-view"
Assert-OutputLine $after.Text "count records_HIRING=3" "records-hiring"
Assert-OutputLine $after.Text "import_record=present" "import-fixture"
foreach ($seed in @("preschool-01", "preschool-02", "paneerwala-02", "space-view-01", "hiring-02")) {
    Assert-OutputLine $after.Text "follow_up ${seed}=present" "follow-up-$seed"
}

Complete-DevTest
