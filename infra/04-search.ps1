# Phase 4: AI Search (Free), keyless, with the chunk index and a security-trimming smoke test
# ADRs: 0006 (hybrid retrieval), 0013 (no keys, group filter), 0016 (tier and vector size)
# Run: pwsh ./infra/04-search.ps1   (safe to re-run; the index definition is overwritten in place)

. "$PSScriptRoot/config.ps1"
$SearchApi = "2024-07-01"

# 1. Service: Free tier, Entra ID only
Write-Host "`n== Search service $SRCH" -ForegroundColor Cyan
$exists = az search service list -g $RG --query "[?name=='$SRCH'].name" -o tsv
if ([string]::IsNullOrEmpty($exists)) {
    az search service create -n $SRCH -g $RG -l $LOC --sku free --disable-local-auth true -o none
    Write-Host "Created (Free, keys disabled)"
} else {
    Write-Host "Already exists"
}
az search service show -n $SRCH -g $RG --query "{sku:sku.name, keysDisabled:disableLocalAuth, status:status}" -o table

# 2. Roles: manage indexes, and read/write documents
Write-Host "`n== Role assignments" -ForegroundColor Cyan
$scope = az search service show -n $SRCH -g $RG --query id -o tsv
Grant-Role "Search Service Contributor" $scope
Grant-Role "Search Index Data Contributor" $scope

$searchToken = az account get-access-token --resource https://search.azure.com --query accessToken -o tsv
$sh = @{ Authorization = "Bearer $searchToken" }
$sep = "https://$SRCH.search.windows.net"

# 3. Index definition: every field traces to an ADR
Write-Host "`n== Index $INDEX" -ForegroundColor Cyan
$index = @{
    name   = $INDEX
    fields = @(
        @{ name = "id";               type = "Edm.String"; key = $true; filterable = $true }
        @{ name = "doc_id";           type = "Edm.String"; filterable = $true }                       # idempotent reprocessing (ADR-0004)
        @{ name = "chunk_index";      type = "Edm.Int32";  filterable = $true; sortable = $true }
        @{ name = "file_name";        type = "Edm.String"; searchable = $true }
        @{ name = "section_heading";  type = "Edm.String"; searchable = $true }                       # from layout roles (ADR-0005)
        @{ name = "content";          type = "Edm.String"; searchable = $true; analyzer = "en.microsoft" }  # BM25 side of hybrid (ADR-0006)
        @{ name = "content_vector";   type = "Collection(Edm.Single)"; searchable = $true; retrievable = $false; stored = $false
           dimensions = $EMBED_DIMS; vectorSearchProfile = "hnsw-cosine" }                            # vector side (ADR-0006, ADR-0016)
        @{ name = "page_start";       type = "Edm.Int32";  filterable = $true }                       # citations
        @{ name = "page_end";         type = "Edm.Int32";  filterable = $true }
        @{ name = "contract_type";    type = "Edm.String"; filterable = $true; facetable = $true }
        @{ name = "vendor_id";        type = "Edm.String"; filterable = $true }                       # join key to system of record (ADR-0010)
        @{ name = "business_unit";    type = "Edm.String"; filterable = $true; facetable = $true }
        @{ name = "allowed_groups";   type = "Collection(Edm.String)"; filterable = $true; retrievable = $false }  # security trimming (ADR-0013)
        @{ name = "clause_categories"; type = "Collection(Edm.String)"; filterable = $true; facetable = $true }    # taxonomy (ADR-0011)
        @{ name = "extraction_version"; type = "Edm.String"; filterable = $true }                     # lineage: which extraction produced this chunk
        @{ name = "ingested_at";      type = "Edm.DateTimeOffset"; filterable = $true; sortable = $true }
    )
    vectorSearch = @{
        algorithms = @(@{ name = "hnsw"; kind = "hnsw"; hnswParameters = @{ metric = "cosine"; m = 4; efConstruction = 400; efSearch = 500 } })
        profiles   = @(@{ name = "hnsw-cosine"; algorithm = "hnsw" })
    }
    semantic = @{
        configurations = @(@{ name = "default"; prioritizedFields = @{
            titleField = @{ fieldName = "section_heading" }
            prioritizedContentFields = @(@{ fieldName = "content" }) } })
    }
}
# Search role assignments can take 5 to 10 minutes to apply, so retry on 403 instead of failing
$indexJson = $index | ConvertTo-Json -Depth 10
for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
        Invoke-RestMethod -Method Put -Uri "$sep/indexes/$($INDEX)?api-version=$SearchApi" -Headers $sh `
            -ContentType "application/json" -Body $indexJson | Out-Null
        Write-Host "Index created or updated"
        break
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ((@(401, 403) -contains $code) -and ($attempt -lt 20)) {
            Write-Host "  HTTP $($code): role not active yet, retrying in 30 s (attempt $attempt of 20)"
            Start-Sleep -Seconds 30
            $searchToken = az account get-access-token --resource https://search.azure.com --query accessToken -o tsv
            $sh = @{ Authorization = "Bearer $searchToken" }
        } else { throw }
    }
}

# 4. Smoke test: three synthetic chunks, two security groups, one hybrid query
Write-Host "`n== Smoke test: embed at $EMBED_DIMS dimensions" -ForegroundColor Cyan
$aoaiToken = az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv
$ah = @{ Authorization = "Bearer $aoaiToken" }
$texts = @(
    "Neither party's aggregate liability under this Agreement shall exceed the fees paid in the twelve months preceding the claim.",
    "Supplier shall indemnify and hold harmless Customer from any third-party claims arising from Supplier's negligence.",
    "Either party may terminate this Agreement upon ninety days written notice to the other party."
)
$emb = Invoke-RestMethod -Method Post -Uri "https://$AOAI.openai.azure.com/openai/v1/embeddings" -Headers $ah `
    -ContentType "application/json" -Body (@{ model = "text-embedding-3-large"; input = $texts; dimensions = $EMBED_DIMS } | ConvertTo-Json)
Write-Host "Vector length: $($emb.data[0].embedding.Count)   (expect $EMBED_DIMS)"

$groups = @(@("grp-legal"), @("grp-legal"), @("grp-procurement"))
$docs = for ($i = 0; $i -lt 3; $i++) {
    @{ "@search.action" = "mergeOrUpload"; id = "smoketest-$i"; doc_id = "smoketest"; chunk_index = $i
       file_name = "smoketest.pdf"; section_heading = "Smoke test"; content = $texts[$i]
       content_vector = $emb.data[$i].embedding; page_start = 1; page_end = 1
       contract_type = "Test"; allowed_groups = $groups[$i]; extraction_version = "smoketest"
       ingested_at = (Get-Date).ToUniversalTime().ToString("o") }
}
Invoke-RestMethod -Method Post -Uri "$sep/indexes/$INDEX/docs/index?api-version=$SearchApi" -Headers $sh `
    -ContentType "application/json" -Body (@{ value = @($docs) } | ConvertTo-Json -Depth 10) | Out-Null
