# Implementation — as built

This document records how the system was actually built and what it produced on a real run. The design rationale lives in [design-doc.md](design-doc.md); this is the concrete counterpart.

## Platform

Built as a no-code workflow in **n8n** (cloud), using the **Anthropic (Claude)** API for all four agents. No application code was written — each agent is an n8n *Basic LLM Chain* node with a system prompt (see [`../prompts/`](../prompts/)) and an assigned Claude model. The human gates are built from n8n's *Wait* and *If* nodes.

## Model routing (as built)

Each agent runs on the cheapest Claude tier that meets its quality bar, with the premium model reserved for verification:

| Agent | n8n node | Claude tier | Why this tier |
| --- | --- | --- | --- |
| 1. Requirements Analyst | Basic LLM Chain | **Sonnet** (mid) | Ambiguity detection needs reasoning, bounded scope |
| 2. Story Writer | Basic LLM Chain | **Haiku 4.5** (low) | Structured transformation once the requirement is clean |
| 3. Test Designer | Basic LLM Chain | **Sonnet** (low–mid) | Edge-case generation rewards a bit more capability |
| 4. QA Verifier | Basic LLM Chain | **Opus** (high) | Highest-judgment step; the one premium call in the pipeline |

This is the core cost lever: three of four steps run on non-premium models, and only the verification step — the one the whole design bets on — uses Opus.

## Human-in-the-loop gates (as built)

Each gate is a two-node pattern inserted into the pipeline:

1. A **Wait** node with *Resume: On Form Submitted*, configured with a form that shows the upstream agent's output (pre-filled via an expression) plus a **Decision** dropdown (Approve / Reject). The workflow pauses here and generates a review link.
2. An **If** node checking `Decision == Approve`. The **true** branch continues the pipeline; the **false** branch is left unconnected, so a rejection halts the flow — nothing downstream runs.

Three gates are placed after the Requirements Analyst, after the Story Writer, and after the QA Verifier. On a full run the pipeline pauses three times, once per gate, and only proceeds on explicit human approval. A rejection at any gate stops the run — verified by running the Reject path and confirming no downstream artifacts are produced.

## Sample run — results

A run on the sample time-off feature request (see [`../examples/`](../examples/)) produced clean requirements, six user stories, and a test set — and the QA Verifier, given a deliberately thin test set, surfaced the coverage gaps the earlier agents missed. Selected findings:

**High severity**
- Manager **rejection path has no test** — the requirement covers approve *and* reject, but only the approval path was tested. Tied back explicitly to an in-scope requirement element.
- Several stories had **no negative or edge tests** (view-balance, submit-request, calendar-reflection were positive-only), each flagged with the specific missing cases.

**Medium severity (emergent — beyond the planted gaps)**
- **Cross-story integration gap:** nothing verified that the remaining balance actually decrements after an approval — the link between the approval story and the balance-display story was untested.
- **Validation-ordering ambiguity:** it was unspecified whether the balance check blocks submission or rejects an already-created request, meaning two tests could both pass while the real over-balance-on-submit path stayed untested.

The emergent findings are the point: a cheaper model running this step would likely have caught the obvious missing tests but not the integration and ordering issues. That difference is the justification for routing this one step to the premium tier.

## Reproducing it

The full build steps are in [build-guide.md](build-guide.md). In short: create the four Basic LLM Chain nodes, paste the prompts, assign the model tiers above, then insert the Wait + If gate pattern at the three checkpoints.

## Honest limits

- This is a prototype and design study, not a benchmarked production system.
- Gains depend on task scoping; ambiguous or novel work benefits less than well-bounded delivery.
- The gates keep humans in the critical path by design — this optimizes for trust and coverage, not full automation.
