# Phase 5b: raise the embedding deployment's rate limit; keep the chat model's guardrail
# ADR-0014 revision: capacity is set per workload, not one number for every deployment.
# GlobalStandard capacity is a rate limit, not a reservation: raising it costs nothing by itself.
# Run: pwsh ./infra/03b-embedding-capacity.ps1   (safe to re-run)

. "$PSScriptRoot/config.ps1"
$EmbedCapacity = 200   # thousand tokens per minute; the pipeline paces itself at 180K (EMBED_TPM)

Write-Host "`n== Raising text-embedding-3-large to $EmbedCapacity K TPM" -ForegroundColor Cyan
az cognitiveservices account deployment create -g $RG -n $AOAI `
    --deployment-name text-embedding-3-large --model-name text-embedding-3-large `
    --model-version 1 --model-format OpenAI --sku-name GlobalStandard --sku-capacity $EmbedCapacity -o none

az cognitiveservices account deployment list -g $RG -n $AOAI `
    --query "[].{name:name, sku:sku.name, capacityK_TPM:sku.capacity}" -o table
Write-Host "gpt-5.4-mini stays at 50K TPM: it is the deployment an agent loop could run away with."
