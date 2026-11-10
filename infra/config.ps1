# Shared names for every infra script. Dot-source it: . ./infra/config.ps1
# One place to change names; every script reads from here.

$RG   = "rg-ci-dev"
$LOC  = "canadacentral"      # ADR-0003: allowed by policy and offers the models
$AOAI = "aoai-ci-dev-2416"   # Azure OpenAI (one per region on this subscription)
$SA   = "stcidev2416"        # ADLS Gen2 data lake for contracts (globally unique name)
$DI   = "di-ci-dev-2416"     # Document Intelligence (S0, ADR-0015)
$SRCH = "srch-ci-dev-2416"   # AI Search (Free, ADR-0016)
$INDEX = "contracts-v1"      # chunk index for the evaluation set
$EMBED_DIMS = 1024           # ADR-0016
$FNSA = "stfncidev2416"      # Function plumbing: deployment package, ingest queue (kept apart from the lake)
$FN   = "fn-ci-dev-2416"     # Flex Consumption ingestion Function (ADR-0018)
$EGT  = "egst-ci-dev-2416"   # Event Grid system topic on the data lake
$PG   = "pg-ci-dev-2416"     # PostgreSQL Flexible Server: clause taxonomy, later agent checkpoints (ADR-0011)
$PGDB = "contracts"

$ErrorActionPreference = "Stop"

function Get-MyObjectId { az ad signed-in-user show --query id -o tsv }

function Grant-RoleToPrincipal($PrincipalId, $Role, $Scope) {
    # For managed identities (Function, Event Grid topic). Returns $true if a new assignment was made.
    # A new identity can take a minute to replicate in Entra ID, so the existence check may fail;
    # create by object ID (no directory lookup) and treat "already exists" as success.
    if ([string]::IsNullOrEmpty($PrincipalId)) { throw "Grant-RoleToPrincipal: empty principal ID for role '$Role'" }
    $existing = az role assignment list --assignee $PrincipalId --scope $Scope --role $Role --query "[].id" -o tsv 2>$null
    if (-not [string]::IsNullOrEmpty($existing)) { Write-Host "  = $Role (already)"; return $false }
    $out = az role assignment create --assignee-object-id $PrincipalId --assignee-principal-type ServicePrincipal `
        --role $Role --scope $Scope -o none 2>&1
    if ($LASTEXITCODE -ne 0 -and ($out -notmatch "RoleAssignmentExists")) { throw "Role '$Role' failed: $out" }
    Write-Host "  + $Role"
    return $true
}

function Grant-Role($Role, $Scope) {
    $me = Get-MyObjectId
    $existing = az role assignment list --assignee $me --scope $Scope --role $Role --query "[].id" -o tsv
    if ([string]::IsNullOrEmpty($existing)) {
        az role assignment create --assignee $me --role $Role --scope $Scope -o none
        Write-Host "Assigned '$Role'. Waiting 120 seconds for it to take effect..."
        Start-Sleep -Seconds 120
    } else {
        Write-Host "'$Role' already assigned"
    }
}
