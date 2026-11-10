# Phase 6: PostgreSQL Flexible Server for the governed clause taxonomy (ADR-0011)
# Entra ID authentication only (password login disabled), firewall open to one client IP,
# smallest Burstable tier. First resource billed hourly: stop it when not in use (infra/06b).
# Run in Cloud Shell:  pwsh ./infra/06-postgres.ps1 -ClientIp <your laptop's public IP>
# Safe to re-run.

param([Parameter(Mandatory = $true)][string]$ClientIp)
. "$PSScriptRoot/config.ps1"

Write-Host "`n== Provider" -ForegroundColor Cyan
az provider register -n Microsoft.DBforPostgreSQL --wait -o none
Write-Host "Registered"

# 1. Server: Burstable B1ms, PostgreSQL 16, Entra-only authentication
Write-Host "`n== Server $PG" -ForegroundColor Cyan
$exists = az postgres flexible-server list -g $RG --query "[?name=='$PG'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    az postgres flexible-server create -g $RG -n $PG -l $LOC `
        --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 `
        --active-directory-auth Enabled --password-auth Disabled `
        --public-access None --yes -o none
    Write-Host "Created (this takes 5 to 10 minutes)"
} else { Write-Host "Already exists" }
az postgres flexible-server show -g $RG -n $PG `
    --query "{state:state, version:version, sku:sku.name, entraAuth:authConfig.activeDirectoryAuth, passwordAuth:authConfig.passwordAuth}" -o table

# 2. Entra admin: me (later the Function and agent identities get their own least-privilege roles)
Write-Host "`n== Entra admin" -ForegroundColor Cyan
$me  = az ad signed-in-user show --query id -o tsv
$upn = az ad signed-in-user show --query userPrincipalName -o tsv
$admins = az postgres flexible-server ad-admin list -g $RG -s $PG --query "[?objectId=='$me'].principalName" -o tsv 2>$null
if ([string]::IsNullOrEmpty($admins)) {
    az postgres flexible-server ad-admin create -g $RG -s $PG --display-name $upn --object-id $me --type User -o none
    Write-Host "Entra admin set: $upn"
} else { Write-Host "Entra admin already set: $admins" }

# 3. Firewall: one client IP, nothing else (private endpoint in phase 13)
Write-Host "`n== Firewall" -ForegroundColor Cyan
az postgres flexible-server firewall-rule create -g $RG -n $PG --rule-name laptop `
    --start-ip-address $ClientIp --end-ip-address $ClientIp -o none
az postgres flexible-server firewall-rule list -g $RG -n $PG --query "[].{rule:name, from:startIpAddress, to:endIpAddress}" -o table

# 4. Database
Write-Host "`n== Database $PGDB" -ForegroundColor Cyan
az postgres flexible-server db create -g $RG -s $PG -d $PGDB -o none
Write-Host "Ready: $PG.postgres.database.azure.com / $PGDB  (user $upn, password = Entra access token)"
Write-Host "Next, from the laptop: python taxonomy/seed_from_cuad.py --cuad-root <folder containing CUAD_v1>" -ForegroundColor Green
