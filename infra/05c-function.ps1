# Phase 5c: Event Grid -> storage queue -> Flex Consumption Function -> pipeline (ADR-0017, ADR-0018)
# Run in Cloud Shell from the repo root: pwsh ./infra/05c-function.ps1   (safe to re-run)
# Takes about 10 minutes: role propagation waits and a remote Python build.

. "$PSScriptRoot/config.ps1"
$PyVersion = "3.12"     # if Flex rejects it in this region, change to "3.11" and re-run
$Repo = Split-Path $PSScriptRoot -Parent

Write-Host "`n== Resource providers" -ForegroundColor Cyan
foreach ($ns in "Microsoft.Web", "Microsoft.EventGrid", "Microsoft.Insights", "Microsoft.OperationalInsights") {
    az provider register -n $ns --wait -o none
}
Write-Host "Registered"

# 1. Plumbing storage account: deployment package, ingest queue, host state
Write-Host "`n== Function storage $FNSA" -ForegroundColor Cyan
$exists = az storage account list -g $RG --query "[?name=='$FNSA'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    # Shared keys stay on until the Function is configured for identity, then are switched off (step 6)
    az storage account create -n $FNSA -g $RG -l $LOC --sku Standard_LRS --kind StorageV2 `
        --min-tls-version TLS1_2 --allow-blob-public-access false -o none
    Write-Host "Created"
} else { Write-Host "Already exists" }
$fnsaId = az storage account show -n $FNSA -g $RG --query id -o tsv
$lakeId = az storage account show -n $SA -g $RG --query id -o tsv

Grant-Role "Storage Blob Data Contributor" $fnsaId
Grant-Role "Storage Queue Data Contributor" $fnsaId
foreach ($q in "ingest", "ingest-poison") {
    az storage queue create -n $q --account-name $FNSA --auth-mode login -o none
}
az storage container create -n app-package --account-name $FNSA --auth-mode login -o none
Write-Host "Queues ingest, ingest-poison and container app-package ready"

# 2. Function app on Flex Consumption with a system-assigned identity
Write-Host "`n== Function app $FN (Flex Consumption, Python $PyVersion)" -ForegroundColor Cyan
$exists = az functionapp list -g $RG --query "[?name=='$FN'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    az functionapp create -g $RG -n $FN --storage-account $FNSA --flexconsumption-location $LOC `
        --runtime python --runtime-version $PyVersion --instance-memory 2048 `
        --deployment-storage-name $FNSA --deployment-storage-container-name app-package `
        --deployment-storage-auth-type SystemAssignedIdentity -o none
    Write-Host "Created"
} else { Write-Host "Already exists" }
$fnPrincipal = az functionapp identity show -g $RG -n $FN --query principalId -o tsv
if ([string]::IsNullOrEmpty($fnPrincipal)) {
    $fnPrincipal = az functionapp identity assign -g $RG -n $FN --query principalId -o tsv
}
Write-Host "Function identity: $fnPrincipal"

# 3. Least-privilege roles for the Function identity
Write-Host "`n== Function identity roles" -ForegroundColor Cyan
$new = $false
$new = (Grant-RoleToPrincipal $fnPrincipal "Storage Blob Data Owner" $fnsaId) -or $new
$new = (Grant-RoleToPrincipal $fnPrincipal "Storage Queue Data Contributor" $fnsaId) -or $new
$new = (Grant-RoleToPrincipal $fnPrincipal "Storage Blob Data Contributor" $lakeId) -or $new
$new = (Grant-RoleToPrincipal $fnPrincipal "Cognitive Services User" (az cognitiveservices account show -n $DI -g $RG --query id -o tsv)) -or $new
$new = (Grant-RoleToPrincipal $fnPrincipal "Cognitive Services OpenAI User" (az cognitiveservices account show -n $AOAI -g $RG --query id -o tsv)) -or $new
$new = (Grant-RoleToPrincipal $fnPrincipal "Search Index Data Contributor" (az search service show -n $SRCH -g $RG --query id -o tsv)) -or $new

