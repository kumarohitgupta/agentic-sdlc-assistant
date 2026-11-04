# Implementation — as built

This document records how the system is built and what it produces. The design rationale lives in [design-doc.md](design-doc.md); this is the concrete counterpart.

The pipeline exists in two runtimes that share one set of prompts ([`../prompts/`](../prompts/)):

| | Python runner | n8n workflow |
| --- | --- | --- |
| Where | [`sdlc_assistant/`](../sdlc_assistant/) | [`n8n/workflow.json`](../n8n/workflow.json) |
| Start | `sdlc-assistant run` | Form trigger (`/form/sdlc-assistant`) |
| Gates | Terminal prompt: approve / revise / edit JSON / reject | Form pages: Approve / Revise / Reject |
| Output | `runs/<id>/delivery-spec.md` + `.json`, with cost log | Final form page + execution data |
| No-key demo | `sdlc-assistant demo` | — |

`n8n/build_workflow.py` generates the n8n workflow from the prompt files, and CI fails if the committed workflow drifts from them.

## Model routing (as built)

| Agent | Claude model | Tier | Why this tier |
| --- | --- | --- | --- |
| 1. Requirements Analyst | Sonnet 5.5 | mid | Ambiguity detection needs reasoning, bounded scope |
| 2. Story Writer | Haiku 5.5 | low | Structured transformation once the requirement is clean |
| 3. Test Designer | Sonnet 5.5 | mid | Edge-case generation rewards more capability |
| 4. QA Verifier | Opus 5.5 | high | Highest-judgment step; the one premium call in the pipeline |

The tier→model mapping lives in one place ([`sdlc_assistant/config.py`](../sdlc_assistant/config.py)). Any agent can be re-routed per run (`--model-qa-verifier claude-sonnet-5-5`) or by environment variable, which is how to test the routing claim: run the eval with the verifier on a cheaper model and compare gap detection.

Every Python run logs tokens and cost per call, and the total next to what the same tokens would have cost on the premium model at every step.

## Orchestration (as built)

- **Hand-offs are validated.** Each reply is parsed (tolerating code fences or stray prose) and checked against the Delivery Spec shape before it enters state. A bad reply gets one retry with the error attached, then the run stops with a clear message.
- **Gates.** Gates 1 and 2 offer approve, revise (reviewer feedback goes into the agent's prompt for a redraft — this is also how open questions get answered), and reject. The Python runner adds *edit*: change the JSON directly, validated before it's accepted. Gate 3 is approve or reject. A rejection stops the run with nothing downstream executed; the partial spec is saved.
- **Feedback loop.** After the QA Verifier, high-severity gaps trigger a loop, capped at 2. Scope gaps (`uncovered_requirement`, `scope_drift`, `inconsistency`) go to the Story Writer, and the new stories go back through Gate 2. Test-only gaps go to the Test Designer. Gaps that survive the cap are shown to the human at Gate 3.
- **Mechanical coverage check.** Alongside the QA Verifier, a deterministic check lists any acceptance criterion missing a positive, negative or edge test, and any test pointing at a criterion that doesn't exist.

In n8n, each agent is a *Basic LLM Chain* with an *Anthropic Chat Model* sub-node. Each gate is a *Form* page followed by a *Switch*, and *Code* nodes parse, validate and carry the Delivery Spec state between steps.

## Verification

- `pytest` covers the full run, routing, rejection, revise feedback, human edits, the loop cap, gate-2 re-entry, retry on malformed output, JSON extraction, prompt rendering, coverage, and the CLI. All tests run offline against the bundled fixtures.
- The n8n workflow was run end to end on n8n 2.46 against a stand-in API serving the same fixtures: revise at Gate 1, the QA loop back through Gate 2, sign-off, the final page, and a reject path, with each call checked for the right model and feedback.

## Sample run

[`../examples/sample-output-delivery-spec.md`](../examples/sample-output-delivery-spec.md) is the offline demo's output on a time-off request. On the first pass the QA Verifier reports two high-severity gaps: the requirement includes manager *rejection*, but no story covers it, and the notification criterion has no tests. It also finds medium gaps, including the untested hand-off between approval and the displayed balance. The loop sends scope gaps to the Story Writer, which adds a rejection story, and test gaps to the Test Designer. The second QA pass finds no high-severity gaps, and every criterion has all three test types.

The demo outputs are fixtures, so they're the same every time. A live run (`sdlc-assistant run --feature-file examples/sample-input-feature.md`) will word things differently.

### Earlier hand-built prototype

Before the generated workflow, the pipeline was built by hand in n8n Cloud (screenshots in [`../assets/`](../assets/)). On a run with a deliberately thin test set, the QA Verifier on Opus found what the planted gaps were meant to catch — the untested manager-rejection path and positive-only stories. It also raised two issues nobody had planted: no test that an approval reduces the balance, and an ambiguity about whether the balance check blocks submission or rejects an already-created request. Those emergent findings are the case for spending the premium tier on this one step. The eval (`sdlc-assistant eval --model-qa-verifier claude-haiku-5-5`) is how to measure it rather than assert it.

## Honest limits

- A prototype and design study, not a benchmarked production system. The evaluation results table in [evaluation.md](evaluation.md) is still to be filled from live runs.
- Gains depend on task scoping; ambiguous or novel work benefits less than well-bounded delivery.
- The gates keep humans in the critical path by design. This optimizes for trust and coverage, not full automation.
