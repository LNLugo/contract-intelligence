# Phase 3: model deployments with keyless (Entra ID) access
# ADRs: 0003 (region and hosting), 0013 (no keys), 0014 (deployment type and model roles)
# Run in Azure Cloud Shell (PowerShell) or locally with the Azure CLI signed in.
# Safe to re-run: each step checks or overwrites rather than duplicating.

$ErrorActionPreference = "Stop"

$RG       = "rg-ci-dev"
$AOAI     = "aoai-ci-dev-2416"
$Capacity = 50   # thousand tokens per minute per deployment: a cost guardrail (ADR-0014)

$Deployments = @(
    @{ Name = "text-embedding-3-large"; Model = "text-embedding-3-large"; Version = "1" },
    @{ Name = "gpt-5.4-mini";           Model = "gpt-5.4-mini";           Version = "2026-03-17" }
)

Write-Host "`n== Existing deployments" -ForegroundColor Cyan
az cognitiveservices account deployment list -g $RG -n $AOAI -o table

# 1. Custom subdomain: required for Entra ID token auth (keys work without it, tokens do not)
Write-Host "`n== Custom subdomain" -ForegroundColor Cyan
$domain = az cognitiveservices account show -g $RG -n $AOAI --query "properties.customSubDomainName" -o tsv
if ([string]::IsNullOrEmpty($domain)) {
    az cognitiveservices account update -g $RG -n $AOAI --custom-domain $AOAI -o none
    Write-Host "Set custom subdomain: $AOAI"
} else {
    Write-Host "Already set: $domain"
}

# 2. Model deployments (GlobalStandard: the only type offered in Canada Central, ADR-0014)
foreach ($d in $Deployments) {
    Write-Host "`n== Deploying $($d.Name)" -ForegroundColor Cyan
    az cognitiveservices account deployment create -g $RG -n $AOAI `
        --deployment-name $d.Name --model-name $d.Model --model-version $d.Version `
        --model-format OpenAI --sku-name GlobalStandard --sku-capacity $Capacity -o none
    Write-Host "Done"
}

# 3. Data-plane role for the signed-in user (least privilege: call models, not manage them)
Write-Host "`n== Role assignment" -ForegroundColor Cyan
$me    = az ad signed-in-user show --query id -o tsv
$scope = az cognitiveservices account show -g $RG -n $AOAI --query id -o tsv
$existing = az role assignment list --assignee $me --scope $scope --role "Cognitive Services OpenAI User" --query "[].id" -o tsv
if ([string]::IsNullOrEmpty($existing)) {
    az role assignment create --assignee $me --role "Cognitive Services OpenAI User" --scope $scope -o none
    Write-Host "Assigned. Waiting 120 seconds for it to take effect..."
    Start-Sleep -Seconds 120
} else {
    Write-Host "Already assigned"
}

# 4. Turn off API keys: from here on, only Entra tokens work (ADR-0013)
Write-Host "`n== Disabling local (key) auth" -ForegroundColor Cyan
az resource update -g $RG -n $AOAI --resource-type Microsoft.CognitiveServices/accounts `
    --set properties.disableLocalAuth=true -o none
Write-Host "Keys disabled"

# 5. Smoke test with a token, not a key
Write-Host "`n== Smoke test" -ForegroundColor Cyan
$token   = az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv
$headers = @{ Authorization = "Bearer $token" }
$ep      = "https://$AOAI.openai.azure.com/openai/v1"

$emb = Invoke-RestMethod -Method Post -Uri "$ep/embeddings" -Headers $headers -ContentType "application/json" `
    -Body (@{ model = "text-embedding-3-large"; input = "limitation of liability" } | ConvertTo-Json)
Write-Host "Embedding dimensions: $($emb.data[0].embedding.Count)   (expect 3072)"

$chat = Invoke-RestMethod -Method Post -Uri "$ep/chat/completions" -Headers $headers -ContentType "application/json" `
    -Body (@{ model = "gpt-5.4-mini"; messages = @(@{ role = "user"; content = "In one sentence, what is an indemnification clause?" }) } | ConvertTo-Json -Depth 5)
Write-Host "Chat: $($chat.choices[0].message.content)"
Write-Host "Tokens used: $($chat.usage.total_tokens)"

Write-Host "`n== Final deployments" -ForegroundColor Cyan
az cognitiveservices account deployment list -g $RG -n $AOAI `
    --query "[].{name:name, model:properties.model.name, sku:sku.name, capacity:sku.capacity}" -o table
