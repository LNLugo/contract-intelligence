# Phase 9: deploy the Contracts API to Azure Container Apps (ADR-0025)
#   pwsh ./infra/09-container-app.ps1                 # deploy the image built for the current commit
#   pwsh ./infra/09-container-app.ps1 -Tag abc1234    # deploy a specific commit's image
#
# - Image built by GitHub Actions (.github/workflows/api-image.yml) and tagged with the commit;
#   ACR Tasks are not permitted on this subscription (build log, 2026-11-12)
# - Two user-assigned managed identities: one pulls the image (AcrPull), one is the API at runtime;
#   no registry password anywhere (the environment is Express: no system-assigned identities)
# - Least privilege at runtime: Search Index Data Reader (not Contributor), Cognitive Services OpenAI User.
#   No Key Vault, storage or PostgreSQL access: the API does not need them yet
# - Identity settings (issuer, audience, tenant) read from Key Vault at deploy time, passed as
#   environment variables (not secret); scale to zero when idle
param([string]$Tag = "", [ValidateSet("true", "false")][string]$Rerank = "true")
. "$PSScriptRoot/config.ps1"
Assert-ResourceSubscription

$repo = Split-Path $PSScriptRoot -Parent
# Default: the last commit that changed the image (the workflow only builds when these paths change)
if (-not $Tag) { $Tag = (git -C $repo log -1 --format=%h --abbrev=7 -- api agents identity ingestion/pipeline Dockerfile .dockerignore .github/workflows/api-image.yml).Trim() }
$tag = $Tag
$IMAGE = "$ACR.azurecr.io/contracts-api"
az config set extension.use_dynamic_install=yes_without_prompt -o none 2>$null   # containerapp CLI extension

Write-Host "== Resource providers" -ForegroundColor Cyan
foreach ($ns in "Microsoft.App", "Microsoft.OperationalInsights", "Microsoft.ContainerRegistry") {
    $s = (az provider show -n $ns --query registrationState -o tsv)
    if ($s -ne "Registered") { Write-Host "  registering $ns ..."; Invoke-Az provider register -n $ns --wait | Out-Null }
    Write-Host "  = $ns"
}

Write-Host "`n== Container Registry (Basic, admin user disabled)" -ForegroundColor Cyan
az acr show -n $ACR -g $RG -o none 2>$null
if ($LASTEXITCODE -ne 0) { Invoke-Az acr create -n $ACR -g $RG -l $LOC --sku Basic --admin-enabled false -o none | Out-Null; Write-Host "  + $ACR" }
else { Write-Host "  = $ACR" }
$acrId = (Invoke-Az acr show -n $ACR -g $RG --query id -o tsv | Out-String).Trim()

Write-Host "`n== Image contracts-api:$tag (built by GitHub Actions)" -ForegroundColor Cyan
$tags = @(az acr repository show-tags -n $ACR --repository contracts-api -o tsv 2>$null)
if ($tags -notcontains $tag) {
    throw "No image contracts-api:$tag in $ACR. Check the api-image workflow run for commit $tag in GitHub Actions (tests must pass before it builds)."
}
Write-Host "  = found"

Write-Host "`n== Log Analytics + Container Apps environment" -ForegroundColor Cyan
az monitor log-analytics workspace show -n $LAW -g $RG -o none 2>$null
if ($LASTEXITCODE -ne 0) { Invoke-Az monitor log-analytics workspace create -n $LAW -g $RG -l $LOC --retention-time 30 -o none | Out-Null; Write-Host "  + $LAW" }
else { Write-Host "  = $LAW" }
az containerapp env show -n $CAE -g $RG -o none 2>$null
if ($LASTEXITCODE -ne 0) {
    $lawCustomerId = (Invoke-Az monitor log-analytics workspace show -n $LAW -g $RG --query customerId -o tsv | Out-String).Trim()
    $lawKey = (Invoke-Az monitor log-analytics workspace get-shared-keys -n $LAW -g $RG --query primarySharedKey -o tsv | Out-String).Trim()
    Invoke-Az containerapp env create -n $CAE -g $RG -l $LOC --logs-workspace-id $lawCustomerId --logs-workspace-key $lawKey -o none | Out-Null
    $lawKey = $null
    Write-Host "  + $CAE"
} else { Write-Host "  = $CAE" }

Write-Host "`n== Identity settings (from Key Vault, not secret)" -ForegroundColor Cyan
$idcfg = (Invoke-Az keyvault secret show --vault-name $KV -n ci-identity-config --query value -o tsv | Out-String) | ConvertFrom-Json
if (-not $idcfg.tenantId -or -not $idcfg.audience -or -not $idcfg.issuer) { throw "ci-identity-config in $KV is incomplete; rerun infra/08-identity.ps1" }
$envVars = @("ID_TENANT_ID=$($idcfg.tenantId)", "ID_AUDIENCE=$($idcfg.audience)", "ID_ISSUER=$($idcfg.issuer)",
             "AOAI=$AOAI", "SRCH=$SRCH", "INDEX=$INDEX", "EMBED_DIMS=$EMBED_DIMS")
