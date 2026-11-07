# Interview talking points

Each likely question points to the ADR that answers it. Each ADR ends with a 20-second spoken version. Once a phase is done, add the measured number to the answer.

| Likely question | ADR | Number to quote (fill in once measured) |
|---|---|---|
| How do you keep the model from hallucinating findings? | 0009, 0012 | Citation support rate; accuracy on non-abstained findings |
| Why hybrid search? Why that reranker? | 0006 | Recall@20; precision@5 per reranker; p95 latency |
| How do you stop a user seeing contracts they should not? | 0013 | Zero leaked chunks in the phase 11 test |
| Why LangGraph and not Foundry Agent Service? | 0007 | |
| How do you integrate with SAP or a system of record safely? | 0010 | Behavior when the vendor API is down |
| How did you chunk, and how do you know it works? | 0005 | Recall, fixed-size vs clause-aware |
| What broke? | 0008, build log | Turn-15 accuracy and prompt tokens, before and after |
| How do you evaluate an LLM system? | 0012 | Judge vs human agreement rate |
| What does it cost? | cost log | Per-contract unit cost |
| How would this change in a regulated enterprise? | 0001, 0003 | |

## Framing this project

This is my own reconstruction of the architecture on my own subscription, built to work hands-on with every Azure service in it. Talk about it as a separate thing from client delivery, and use its measured numbers only for this build.
