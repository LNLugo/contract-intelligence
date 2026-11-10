# Phase 6: PostgreSQL Flexible Server for the governed clause taxonomy (ADR-0011)
# Entra ID authentication only (password login disabled), firewall open to one client IP,
# smallest Burstable tier. First resource billed hourly: stop it when not in use (infra/06b).
# Run in Cloud Shell:  pwsh ./infra/06-postgres.ps1 -ClientIp <your laptop's public IP>
# Safe to re-run. Every az call stops the script on failure (Invoke-Az).

param([Parameter(Mandatory = $true)][string]$ClientIp)
. "$PSScriptRoot/config.ps1"

Write-Host "`n== Provider" -ForegroundColor Cyan
Invoke-Az provider register -n Microsoft.DBforPostgreSQL --wait -o none | Out-Null
Write-Host "Registered"

# Option names changed across CLI versions; pick the ones this installation knows
$entraFlag  = if (Test-AzOption "postgres flexible-server create" "--microsoft-entra-auth") { "--microsoft-entra-auth" } else { "--active-directory-auth" }
$adminGroup = if (Test-AzOption "postgres flexible-server" "microsoft-entra-admin") { "microsoft-entra-admin" } else { "ad-admin" }
Write-Host "CLI uses: $entraFlag, $adminGroup"

# 1. Server: Burstable B1ms, PostgreSQL 16, Entra-only authentication
Write-Host "`n== Server $PG" -ForegroundColor Cyan
$exists = az postgres flexible-server list -g $RG --query "[?name=='$PG'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    Write-Host "Creating (5 to 10 minutes)..."
    Invoke-Az postgres flexible-server create -g $RG -n $PG -l $LOC `
        --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 `
        $entraFlag Enabled --password-auth Disabled `
        --public-access None --yes -o none | Out-Null
    Write-Host "Created"
} else { Write-Host "Already exists" }
Invoke-Az postgres flexible-server show -g $RG -n $PG `
    --query "{state:state, version:version, sku:sku.name, entraAuth:authConfig.activeDirectoryAuth, passwordAuth:authConfig.passwordAuth}" -o table

# 2. Entra admin: me (the Function and agent identities get their own least-privilege roles later)
Write-Host "`n== Entra admin" -ForegroundColor Cyan
$me  = az ad signed-in-user show --query id -o tsv
$upn = az ad signed-in-user show --query userPrincipalName -o tsv
$admins = az postgres flexible-server $adminGroup list -g $RG -s $PG --query "[?objectId=='$me'].principalName" -o tsv 2>$null
if ([string]::IsNullOrEmpty($admins)) {
    Invoke-Az postgres flexible-server $adminGroup create -g $RG -s $PG --display-name $upn --object-id $me --type User -o none | Out-Null
    Write-Host "Entra admin set: $upn"
} else { Write-Host "Entra admin already set: $admins" }

# 3. Firewall: one client IP, nothing else (private endpoint in phase 13)
Write-Host "`n== Firewall" -ForegroundColor Cyan
Invoke-Az postgres flexible-server firewall-rule create -g $RG --server-name $PG --name laptop `
    --start-ip-address $ClientIp --end-ip-address $ClientIp -o none | Out-Null
Invoke-Az postgres flexible-server firewall-rule list -g $RG --server-name $PG `
    --query "[].{rule:name, from:startIpAddress, to:endIpAddress}" -o table

# 4. Database
Write-Host "`n== Database $PGDB" -ForegroundColor Cyan
$dbs = az postgres flexible-server db list -g $RG --server-name $PG --query "[?name=='$PGDB'].name" -o tsv
if ([string]::IsNullOrEmpty($dbs)) {
    Invoke-Az postgres flexible-server db create -g $RG --server-name $PG --name $PGDB -o none | Out-Null
    Write-Host "Created $PGDB"
} else { Write-Host "$PGDB already exists" }

Write-Host "`nReady: $PG.postgres.database.azure.com / $PGDB  (user $upn, password = Entra access token)" -ForegroundColor Green
Write-Host "Next, from the laptop: python taxonomy/seed_from_cuad.py --cuad-root <folder containing CUAD_v1>"