Write-Host "  issuer and audience set"

Write-Host "`n== Two user-assigned identities: one to pull the image, one for the running API" -ForegroundColor Cyan
# The environment is an Express environment, which supports only user-assigned identities
# (build log, 2026-11-12). Separate identities also separate duties: the pull identity can only
# read the registry; the runtime identity can only read the index and call the embedding model.
function Get-Uami($Name) {
    az identity show -n $Name -g $RG -o none 2>$null
    if ($LASTEXITCODE -ne 0) { Invoke-Az identity create -n $Name -g $RG -l $LOC -o none | Out-Null; Write-Host "  + $Name" }
    else { Write-Host "  = $Name" }
    return (Invoke-Az identity show -n $Name -g $RG -o json | Out-String) | ConvertFrom-Json
}
$pull = Get-Uami "id-ci-api-pull-2416"
$run  = Get-Uami "id-ci-api-run-2416"

Write-Host "`n== Roles (least privilege)" -ForegroundColor Cyan
$new = (Grant-RoleToPrincipal $pull.principalId "AcrPull" $acrId)
$new = (Grant-RoleToPrincipal $run.principalId "Search Index Data Reader" (az search service show -n $SRCH -g $RG --query id -o tsv)) -or $new
$new = (Grant-RoleToPrincipal $run.principalId "Cognitive Services OpenAI User" (az cognitiveservices account show -n $AOAI -g $RG --query id -o tsv)) -or $new
# Vendor tool (ADR-0026): read ONE secret, the API Management subscription key, not the whole vault
$kvId = (Invoke-Az keyvault show -n $KV -g $RG --query id -o tsv | Out-String).Trim()
$new = (Grant-RoleToPrincipal $run.principalId "Key Vault Secrets User" "$kvId/secrets/apim-subscription-key") -or $new
if ($new) { Write-Host "  waiting 90 s for new role assignments to take effect..."; Start-Sleep -Seconds 90 }

# DefaultAzureCredential inside the container uses the identity named by AZURE_CLIENT_ID
$envVars += "AZURE_CLIENT_ID=$($run.clientId)"
$envVars += "RERANK=$Rerank"
$envVars += "KV=$KV"
$envVars += "APIM=$APIM"

Write-Host "`n== Container App $CA" -ForegroundColor Cyan
$app = az containerapp show -n $CA -g $RG -o json 2>$null | ConvertFrom-Json
if ($null -ne $app -and "$($app.identity.type)" -match "SystemAssigned") {
    # Left over from the first attempt (system-assigned identity, refused on Express). Nothing was
    # served from it; remove its role assignments, then the app, and create it again.
    $sp = $app.identity.principalId
    foreach ($ra in @(az role assignment list --assignee $sp --all --query "[].id" -o tsv)) {
        if ($ra) { Invoke-Az role assignment delete --ids $ra -o none | Out-Null }
    }
    Invoke-Az containerapp delete -n $CA -g $RG --yes -o none | Out-Null
    Write-Host "  - removed first attempt (system-assigned identity and its roles)"
    $app = $null
}
if ($null -eq $app) {
    Invoke-Az containerapp create -n $CA -g $RG --environment $CAE `
        --user-assigned $pull.id $run.id --registry-server "$ACR.azurecr.io" --registry-identity $pull.id `
        --image "$IMAGE`:$tag" --target-port 8000 --ingress external --env-vars @envVars `
        --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi -o none | Out-Null
    Write-Host "  + $CA running contracts-api:$tag"
} else {
    Invoke-Az containerapp update -n $CA -g $RG --image "$IMAGE`:$tag" --set-env-vars @envVars `
        --min-replicas 0 --max-replicas 1 -o none | Out-Null
    Write-Host "  ~ $CA now running contracts-api:$tag"
}
$fqdn = (Invoke-Az containerapp show -n $CA -g $RG --query properties.configuration.ingress.fqdn -o tsv | Out-String).Trim()
if ([string]::IsNullOrEmpty($fqdn)) { throw "No ingress hostname returned for $CA" }

Write-Host "`n== Checks (first request may take ~20 s: the app scales from zero)" -ForegroundColor Cyan
$base = "https://$fqdn"
$health = curl -s -o /dev/null -w "%{http_code}" --max-time 90 "$base/health"
$noToken = curl -s -o /dev/null -w "%{http_code}" --max-time 60 -X POST "$base/search" -H "Content-Type: application/json" -d '{"query":"x"}'
$serverHdr = (curl -s -I --max-time 60 "$base/health" | Select-String -Pattern "^server:" | Out-String).Trim()
Write-Host "  /health                 $health   (expect 200)"
Write-Host "  /search without token   $noToken   (expect 401)"
Write-Host "  server header           $(if ($serverHdr) { $serverHdr } else { 'none from the app' })"
if ($health -ne "200" -or $noToken -ne "401") { throw "Deployed API checks failed. Logs: az containerapp logs show -n $CA -g $RG --tail 50" }

Write-Host "`nDeployed: $base  (image contracts-api:$tag)"
Write-Host "Next, on the laptop: python -m api.smoke_test --base-url $base"
