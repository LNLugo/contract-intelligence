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
$KV     = "kv-ci-dev-2416"     # Key Vault: system-of-record credential, APIM subscription key (ADR-0010)
$APIM   = "apim-ci-dev-2416"   # API Management, Consumption tier
$SAPFN  = "fn-sapmock-2416"    # mock SAP vendor master (separate app: a different system)
$ACR    = "acrcidev2416"       # Container Registry (Basic), images pulled by managed identity (ADR-0025)
$LAW    = "law-ci-dev-2416"    # Log Analytics for the Container Apps environment
$CAE    = "cae-ci-dev-2416"    # Container Apps environment (Consumption)
$CA     = "ca-ci-api-2416"     # Contracts API (ADR-0023, ADR-0024, ADR-0025)

$ErrorActionPreference = "Stop"

function Get-MyObjectId { az ad signed-in-user show --query id -o tsv }

function Invoke-Az {
    # Run az and STOP on failure. Native commands do not throw in PowerShell, so without this
    # a failed step is followed by a success message (build log, 2026-11-09, twice).
    # No param() block on purpose: an advanced function would try to bind -g, -n, -o as its own
    # parameters. $args passes every argument through to az unchanged.
    $azArgs = @($args)
    $out = & az @azArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($azArgs[0..2] -join ' ') failed:`n$($out | Out-String)" }
    return $out
}

function Invoke-Arm($Method, $Url, $BodyObject) {
    # Resource Manager REST call with fail-fast; used where the CLI lags the platform
    $tmp = New-TemporaryFile
    if ($null -ne $BodyObject) { $BodyObject | ConvertTo-Json -Depth 20 | Set-Content $tmp }
    $azArgs = @("rest", "--method", $Method, "--url", $Url)
    if ($null -ne $BodyObject) { $azArgs += @("--body", "@$tmp", "--headers", "Content-Type=application/json") }
    $out = & az @azArgs 2>&1
    Remove-Item $tmp -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) { throw "$Method $Url failed:`n$($out | Out-String)" }
    return ($out | Out-String)
}

function Test-AzOption($Command, $Option) {
    # The CLI renames options between versions; check what this installation supports
    $help = & az @($Command.Split(' ') + '--help') 2>&1 | Out-String
    return $help -match [regex]::Escape($Option)
}

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

function Assert-ResourceSubscription {
    # Two tenants are in play since Phase 8 (ADR-0024). Every resource script checks it is pointed
    # at the subscription that holds $RG before doing anything (build log, 2026-11-11).
    $sub = az account show --query "{name:name, tenant:tenantId}" -o json 2>$null | ConvertFrom-Json
    az group show -n $RG -o none 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Resource group $RG not found in '$($sub.name)'. Switch back: az account set --subscription 'Azure for Students' (or az login)."
    }
}

