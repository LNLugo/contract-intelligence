# Stops an infra script unless it runs in Azure Cloud Shell (PowerShell).
# Loaded first by every infra/0*.ps1 script (build log, 2026-11-25). Not by config.ps1:
# eval/check_ingestion.ps1 loads config.ps1 and must run on the laptop.
# Why: scripts run by mistake in Windows PowerShell on the laptop failed part-way,
# against whatever subscription the laptop was signed in to.
# A deliberate local run with PowerShell 7 and the Azure CLI: set $env:CI_INFRA_LOCAL = "1" first.

$inCloudShell = [bool]($env:AZUREPS_HOST_ENVIRONMENT -like "cloud-shell*" -or $env:ACC_CLOUD)

if ($PSVersionTable.PSEdition -ne "Core") {
    throw "Windows PowerShell $($PSVersionTable.PSVersion) is not supported. Run this in Azure Cloud Shell (PowerShell)."
}
if (-not $inCloudShell -and $env:CI_INFRA_LOCAL -ne "1") {
    throw "Run this in Azure Cloud Shell (PowerShell), not on the laptop. For a deliberate local run with PowerShell 7, set `$env:CI_INFRA_LOCAL = '1' first."
}
