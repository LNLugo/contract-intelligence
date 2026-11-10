# Cost control for the only hourly-billed resource (cost log rule 1).
# A stopped Flexible Server bills storage only. Azure restarts a stopped server automatically
# after 7 days, so stop it again if it is not in use.
#   pwsh ./infra/06b-postgres-stop-start.ps1 -Action stop
#   pwsh ./infra/06b-postgres-stop-start.ps1 -Action start

param([ValidateSet("stop", "start", "status")][string]$Action = "status")
. "$PSScriptRoot/config.ps1"
if ($Action -ne "status") { az postgres flexible-server $Action -g $RG -n $PG -o none }
az postgres flexible-server show -g $RG -n $PG --query "{server:name, state:state}" -o table
