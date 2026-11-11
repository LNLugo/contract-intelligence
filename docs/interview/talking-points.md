# Interview talking points

Each likely question points to the ADR that answers it and the number measured so far. Each ADR ends with a 20-second spoken version.

| Likely question | ADR | Number to quote |
|---|---|---|
| How do you know an improvement is real? | 0022, A/A tests | Ran the same configuration twice: 9% of answers changed, and one identical comparison came out p = 0.031. Now every configuration gets an A/A run first |
| How do you keep the model from hallucinating findings? | 0020, 0021, 0009 | Fabricated quotes reaching a reviewer: 0 (citations checked in code; 2 bad quotes dropped in 200 questions). Grounding on the lawyers' labelled text: 95% |
| How do you know a clause is missing, not just not retrieved? | 0009 revision | Reranker scores for present and absent clauses overlap (median 2.30 vs 1.96); absence is decided by the model reading evidence, a score is only a floor |
| How good is your retrieval? | 0006, 0015 | Clause in top 5: 95% over 279 labelled clauses; drops to 84% on very long contracts |
| What went wrong, and how did you find it? | 0021, build log | 23 "false claims" were the model saying "No" with evidence, counted as "yes" by my routing; fixed in the output contract, re-measured with retrieval frozen |
| How do you stop a user seeing contracts they should not? | 0013, 0023 | Groups come from the validated Entra token, never the request; filter inside the search query, fail closed; leakage test probes every group (enumerate, forbidden docs by ID and name, adversarial text, injection) and must find 0 leaks |
| Where can access control still fail even with a correct filter? | 0023 | Wrong or stale tags, confused-deputy tools, side channels (history, logs, eval artifacts), token group overage and ~1 h membership lag, admins with data-plane roles |
| Why a queue between Event Grid and the Function? | 0018 | Event Grid waits 30 s; 31 of 48 contracts took longer |
| How do you handle rate limits? | 0014 revision | Batch lost 2 of 50 to 429s; capacity set per workload, client paces under the limit |
| How did you choose your evaluation set? | 0015 | Measured 9,348 pages; stratified by length; a median-only set would have shown 99% retrieval instead of 84% on long contracts |
| What does it cost? | cost log | $15.26 to extract 1,526 pages; ~4,100 tokens per question; ~$16 total to date |
| Why LangGraph and not Foundry Agent Service? | 0007 | |
| How do you integrate with SAP or a system of record safely? | 0010 | |
| How would this change in a regulated enterprise? | 0001, 0003, 0014 | GlobalStandard processing would be rejected for residency; private endpoints first |

## Framing this project

This is my own reconstruction of the architecture on my own subscription, built to work hands-on with every Azure service in it. Talk about it as separate from client delivery, and use its measured numbers only for this build.
