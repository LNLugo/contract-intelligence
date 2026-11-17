# Separate chat deployment for evaluation runs (ADR-0014 per-workload capacity, ADR-0022, ADR-0027)
# Same model and version as the app's deployment, higher rate limit, its own name. Evaluation
# traffic never competes with interactive users, and the app's 50K TPM runaway guardrail stays.
# GlobalStandard capacity is a rate limit, not a reservation: this costs nothing until used.
# Run: pwsh ./infra/03c-eval-deployment.ps1   (safe to re-run)
# Use:  $env:CHAT_DEPLOYMENT = "gpt-5.4-mini-eval"   before an evaluation run

. "$PSScriptRoot/config.ps1"
Assert-ResourceSubscription
$EvalDeployment = "gpt-5.4-mini-eval"
$EvalCapacity   = 200   # thousand tokens per minute

# Same version as the app deployment, read rather than hard-coded, so the two cannot drift apart
$version = (Invoke-Az cognitiveservices account deployment show -g $RG -n $AOAI --deployment-name gpt-5.4-mini `
    --query properties.model.version -o tsv | Out-String).Trim()

Write-Host "`n== Deployment $EvalDeployment (gpt-5.4-mini $version, $EvalCapacity K TPM)" -ForegroundColor Cyan
Invoke-Az cognitiveservices account deployment create -g $RG -n $AOAI `
    --deployment-name $EvalDeployment --model-name gpt-5.4-mini --model-version $version `
    --model-format OpenAI --sku-name GlobalStandard --sku-capacity $EvalCapacity -o none | Out-Null

az cognitiveservices account deployment list -g $RG -n $AOAI `
    --query "[].{deployment:name, model:properties.model.name, version:properties.model.version, capacityK_TPM:sku.capacity}" -o table
Write-Host "Use it for evaluation runs only:  `$env:CHAT_DEPLOYMENT = '$EvalDeployment'"
