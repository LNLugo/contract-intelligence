# Phase 8: identity for the API (ADR-0023, ADR-0024)
# Runs while signed in to the IDENTITY tenant (separate from the tenant that holds the Azure resources):
#   az login --tenant <identity-domain> --allow-no-subscriptions --use-device-code
#
# Creates, idempotently:
#   - API app registration "ci-contracts-api" with app roles Contracts.Legal and Contracts.Procurement,
#     identifier URI api://<appId>, v2 tokens; its service principal requires role assignment, so Entra
#     refuses to issue a token to anyone without a role (first layer; the API checks again)
#   - three test client apps (legal, procurement, norole) for automated tests (client credentials flow)
#   - three test users (legal, procurement, norole) for interactive sign-in later (review app)
# Secrets (client secrets, initial user passwords) are generated in memory and written straight to
# Key Vault in the RESOURCE tenant. They are never printed, stored in files or committed.
#
# Usage (Cloud Shell, pwsh):
#   pwsh ./infra/08-identity.ps1 -ResourceTenant <stevens-tenant-id> -IdentityDomain ciidentitydev2416.onmicrosoft.com
param(
    [Parameter(Mandatory)] [string] $ResourceTenant,
    [Parameter(Mandatory)] [string] $IdentityDomain
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot/config.ps1"

$GRAPH = "https://graph.microsoft.com/v1.0"
$API_NAME = "ci-contracts-api"
$ROLES = @(
    @{ value = "Contracts.Legal";       displayName = "Contracts: legal";       group = "grp-legal" }
    @{ value = "Contracts.Procurement"; displayName = "Contracts: procurement"; group = "grp-procurement" }
)
$TESTS = @(
    @{ name = "legal";       role = "Contracts.Legal" }
    @{ name = "procurement"; role = "Contracts.Procurement" }
    @{ name = "norole";      role = $null }
)

function Graph($Method, $Path, $Body = $null) {
    # New directory objects take seconds to replicate: a service principal or role assignment created
    # right after its app can fail with "does not exist". Retry those; stop on anything else.
    for ($i = 1; ; $i++) {
        try { $out = Invoke-Arm $Method "$GRAPH$Path" $Body; break }
        catch {
            $transient = $_.Exception.Message -match "does not exist|does not reference|ResourceNotFound|Request_BadRequest.*not found"
            if (-not $transient -or $i -ge 6) { throw }
            Write-Host "  (directory replication, retry $i in 10 s)"; Start-Sleep -Seconds 10
        }
    }
    if ([string]::IsNullOrWhiteSpace($out)) { return $null }
    return ($out | ConvertFrom-Json)
}
function Q($s) { [uri]::EscapeDataString($s) }

function New-Secret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).Replace('+', 'x').Replace('/', 'y') + "aA1!"
}

# ---- 0. Preconditions: right tenant, and Key Vault reachable BEFORE anything is created ----
$org = Graph GET "/organization?`$select=id,verifiedDomains"
$domains = @($org.value[0].verifiedDomains.name)
if ($domains -notcontains $IdentityDomain) {
    throw "Signed in to the wrong tenant (domains: $($domains -join ', ')). Run: az login --tenant $IdentityDomain --allow-no-subscriptions --use-device-code"
}
$IDENTITY_TENANT = $org.value[0].id
Write-Host "Identity tenant: $IdentityDomain"

