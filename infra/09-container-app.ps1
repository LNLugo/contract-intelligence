# Phase 9: deploy the Contracts API to Azure Container Apps (ADR-0025)
#   pwsh ./infra/09-container-app.ps1                 # build a new image and deploy
#   pwsh ./infra/09-container-app.ps1 -SkipBuild      # redeploy the last image (settings/roles only)
#
# - Image built in the cloud with ACR Tasks (no local Docker), tagged with the git commit
# - Container App with a system-assigned managed identity; pulls from ACR with that identity (AcrPull),
#   no registry password anywhere
# - Least privilege at runtime: Search Index Data Reader (not Contributor), Cognitive Services OpenAI User.
#   No Key Vault, storage or PostgreSQL access: the API does not need them yet
# - Identity settings (issuer, audience, tenant) read from Key Vault at deploy time, passed as
#   environment variables (not secret); scale to zero when idle
param([switch]$SkipBuild)
. "$PSScriptRoot/config.ps1"
Assert-ResourceSubscription

$repo = Split-Path $PSScriptRoot -Parent
$tag = (git -C $repo rev-parse --short HEAD).Trim()
if (-not $SkipBuild -and (git -C $repo status --porcelain -- api agents identity ingestion/pipeline Dockerfile)) {
    throw "Uncommitted changes in the API code. Commit and push first, so the image tag names exactly what is deployed."
}
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

if (-not $SkipBuild) {
    Write-Host "`n== Build image $IMAGE`:$tag in ACR (cloud build)" -ForegroundColor Cyan
    az acr build -r $ACR -t "contracts-api:$tag" -f "$repo/Dockerfile" $repo -o none
    if ($LASTEXITCODE -ne 0) {
        throw "ACR build failed. If the error says tasks are not allowed on this subscription, tell Claude: the fallback is building in GitHub Actions."
    }
    Write-Host "  + contracts-api:$tag"
} else {
    $tag = (Invoke-Az acr repository show-tags -n $ACR --repository contracts-api --orderby time_desc --top 1 -o tsv | Out-String).Trim()
    Write-Host "`n== Reusing image contracts-api:$tag"
}

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

Write-Host "`n== Container App $CA" -ForegroundColor Cyan
az containerapp show -n $CA -g $RG -o none 2>$null
$exists = ($LASTEXITCODE -eq 0)
if (-not $exists) {
    # Start from a public placeholder image: the identity must exist before it can be allowed to pull from ACR
    Invoke-Az containerapp create -n $CA -g $RG --environment $CAE --system-assigned `
        --image mcr.microsoft.com/k8se/quickstart:latest --target-port 80 --ingress external `
        --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi -o none | Out-Null
    Write-Host "  + $CA (placeholder image)"
} else { Write-Host "  = $CA" }
$principal = (Invoke-Az containerapp show -n $CA -g $RG --query identity.principalId -o tsv | Out-String).Trim()

Write-Host "`n== Roles for the API's managed identity (least privilege)" -ForegroundColor Cyan
$new = (Grant-RoleToPrincipal $principal "AcrPull" $acrId)
$new = (Grant-RoleToPrincipal $principal "Search Index Data Reader" (az search service show -n $SRCH -g $RG --query id -o tsv)) -or $new
$new = (Grant-RoleToPrincipal $principal "Cognitive Services OpenAI User" (az cognitiveservices account show -n $AOAI -g $RG --query id -o tsv)) -or $new
if ($new) { Write-Host "  waiting 90 s for new role assignments to take effect..."; Start-Sleep -Seconds 90 }

Write-Host "`n== Deploy contracts-api:$tag" -ForegroundColor Cyan
Invoke-Az containerapp registry set -n $CA -g $RG --server "$ACR.azurecr.io" --identity system -o none | Out-Null
Invoke-Az containerapp ingress update -n $CA -g $RG --target-port 8000 -o none | Out-Null
Invoke-Az containerapp update -n $CA -g $RG --image "$IMAGE`:$tag" --set-env-vars @envVars `
    --min-replicas 0 --max-replicas 1 -o none | Out-Null
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
