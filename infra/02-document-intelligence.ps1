# Phase 2: Document Intelligence, keyless, with the same submit-and-poll pattern the Function will use
# ADRs: 0004 (submit + poll), 0013 (no keys)
# Run: pwsh ./infra/02-document-intelligence.ps1   (safe to re-run)

. "$PSScriptRoot/config.ps1"

# 1. Resource: F0 (free) tier. Free tier analyzes only the first 2 pages of each document.
Write-Host "`n== Document Intelligence $DI" -ForegroundColor Cyan
$exists = az cognitiveservices account list -g $RG --query "[?name=='$DI'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    az cognitiveservices account create -n $DI -g $RG -l $LOC `
        --kind FormRecognizer --sku F0 --custom-domain $DI --yes -o none
    Write-Host "Created (F0)"
} else {
    Write-Host "Already exists"
}

# 2. Data-plane role and keys off
Write-Host "`n== Role assignment" -ForegroundColor Cyan
$scope = az cognitiveservices account show -n $DI -g $RG --query id -o tsv
Grant-Role "Cognitive Services User" $scope

az resource update -g $RG -n $DI --resource-type Microsoft.CognitiveServices/accounts `
    --set properties.disableLocalAuth=true -o none
Write-Host "Keys disabled"

# 3. Smoke test: prebuilt-layout on a public sample PDF, submit then poll (the async pattern)
Write-Host "`n== Smoke test: submit" -ForegroundColor Cyan
$token   = az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv
$headers = @{ Authorization = "Bearer $token" }
$ep      = "https://$DI.cognitiveservices.azure.com/documentintelligence/documentModels/prebuilt-layout:analyze?api-version=2024-11-30"
$body    = @{ urlSource = "https://raw.githubusercontent.com/Azure-Samples/cognitive-services-REST-api-samples/master/curl/form-recognizer/sample-layout.pdf" } | ConvertTo-Json

$submit = Invoke-WebRequest -Method Post -Uri $ep -Headers $headers -ContentType "application/json" -Body $body
$opUrl  = $submit.Headers["Operation-Location"] | Select-Object -First 1
Write-Host "HTTP $($submit.StatusCode) (expect 202). Operation: $opUrl"

Write-Host "`n== Smoke test: poll" -ForegroundColor Cyan
$sw = [Diagnostics.Stopwatch]::StartNew()
do {
    Start-Sleep -Seconds 2
    $result = Invoke-RestMethod -Uri $opUrl -Headers $headers
    Write-Host "  status: $($result.status)"
} while ($result.status -in @("notStarted", "running") -and $sw.Elapsed.TotalSeconds -lt 120)

if ($result.status -ne "succeeded") { throw "Analysis ended with status $($result.status)" }

$a = $result.analyzeResult
Write-Host "`nSucceeded in $([int]$sw.Elapsed.TotalSeconds) s"
Write-Host "Pages: $($a.pages.Count)   Paragraphs: $($a.paragraphs.Count)   Tables: $($a.tables.Count)"
Write-Host "Paragraph roles found: $(($a.paragraphs | Where-Object role | Select-Object -ExpandProperty role -Unique) -join ', ')"
Write-Host "First 300 characters of content:"
Write-Host $a.content.Substring(0, [Math]::Min(300, $a.content.Length))