$kvToken = az account get-access-token --tenant $ResourceTenant --resource https://vault.azure.net --query accessToken -o tsv 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($kvToken)) {
    throw "Cannot get a Key Vault token for the resource tenant. Run 'az login' (Stevens) once, then 'az login --tenant $IdentityDomain --allow-no-subscriptions --use-device-code', and retry."
}
$KV_URL = "https://$KV.vault.azure.net"
function Set-KvSecret($Name, $Value, $ContentType) {
    $body = @{ value = $Value; contentType = $ContentType } | ConvertTo-Json
    try {
        Invoke-RestMethod -Method Put -Uri "$KV_URL/secrets/$($Name)?api-version=7.4" -ContentType "application/json" `
            -Headers @{ Authorization = "Bearer $kvToken" } -Body $body | Out-Null
    } catch { throw "Writing secret '$Name' to $KV failed: $($_.Exception.Message)" }
    Write-Host "  secret $Name -> $KV"
}
# Probe write access with a non-secret value before creating anything
Set-KvSecret "ci-identity-probe" "ok" "probe"

# ---- 1. API app registration with app roles ----
Write-Host "`n== API app registration"
$api = (Graph GET "/applications?`$filter=$(Q "displayName eq '$API_NAME'")").value | Select-Object -First 1
if ($null -eq $api) {
    $appRoles = $ROLES | ForEach-Object {
        @{ id = [guid]::NewGuid().ToString(); value = $_.value; displayName = $_.displayName
           description = "Read contracts entitled to $($_.group)"; allowedMemberTypes = @("User", "Application"); isEnabled = $true }
    }
    $api = Graph POST "/applications" @{
        displayName = $API_NAME; signInAudience = "AzureADMyOrg"
        api = @{ requestedAccessTokenVersion = 2 }; appRoles = @($appRoles)
    }
    Write-Host "  + $API_NAME"
} else { Write-Host "  = $API_NAME (already)" }
$missing = $ROLES | Where-Object { $api.appRoles.value -notcontains $_.value }
if ($missing) { throw "App roles missing on existing $API_NAME : $($missing.value -join ', '). Fix in the portal or delete the app and rerun." }
$AUDIENCE = "api://$($api.appId)"
if ($api.identifierUris -notcontains $AUDIENCE) {
    Graph PATCH "/applications/$($api.id)" @{ identifierUris = @($AUDIENCE) } | Out-Null
    Write-Host "  + identifier URI $AUDIENCE"
}
$roleId = @{}; foreach ($r in $api.appRoles) { $roleId[$r.value] = $r.id }

function Get-Sp($AppId) {
    $sp = (Graph GET "/servicePrincipals?`$filter=$(Q "appId eq '$AppId'")").value | Select-Object -First 1
    if ($null -eq $sp) { $sp = Graph POST "/servicePrincipals" @{ appId = $AppId } }
    return $sp
}
$apiSp = Get-Sp $api.appId
Graph PATCH "/servicePrincipals/$($apiSp.id)" @{ appRoleAssignmentRequired = $true } | Out-Null
Write-Host "  = service principal requires role assignment (no role, no token)"

$assigned = @((Graph GET "/servicePrincipals/$($apiSp.id)/appRoleAssignedTo").value)
function Grant-AppRole($PrincipalId, $Role, $Label) {
    if ($null -eq $Role) { Write-Host "  = $Label has no role (on purpose)"; return }
    if ($assigned | Where-Object { $_.principalId -eq $PrincipalId -and $_.appRoleId -eq $roleId[$Role] }) {
        Write-Host "  = $Label -> $Role (already)"; return
    }
    Graph POST "/servicePrincipals/$($apiSp.id)/appRoleAssignedTo" @{
        principalId = $PrincipalId; resourceId = $apiSp.id; appRoleId = $roleId[$Role] } | Out-Null
    Write-Host "  + $Label -> $Role"
}

# ---- 2. Test client apps (automated tests, client credentials flow) ----
Write-Host "`n== Test client apps"
$clients = @{}
foreach ($t in $TESTS) {
    $name = "ci-test-$($t.name)"
    $app = (Graph GET "/applications?`$filter=$(Q "displayName eq '$name'")").value | Select-Object -First 1
    if ($null -eq $app) { $app = Graph POST "/applications" @{ displayName = $name; signInAudience = "AzureADMyOrg" }; Write-Host "  + $name" }
    else { Write-Host "  = $name (already)" }
    $sp = Get-Sp $app.appId
    Grant-AppRole $sp.id $t.role $name
    # Rotate: remove earlier test secrets, add a new one (90 days), store it in Key Vault
    foreach ($c in @($app.passwordCredentials | Where-Object { $_.displayName -eq "ci-tests" })) {
        Graph POST "/applications/$($app.id)/removePassword" @{ keyId = $c.keyId } | Out-Null
    }
    $cred = Graph POST "/applications/$($app.id)/addPassword" @{
        passwordCredential = @{ displayName = "ci-tests"; endDateTime = (Get-Date).ToUniversalTime().AddDays(90).ToString("o") } }
    Set-KvSecret "ci-test-$($t.name)-secret" $cred.secretText "client secret, $name"
    $cred = $null
    $clients[$t.name] = $app.appId
}

# ---- 3. Test users (interactive sign-in later; MFA applies) ----
Write-Host "`n== Test users"
foreach ($t in $TESTS) {
    $upn = "ci-$($t.name)@$IdentityDomain"
    $user = (Graph GET "/users?`$filter=$(Q "userPrincipalName eq '$upn'")").value | Select-Object -First 1
    if ($null -eq $user) {
        $pw = New-Secret
        $user = Graph POST "/users" @{
            accountEnabled = $true; displayName = "CI test $($t.name)"; mailNickname = "ci-$($t.name)"
            userPrincipalName = $upn; passwordProfile = @{ forceChangePasswordNextSignIn = $true; password = $pw } }
        Set-KvSecret "ci-user-$($t.name)-password" $pw "initial password (change at first sign-in), $upn"
        $pw = $null
        Write-Host "  + $upn"
    } else { Write-Host "  = $upn (already; password not reset)" }
    Grant-AppRole $user.id $t.role $upn
}

# ---- 4. Non-secret settings the API and tests need ----
$settings = @{
    tenantId = $IDENTITY_TENANT; issuer = "https://login.microsoftonline.com/$IDENTITY_TENANT/v2.0"
    audience = $api.appId; scope = "$AUDIENCE/.default"
    roleToGroup = @{ "Contracts.Legal" = "grp-legal"; "Contracts.Procurement" = "grp-procurement" }
    clients = $clients
} | ConvertTo-Json -Depth 5
Set-KvSecret "ci-identity-config" $settings "identity settings (not secret)"

Write-Host "`nDone. Settings (not secret, keep out of the public repo):"
Write-Host $settings
Write-Host "`nVerify: the norole client must be REFUSED a token by Entra (AADSTS501051), the other two get one with a 'roles' claim."