Write-Host "Uploaded 3 chunks"
Start-Sleep -Seconds 3

function Search-AsGroup($query, $group) {
    $q = Invoke-RestMethod -Method Post -Uri "https://$AOAI.openai.azure.com/openai/v1/embeddings" -Headers $ah `
        -ContentType "application/json" -Body (@{ model = "text-embedding-3-large"; input = $query; dimensions = $EMBED_DIMS } | ConvertTo-Json)
    $body = @{
        search = $query; top = 5; select = "id,section_heading,content"
        filter = "allowed_groups/any(g: search.in(g, '$group'))"
        vectorQueries = @(@{ kind = "vector"; vector = $q.data[0].embedding; fields = "content_vector"; k = 20 })
    }
    Invoke-RestMethod -Method Post -Uri "$sep/indexes/$INDEX/docs/search?api-version=$SearchApi" -Headers $sh `
        -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 10)
}

Write-Host "`n== Hybrid query 'cap on damages' as grp-legal" -ForegroundColor Cyan
$r = Search-AsGroup "cap on damages" "grp-legal"
$r.value | ForEach-Object { Write-Host ("  {0:N4}  {1}" -f $_.'@search.score', $_.id) }
Write-Host "  Top hit should be smoketest-0 (liability), found by meaning: the words 'cap' and 'damages' are not in it"

Write-Host "`n== Same query as grp-procurement (security trimming)" -ForegroundColor Cyan
$r = Search-AsGroup "cap on damages" "grp-procurement"
$r.value | ForEach-Object { Write-Host ("  {0:N4}  {1}" -f $_.'@search.score', $_.id) }
Write-Host "  Expect only smoketest-2: the legal chunks never come back for this group"

Write-Host "`n== Semantic ranker availability on this tier" -ForegroundColor Cyan
try {
    Invoke-RestMethod -Method Post -Uri "$sep/indexes/$INDEX/docs/search?api-version=$SearchApi" -Headers $sh -ContentType "application/json" `
        -Body (@{ search = "cap on damages"; queryType = "semantic"; semanticConfiguration = "default"; top = 3 } | ConvertTo-Json) | Out-Null
    Write-Host "Semantic ranker: available"
} catch {
    Write-Host "Semantic ranker: not available ($($_.Exception.Message.Split([Environment]::NewLine)[0]))"
}

# 5. Clean up test chunks, report storage
Invoke-RestMethod -Method Post -Uri "$sep/indexes/$INDEX/docs/index?api-version=$SearchApi" -Headers $sh -ContentType "application/json" `
    -Body (@{ value = @(0..2 | ForEach-Object { @{ "@search.action" = "delete"; id = "smoketest-$_" } }) } | ConvertTo-Json -Depth 5) | Out-Null
Write-Host "`nTest chunks deleted"

$stats = Invoke-RestMethod -Uri "$sep/servicestats?api-version=$SearchApi" -Headers $sh
$c = $stats.counters
Write-Host ("Storage used: {0:N1} MB of {1:N0} MB   Indexes: {2} of {3}   Vector index: {4:N1} MB of {5:N0} MB" -f `
    ($c.storageSize.usage / 1MB), ($c.storageSize.quota / 1MB), $c.indexesCount.usage, $c.indexesCount.quota,
    ($c.vectorIndexSize.usage / 1MB), ($c.vectorIndexSize.quota / 1MB))
