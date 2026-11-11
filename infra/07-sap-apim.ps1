# Phase 7: system-of-record integration (ADR-0010)
#   agent --(APIM subscription key, read from Key Vault)--> API Management
#   API Management --(SAP credential, Key Vault-backed named value via APIM's managed identity)--> mock SAP
#   mock SAP reads the same credential through a Key Vault reference in its app settings
# No secret is printed, stored in config, or committed. Run in Cloud Shell:
#   pwsh ./infra/07-sap-apim.ps1        (safe to re-run; API Management creation takes several minutes)

. "$PSScriptRoot/config.ps1"
$ApimApi = "2022-08-01"
$sub = az account show --query id -o tsv
$rgId = "/subscriptions/$sub/resourceGroups/$RG"

Write-Host "`n== Providers" -ForegroundColor Cyan
foreach ($ns in "Microsoft.KeyVault", "Microsoft.ApiManagement") { Invoke-Az provider register -n $ns --wait -o none | Out-Null }
Write-Host "Registered"

# ---------------------------------------------------------------- 1. Key Vault (RBAC mode)
Write-Host "`n== Key Vault $KV" -ForegroundColor Cyan
$exists = az keyvault list -g $RG --query "[?name=='$KV'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    Invoke-Az keyvault create -n $KV -g $RG -l $LOC --enable-rbac-authorization true -o none | Out-Null
    Write-Host "Created (RBAC authorization; access policies not used)"
} else { Write-Host "Already exists" }
$kvId  = az keyvault show -n $KV -g $RG --query id -o tsv
$kvUri = az keyvault show -n $KV -g $RG --query properties.vaultUri -o tsv
Grant-Role "Key Vault Secrets Officer" $kvId

function Set-RandomSecret($Name) {
    # Generate in memory, write through a temp file (never on the command line or the screen)
    $existing = az keyvault secret list --vault-name $KV --query "[?name=='$Name'].name" -o tsv 2>$null
    if (-not [string]::IsNullOrEmpty($existing)) { Write-Host "Secret $Name already exists (kept)"; return }
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $tmp = New-TemporaryFile
    [Convert]::ToBase64String($bytes) | Set-Content -NoNewline $tmp
    Invoke-Az keyvault secret set --vault-name $KV -n $Name --file $tmp -o none | Out-Null
    Remove-Item $tmp
    Write-Host "Secret $Name created (value never displayed)"
}
Set-RandomSecret "sap-api-key"

# ---------------------------------------------------------------- 2. Mock SAP Function app
Write-Host "`n== Mock SAP Function $SAPFN" -ForegroundColor Cyan
$fnsaId = az storage account show -n $FNSA -g $RG --query id -o tsv
$exists = az functionapp list -g $RG --query "[?name=='$SAPFN'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    # Flex creation reads the storage account's keys once. Keys are re-disabled at the end of this
    # step; the window is minutes and the app is configured for identity before it closes.
    Invoke-Az storage account update -n $FNSA -g $RG --allow-shared-key-access true -o none | Out-Null
    Invoke-Az storage container create -n app-package-sapmock --account-name $FNSA --auth-mode login -o none | Out-Null
    Invoke-Az functionapp create -g $RG -n $SAPFN --storage-account $FNSA --flexconsumption-location $LOC `
        --runtime python --runtime-version 3.12 --instance-memory 2048 `
        --deployment-storage-name $FNSA --deployment-storage-container-name app-package-sapmock `
        --deployment-storage-auth-type SystemAssignedIdentity -o none | Out-Null
    Write-Host "Created"
} else { Write-Host "Already exists" }
$sapPrincipal = az functionapp identity show -g $RG -n $SAPFN --query principalId -o tsv
if ([string]::IsNullOrEmpty($sapPrincipal)) { $sapPrincipal = az functionapp identity assign -g $RG -n $SAPFN --query principalId -o tsv }
$new = $false
$new = (Grant-RoleToPrincipal $sapPrincipal "Storage Blob Data Owner" $fnsaId) -or $new
$new = (Grant-RoleToPrincipal $sapPrincipal "Storage Queue Data Contributor" $fnsaId) -or $new
$new = (Grant-RoleToPrincipal $sapPrincipal "Key Vault Secrets User" $kvId) -or $new

Invoke-Az functionapp config appsettings set -g $RG -n $SAPFN -o none --settings `
    "AzureWebJobsStorage__accountName=$FNSA" `
    "SAP_API_KEY=@Microsoft.KeyVault(SecretUri=$($kvUri)secrets/sap-api-key/)" | Out-Null
az functionapp config appsettings delete -g $RG -n $SAPFN --setting-names AzureWebJobsStorage -o none 2>$null
Invoke-Az storage account update -n $FNSA -g $RG --allow-shared-key-access false -o none | Out-Null
Write-Host "Identity-based storage, SAP_API_KEY as a Key Vault reference, shared keys disabled again"
if ($new) { Write-Host "Waiting 120 s for new role assignments..."; Start-Sleep -Seconds 120 }

$src = Join-Path (Split-Path $PSScriptRoot -Parent) "sap-mock"
$pkg = Join-Path ([IO.Path]::GetTempPath()) "sapmock.zip"
Remove-Item $pkg -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $src "*") -DestinationPath $pkg
Invoke-Az functionapp deployment source config-zip -g $RG -n $SAPFN --src $pkg --build-remote true -o none | Out-Null
# Flex Consumption apps do not always fill defaultHostName at the top level; try every place the
# host can live and stop if none has it (a blank host produced "https:///api", build log 2026-11-11)
$sapHost = $null
foreach ($q in "defaultHostName", "properties.defaultHostName", "hostNames[0]", "enabledHostNames[0]") {
    $h = az functionapp show -g $RG -n $SAPFN --query $q -o tsv 2>$null
    if (-not [string]::IsNullOrEmpty($h) -and $h -notmatch "\.scm\.") { $sapHost = $h; break }
}
if ([string]::IsNullOrEmpty($sapHost)) { throw "Could not determine the host name of $SAPFN" }
Write-Host "Deployed: https://$sapHost/api/vendors/{id}"

# ---------------------------------------------------------------- 3. API Management (Consumption)
Write-Host "`n== API Management $APIM (Consumption; first creation takes several minutes)" -ForegroundColor Cyan
$exists = az apim list -g $RG --query "[?name=='$APIM'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    $upn = az ad signed-in-user show --query userPrincipalName -o tsv
    Invoke-Az apim create -g $RG -n $APIM -l $LOC --sku-name Consumption `
        --publisher-name "Contract Intelligence (dev)" --publisher-email $upn `
        --enable-managed-identity true -o none | Out-Null
    Write-Host "Created"
} else { Write-Host "Already exists" }
$apimId = "$rgId/providers/Microsoft.ApiManagement/service/$APIM"
$apimPrincipal = az apim show -g $RG -n $APIM --query identity.principalId -o tsv
if ([string]::IsNullOrEmpty($apimPrincipal)) { throw "API Management has no managed identity" }
if (Grant-RoleToPrincipal $apimPrincipal "Key Vault Secrets User" $kvId) {
    Write-Host "Waiting 120 s for APIM's Key Vault role..."; Start-Sleep -Seconds 120
}

