# Phase 9a: let GitHub Actions push images to ACR without any stored secret (ADR-0025)
# ACR Tasks (cloud build) are not permitted on this subscription, so images are built in GitHub Actions.
#   pwsh ./infra/09a-github-oidc.ps1
# Creates a user-assigned managed identity that trusts ONE thing (GitHub OIDC tokens for pushes to main
# of LNLugo/contract-intelligence) and can do ONE thing (AcrPush on this registry).
param([string]$Repo = "LNLugo/contract-intelligence", [string]$Branch = "main")
. "$PSScriptRoot/guard.ps1"   # Cloud Shell only: stops before any az command
. "$PSScriptRoot/config.ps1"
Assert-ResourceSubscription
$UAMI = "id-ci-github-2416"

Write-Host "== Managed identity for GitHub Actions" -ForegroundColor Cyan
az identity show -n $UAMI -g $RG -o none 2>$null
if ($LASTEXITCODE -ne 0) { Invoke-Az identity create -n $UAMI -g $RG -l $LOC -o none | Out-Null; Write-Host "  + $UAMI" }
else { Write-Host "  = $UAMI" }
$id = (Invoke-Az identity show -n $UAMI -g $RG -o json | Out-String) | ConvertFrom-Json

Write-Host "`n== Federated credential: trust only $Repo, branch $Branch" -ForegroundColor Cyan
# GitHub's OIDC subject uses immutable IDs: repo:OWNER@OWNER_ID/REPO@REPO_ID:ref:refs/heads/BRANCH.
# IDs survive renames, so a deleted-and-recreated account or repo with the same name cannot match
# (build log, 2026-11-12: the name-only subject was rejected with AADSTS700213).
$gh = Invoke-RestMethod "https://api.github.com/repos/$Repo"
$subject = "repo:$($gh.owner.login)@$($gh.owner.id)/$($gh.name)@$($gh.id):ref:refs/heads/$Branch"
$fc = az identity federated-credential show -n github-main --identity-name $UAMI -g $RG -o json 2>$null | ConvertFrom-Json
if ($null -eq $fc) {
    Invoke-Az identity federated-credential create -n github-main --identity-name $UAMI -g $RG `
        --issuer "https://token.actions.githubusercontent.com" --subject $subject `
        --audiences "api://AzureADTokenExchange" -o none | Out-Null
    Write-Host "  + subject $subject"
} elseif ($fc.subject -ne $subject) {
    Invoke-Az identity federated-credential update -n github-main --identity-name $UAMI -g $RG `
        --issuer "https://token.actions.githubusercontent.com" --subject $subject `
        --audiences "api://AzureADTokenExchange" -o none | Out-Null
    Write-Host "  ~ subject $($fc.subject) -> $subject"
} else { Write-Host "  = subject $subject" }

Write-Host "`n== Role: AcrPush on $ACR only" -ForegroundColor Cyan
$acrId = (Invoke-Az acr show -n $ACR -g $RG --query id -o tsv | Out-String).Trim()
Grant-RoleToPrincipal $id.principalId "AcrPush" $acrId | Out-Null

$acct = (Invoke-Az account show -o json | Out-String) | ConvertFrom-Json
Write-Host "`nDone. On the LAPTOP (repo root), store these as GitHub Actions secrets (identifiers, kept out of logs):"
Write-Host "  gh secret set AZURE_CLIENT_ID --body $($id.clientId)"
Write-Host "  gh secret set AZURE_TENANT_ID --body $($acct.tenantId)"
Write-Host "  gh secret set AZURE_SUBSCRIPTION_ID --body $($acct.id)"
