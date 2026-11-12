# Cost control for the only hourly-billed resource (cost log rule 1).
# A stopped Flexible Server bills storage only. Azure restarts a stopped server automatically
# after 7 days, so stop it again if it is not in use.
#   pwsh ./infra/06b-postgres-stop-start.ps1 -Action stop
#   pwsh ./infra/06b-postgres-stop-start.ps1 -Action start
#   pwsh ./infra/06b-postgres-stop-start.ps1            (status)
# Fails fast on the wrong subscription; asking for the state it is already in is success.

param([ValidateSet("stop", "start", "status")][string]$Action = "status")
. "$PSScriptRoot/config.ps1"
Assert-ResourceSubscription

function Get-State { (Invoke-Az postgres flexible-server show -g $RG -n $PG --query state -o tsv | Out-String).Trim() }

$state = Get-State
$target = @{ stop = "Stopped"; start = "Ready" }[$Action]
if ($Action -eq "status") {
    Write-Host "$PG : $state"
} elseif ($state -eq $target) {
    Write-Host "$PG : already $state"
} else {
    Write-Host "$PG : $state -> $Action ..."
    Invoke-Az postgres flexible-server $Action -g $RG -n $PG -o none | Out-Null
    Write-Host "$PG : $(Get-State)"
    if ($Action -eq "stop") { Write-Host "Azure starts a stopped server again after 7 days; stop it again if unused." }
}