# Key Vault-backed named value: APIM fetches the SAP credential with its own identity
$base = "https://management.azure.com$apimId"
Invoke-Arm "put" "$base/namedValues/sap-api-key?api-version=$ApimApi" @{
    properties = @{ displayName = "sap-api-key"; secret = $true
                    keyVault = @{ secretIdentifier = "$($kvUri)secrets/sap-api-key" } } } | Out-Null
Write-Host "Named value sap-api-key -> Key Vault (no copy of the secret in APIM)"

# Typed API: one read-only operation
Invoke-Arm "put" "$base/apis/sap-vendor?api-version=$ApimApi" @{
    properties = @{ displayName = "SAP vendor master (mock)"; path = "sap"; protocols = @("https")
                    serviceUrl = "https://$sapHost/api"; subscriptionRequired = $true } } | Out-Null
Invoke-Arm "put" "$base/apis/sap-vendor/operations/get-vendor?api-version=$ApimApi" @{
    properties = @{ displayName = "Get vendor"; method = "GET"; urlTemplate = "/vendors/{vendorId}"
                    templateParameters = @(@{ name = "vendorId"; type = "string"; required = $true }) } } | Out-Null

$policy = @'
<policies>
  <inbound>
    <base />
    <rate-limit calls="60" renewal-period="60" />
    <set-header name="x-sap-api-key" exists-action="override"><value>{{sap-api-key}}</value></set-header>
  </inbound>
  <backend>
    <forward-request timeout="10" />
  </backend>
  <outbound>
    <base />
    <set-header name="x-powered-by" exists-action="delete" />
  </outbound>
  <on-error><base /></on-error>
</policies>
'@
Invoke-Arm "put" "$base/apis/sap-vendor/policies/policy?api-version=$ApimApi" @{
    properties = @{ format = "rawxml"; value = $policy } } | Out-Null
Write-Host "API sap-vendor: GET /sap/vendors/{vendorId}; rate limit 60/min; 10 s backend timeout; SAP key injected"

# Subscription scoped to this API only; its key goes straight into Key Vault
Invoke-Arm "put" "$base/subscriptions/contract-agents?api-version=$ApimApi" @{
    properties = @{ displayName = "contract-agents"; scope = "$apimId/apis/sap-vendor"; state = "active" } } | Out-Null
$keys = Invoke-Arm "post" "$base/subscriptions/contract-agents/listSecrets?api-version=$ApimApi" $null | ConvertFrom-Json
$tmp = New-TemporaryFile
$keys.primaryKey | Set-Content -NoNewline $tmp
Invoke-Az keyvault secret set --vault-name $KV -n apim-subscription-key --file $tmp -o none | Out-Null
Remove-Item $tmp
Write-Host "Subscription key stored in Key Vault as apim-subscription-key (never displayed)"

# ---------------------------------------------------------------- 4. Tests: the allowed path, and the two forbidden ones
Write-Host "`n== Tests" -ForegroundColor Cyan
$gw = "https://$APIM.azure-api.net/sap/vendors"
function Get-Status($Url, $Headers) {
    try { (Invoke-WebRequest -Uri $Url -Headers $Headers -SkipHttpErrorCheck -TimeoutSec 60).StatusCode } catch { "error: $($_.Exception.Message)" }
}
$subKey = az keyvault secret show --vault-name $KV -n apim-subscription-key --query value -o tsv
Start-Sleep -Seconds 20
Write-Host ("Through APIM with subscription key  : {0}   (expect 200)" -f (Get-Status "$gw/V1A2B3C" @{ "Ocp-Apim-Subscription-Key" = $subKey }))
Write-Host ("Through APIM without a key          : {0}   (expect 401)" -f (Get-Status "$gw/V1A2B3C" @{}))
Write-Host ("Straight to mock SAP, no SAP key    : {0}   (expect 401)" -f (Get-Status "https://$sapHost/api/vendors/V1A2B3C" @{}))
Write-Host "`nFrom the laptop: python -m agents.tools.vendor V1A2B3C" -ForegroundColor Green