# 4. App settings: identity-based connections only, no connection strings
Write-Host "`n== App settings" -ForegroundColor Cyan
az functionapp config appsettings set -g $RG -n $FN -o none --settings `
    "AzureWebJobsStorage__accountName=$FNSA" `
    "IngestQueue__queueServiceUri=https://$FNSA.queue.core.windows.net" `
    "AOAI=$AOAI" "SA=$SA" "DI=$DI" "SRCH=$SRCH" "INDEX=$INDEX" "EMBED_DIMS=$EMBED_DIMS" "EMBED_TPM=150000"
az functionapp config appsettings delete -g $RG -n $FN --setting-names AzureWebJobsStorage -o none 2>$null
Write-Host "Identity-based settings applied; AzureWebJobsStorage connection string removed"

if ($new) { Write-Host "Waiting 120 s for new role assignments..."; Start-Sleep -Seconds 120 }

# 5. Deploy the code: same pipeline library as the batch script, remote build on Azure
Write-Host "`n== Deploy" -ForegroundColor Cyan
# Stage only what the Function needs (Compress-Archive flattens individual files, so copy into a tree first)
$src   = Join-Path $Repo "ingestion"
$stage = Join-Path ([IO.Path]::GetTempPath()) "ingestion-stage"
$pkg   = Join-Path ([IO.Path]::GetTempPath()) "ingestion.zip"
Remove-Item $stage, $pkg -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path (Join-Path $stage "pipeline") -Force | Out-Null
Copy-Item (Join-Path $src "function_app.py"), (Join-Path $src "host.json"), (Join-Path $src "requirements.txt") $stage
Copy-Item (Join-Path $src "pipeline/*.py") (Join-Path $stage "pipeline")
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $pkg
Write-Host "Package: $((Get-ChildItem $stage -Recurse -File).Count) files"
az functionapp deployment source config-zip -g $RG -n $FN --src $pkg --build-remote true -o none
Start-Sleep -Seconds 20
$fns = az functionapp function list -g $RG -n $FN --query "[].name" -o tsv
Write-Host "Functions deployed: $fns   (expect $FN/ingest)"

# 6. Now that the Function uses its identity, switch shared keys off on the plumbing account
Write-Host "`n== Disable shared keys on $FNSA" -ForegroundColor Cyan
az storage account update -n $FNSA -g $RG --allow-shared-key-access false -o none
Write-Host "Shared key access: $(az storage account show -n $FNSA -g $RG --query allowSharedKeyAccess -o tsv)"

# 7. Event Grid system topic on the data lake, with its own identity for delivery and dead-lettering
Write-Host "`n== Event Grid system topic $EGT" -ForegroundColor Cyan
$topic = az eventgrid system-topic list -g $RG --query "[?source=='$lakeId'].name | [0]" -o tsv
if ([string]::IsNullOrEmpty($topic)) {
    az eventgrid system-topic create -g $RG -n $EGT -l $LOC --topic-type microsoft.storage.storageaccounts `
        --source $lakeId -o none
    $topic = $EGT
    Write-Host "Created"
} else { Write-Host "Using existing topic $topic" }
$topicPrincipal = az eventgrid system-topic show -g $RG -n $topic --query identity.principalId -o tsv
if ([string]::IsNullOrEmpty($topicPrincipal)) {
    az eventgrid system-topic update -g $RG -n $topic --mi-system-assigned -o none 2>$null
    if ($LASTEXITCODE -ne 0) { az eventgrid system-topic update -g $RG -n $topic --identity systemassigned -o none }
    $topicPrincipal = az eventgrid system-topic show -g $RG -n $topic --query identity.principalId -o tsv
}
Write-Host "Topic identity: $topicPrincipal"
$new = $false
$new = (Grant-RoleToPrincipal $topicPrincipal "Storage Queue Data Message Sender" $fnsaId) -or $new
$new = (Grant-RoleToPrincipal $topicPrincipal "Storage Blob Data Contributor" $lakeId) -or $new
if ($new) { Write-Host "Waiting 120 s for topic role assignments..."; Start-Sleep -Seconds 120 }

# 8. Subscription: only PDFs written to contracts-raw/inbox/, only real blob writes
Write-Host "`n== Event subscription ingest-inbox" -ForegroundColor Cyan
az eventgrid system-topic event-subscription create -g $RG --system-topic-name $topic -n ingest-inbox `
    --delivery-identity systemassigned --delivery-identity-endpoint-type storagequeue `
    --delivery-identity-endpoint "$fnsaId/queueservices/default/queues/ingest" `
    --included-event-types Microsoft.Storage.BlobCreated `
    --subject-begins-with "/blobServices/default/containers/contracts-raw/blobs/inbox/" `
    --subject-ends-with ".pdf" `
    --advanced-filter data.api StringIn PutBlob PutBlockList FlushWithClose `
    --max-delivery-attempts 10 --event-ttl 1440 `
    --deadletter-identity systemassigned `
    --deadletter-identity-endpoint "$lakeId/blobServices/default/containers/deadletter" -o none
az eventgrid system-topic event-subscription show -g $RG --system-topic-name $topic -n ingest-inbox `
    --query "{state:provisioningState, prefix:filter.subjectBeginsWith, maxAttempts:retryPolicy.maxDeliveryAttempts}" -o table

Write-Host "`nReady. Test from the laptop with: python ingestion/upload_to_inbox.py <pdf> --type <type> --groups grp-legal" -ForegroundColor Green
