# Phase 2b: move Document Intelligence from F0 (2 pages per document) to S0 (pay per page)
# ADR-0015. Run: pwsh ./infra/02b-document-intelligence-s0.ps1   (safe to re-run)

. "$PSScriptRoot/config.ps1"

Write-Host "`n== Current tier" -ForegroundColor Cyan
$sku = az cognitiveservices account show -n $DI -g $RG --query sku.name -o tsv
Write-Host "$DI is on $sku"

if ($sku -ne "S0") {
    Write-Host "`n== Upgrading to S0" -ForegroundColor Cyan
    az cognitiveservices account update -n $DI -g $RG --sku S0 -o none
    $sku = az cognitiveservices account show -n $DI -g $RG --query sku.name -o tsv
    Write-Host "$DI is now on $sku"
} else {
    Write-Host "Already S0, nothing to do"
}

Write-Host "`n== Settings still enforced" -ForegroundColor Cyan
az cognitiveservices account show -n $DI -g $RG `
    --query "{sku:sku.name, keysDisabled:properties.disableLocalAuth, subdomain:properties.customSubDomainName}" -o table
