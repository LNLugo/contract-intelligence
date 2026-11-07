# Phase 1: ADLS Gen2 data lake for contracts, keyless
# ADRs: 0001 (public first, identity first), 0004 (raw and extracted kept separately), 0013 (no keys)
# Run: pwsh ./infra/01-storage.ps1   (safe to re-run)

. "$PSScriptRoot/config.ps1"

# 1. Storage account: hierarchical namespace on (ADLS Gen2), no public blobs, no shared keys
Write-Host "`n== Storage account $SA" -ForegroundColor Cyan
$exists = az storage account list -g $RG --query "[?name=='$SA'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    $avail = az storage account check-name -n $SA --query nameAvailable -o tsv
    if ($avail -ne "true") { throw "Name $SA is taken globally. Change `$SA in infra/config.ps1 and re-run." }
    az storage account create -n $SA -g $RG -l $LOC `
        --sku Standard_LRS --kind StorageV2 --hns true `
        --min-tls-version TLS1_2 --allow-blob-public-access false `
        --allow-shared-key-access false -o none
    Write-Host "Created"
} else {
    Write-Host "Already exists"
}

# 2. Data-plane role for me (Contributor on the resource does NOT grant data access)
Write-Host "`n== Role assignment" -ForegroundColor Cyan
$scope = az storage account show -n $SA -g $RG --query id -o tsv
Grant-Role "Storage Blob Data Contributor" $scope

# 3. File systems (containers): one per stage of the pipeline
#    contracts-raw        uploaded PDFs; Event Grid fires on BlobCreated here (phase 5)
#    contracts-extracted  Document Intelligence JSON; re-chunk without re-extracting (ADR-0004)
#    deadletter           events that failed after retries (phase 5)
Write-Host "`n== File systems" -ForegroundColor Cyan
foreach ($fs in @("contracts-raw", "contracts-extracted", "deadletter")) {
    $found = az storage fs exists -n $fs --account-name $SA --auth-mode login --query exists -o tsv
    if ($found -ne "true") {
        az storage fs create -n $fs --account-name $SA --auth-mode login -o none
        Write-Host "Created $fs"
    } else {
        Write-Host "$fs already exists"
    }
}

# 4. Smoke test: write and read with my identity, and prove keys are refused
Write-Host "`n== Smoke test" -ForegroundColor Cyan
$tmp = New-TemporaryFile
"phase 1 smoke test $(Get-Date -Format o)" | Out-File $tmp
az storage fs file upload -f contracts-raw -p "_smoketest/hello.txt" -s $tmp --account-name $SA --auth-mode login --overwrite -o none
az storage fs file list -f contracts-raw --path _smoketest --account-name $SA --auth-mode login --query "[].name" -o tsv
az storage fs file delete -f contracts-raw -p "_smoketest/hello.txt" --account-name $SA --auth-mode login --yes -o none
Remove-Item $tmp
Write-Host "Write, list, delete with Entra identity: OK"

$keyAccess = az storage account show -n $SA -g $RG --query allowSharedKeyAccess -o tsv
Write-Host "Shared key access allowed: $keyAccess   (expect false)"
$hns = az storage account show -n $SA -g $RG --query isHnsEnabled -o tsv
Write-Host "Hierarchical namespace: $hns   (expect true)"
