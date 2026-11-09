# Hop-by-hop health check for the event-driven ingestion path (ADR-0018).
# Run on the laptop (Windows PowerShell or pwsh), signed in with az login.
# Cloud Shell cannot query Application Insights, so step 4 needs the laptop.
#   .\eval\check_ingestion.ps1            # last 2 hours
#   .\eval\check_ingestion.ps1 -Hours 24

param([int]$Hours = 2)
. "$PSScriptRoot/../infra/config.ps1"
$ErrorActionPreference = "Continue"   # report every hop even if one check fails

function Decode-Message($content) {
    try { $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($content)) } catch { $text = $content }
    if ($text -match '"url"\s*:\s*"([^"]+)"') { return $Matches[1].Split("/")[-1] }
    return "(unreadable) " + $text.Substring(0, [Math]::Min(40, $text.Length))
}

Write-Host "`n== 1. Event Grid (last $Hours h): published -> matched by filter -> delivered to queue" -ForegroundColor Cyan
$topicId = az eventgrid system-topic show -g $RG -n $EGT --query id -o tsv
az monitor metrics list --resource $topicId --interval PT1H --aggregation Total -o table `
    --offset "$($Hours)h" --metric PublishSuccessCount MatchedEventCount DeliverySuccessCount DeliveryAttemptFailCount DeadLetteredCount 2>$null

Write-Host "`n== 2. Queues" -ForegroundColor Cyan
foreach ($q in "ingest", "ingest-poison") {
    $msgs = az storage message peek --queue-name $q --account-name $FNSA --auth-mode login --num-messages 32 --only-show-errors -o json | ConvertFrom-Json
    Write-Host ("{0,-14} {1} message(s)" -f $q, @($msgs).Count)
    foreach ($m in @($msgs)) { if ($m) { Write-Host "   - $(Decode-Message $m.content)  (dequeued $($m.dequeueCount)x)" } }
}

Write-Host "`n== 3. Dead letter (Event Grid could not reach the queue)" -ForegroundColor Cyan
$dl = az storage fs file list -f deadletter --account-name $SA --auth-mode login --query "[].name" -o tsv 2>$null
if ($dl) { $dl | Select-Object -First 10 } else { Write-Host "empty" }

Write-Host "`n== 4. Function outcomes (last $Hours h)" -ForegroundColor Cyan
az extension add -n application-insights --only-show-errors 2>$null
$kql = "requests | where timestamp > ago($($Hours)h) | summarize runs=count(), failed=countif(success == false), p50_s=round(percentile(duration, 50)/1000, 1), p95_s=round(percentile(duration, 95)/1000, 1)"
az monitor app-insights query --app $FN -g $RG --analytics-query $kql --query "tables[0].rows[0]" -o tsv
Write-Host "(runs, failed, p50 seconds, p95 seconds)"

Write-Host "`n== 5. Distinct failure reasons (last $Hours h)" -ForegroundColor Cyan
$kql = "exceptions | where timestamp > ago($($Hours)h) | extend reason=tostring(split(innermostMessage, '\n')[2]) | summarize n=count() by reason | order by n desc | take 5"
az monitor app-insights query --app $FN -g $RG --analytics-query $kql --query "tables[0].rows[]" -o tsv
