# Design Document — Agentic SDLC Delivery Assistant

**Status:** v1 — implemented twice: a Python runner (`sdlc_assistant/`) and an importable n8n workflow (`n8n/workflow.json`). Both follow this document.
**Scope:** upstream SDLC (requirements → stories → tests → verification). Code generation and deployment are explicitly out of scope.

This document explains the *why* behind every design choice. It is written to be defensible in a design review: each decision states the alternative considered and the reason for the call.

---

## 1. Problem framing

Software delivery has three broad phases where AI can assist: **planning** (requirements, stories, test design), **building** (code generation), and **verifying** (review, QA). Most tooling and attention has gone to the building phase, because code generation demos well. But when AI-native delivery is benchmarked end-to-end, the speed advantage is large in building and thin — sometimes negative — in planning and verification, because those phases reward judgment and consistency over raw generation.

That creates a specific opportunity: **the planning and verification phases are underserved and are where quality gaps concentrate.** A system that structures the front of the SDLC well, and self-checks before a human reviews, addresses the part of the lifecycle where AI assistance is currently weakest.

**Design goal:** take an ambiguous feature request and produce a verified, review-ready delivery package, minimizing both human effort and the risk of shipping work that doesn't match the ask.

## 2. Why multi-agent (and not one big prompt)

A single large prompt could, in principle, produce requirements, stories, and tests in one shot. We reject that for three reasons:

1. **Quality.** Narrow, single-responsibility agents can be prompted precisely and produce more consistent output than one prompt juggling four jobs. This mirrors separation of concerns in system design.
2. **Cost control.** Splitting the work lets us send each step to the cheapest model that can do it well, instead of paying top-tier prices for the whole chain (see §5).
3. **Verifiability.** A separate verification agent that never wrote the stories is far more likely to catch their gaps than the same context asked to check itself.

The tradeoff is orchestration overhead — more moving parts, more handoffs, more places for context to drift. We mitigate drift by passing structured state (§6) rather than free-form chat.

## 3. The agents

Each agent has one responsibility, a defined input, a defined output, and an assigned model tier.

### Agent 1 — Requirements Analyst
- **Job:** turn a raw feature request into a clean, disambiguated requirement. Surface hidden assumptions and list open questions rather than inventing answers.
- **Input:** raw feature request (free text).
- **Output:** structured requirement — problem statement, in-scope, out-of-scope, assumptions, open questions.
- **Model tier:** mid. Ambiguity detection needs some reasoning, but the task is bounded.
- **Key behavior:** it must *flag* ambiguity, not paper over it. A confident but wrong interpretation is the most expensive failure in the chain, because everything downstream inherits it.

### Agent 2 — Story Writer
- **Job:** decompose the approved requirement into user stories, each with acceptance criteria.
- **Input:** approved requirement.
- **Output:** list of user stories in `As a / I want / so that` form, each with Gherkin `Given / When / Then` acceptance criteria. Every criterion gets its own id (`US-1.AC1`) so tests and gaps can point at it exactly.
- **Model tier:** low. This is largely structured transformation once the requirement is clean.

### Agent 3 — Test Designer
- **Job:** generate test cases for each acceptance criterion — happy path, negative cases, and edge cases.
- **Input:** approved user stories.
- **Output:** test cases, each linked to a specific acceptance criterion id, tagged by type.
- **Model tier:** mid. Edge-case generation benefits from a stronger model than story formatting does.

### Agent 4 — QA Verifier
- **Job:** the quality gate. Check two kinds of coverage: do the stories fully cover the requirement, and do the tests fully cover the acceptance criteria? Produce a gap report.
- **Input:** requirement + stories + tests (the full spec so far).
- **Output:** gap report — a list of uncovered requirement elements, untested criteria, and inconsistencies, each with a severity.
- **Model tier:** high. This is the highest-judgment step and the one where we most want reasoning quality, so it gets the strongest model even though it runs once.

## 4. Orchestration pattern

The pipeline is a **sequential chain with review gates and a conditional feedback loop**:

- Agents run in order 1 → 2 → 3 → 4.
- After agents 1, 2, and 4 there is a **human-in-the-loop (HITL) gate**.
- If the QA Verifier (agent 4) reports high-severity gaps, the orchestrator **routes back** with the gap report attached, rather than surfacing broken output to the human. Where it routes depends on the gap:
  - a **scope** gap (`uncovered_requirement`, `scope_drift`, `inconsistency`) goes back to the **Story Writer**, and the revised stories pass through Gate 2 again, because a human approved the old ones;
  - a gap that is only **thin tests** (`untested_criterion`) goes back to the **Test Designer**, since the approved stories are fine.

  This is the one automatic loop in the system, and it is bounded (max 2 iterations) to prevent runaway cost. Gaps that survive the cap go to Gate 3, where the human sees them.
- At Gates 1 and 2 the reviewer can **approve**, **revise** (write feedback — including answers to open questions — and the agent redrafts), **edit** the JSON directly (Python runner), or **reject**, which stops the run with nothing downstream produced.

An **orchestrator** owns control flow: it invokes each agent, enforces the gates, carries the shared state object, and decides when to loop versus advance. It holds no domain logic of its own — a deliberate choice so that agent behavior stays inspectable and swappable.

### Why gates at 1, 2, and 4 (and not 3)
Gates are placed where a wrong call is *expensive to unwind*:
- **Gate 1 (after requirements):** the highest-leverage checkpoint — a misread requirement corrupts everything after it.
- **Gate 2 (after stories):** stories define scope; catching a missing story here is cheap, catching it after test design is not.
- **Gate 3 (after verification):** the human reviews a *pre-checked* package and makes the ship/iterate call.
- **No gate after test design (agent 3):** tests are downstream of already-approved stories, and the QA Verifier checks them immediately after — a gate here would add friction without adding much safety.

## 5. Model-routing strategy

The core cost lever. Rather than run the whole chain on one premium model, each agent is assigned the cheapest tier that meets its quality bar:

| Agent | Task type | Model tier | Rationale |
| --- | --- | --- | --- |
| 1. Requirements Analyst | Ambiguity detection | **Mid** | Needs reasoning to spot gaps, but bounded scope |
| 2. Story Writer | Structured transformation | **Low** | Mostly formatting once requirement is clean |
| 3. Test Designer | Enumeration + edge cases | **Mid** | Edge cases reward a bit more capability |
| 4. QA Verifier | Cross-artifact reasoning | **High** | Highest-judgment step; worth the premium |

The insight: **spend model budget where judgment lives (verification) and economize where the task is structural (story formatting).** This keeps average cost-per-run low while protecting quality at the step that matters most. Tier names are model-agnostic on purpose — you plug in whatever low/mid/high models your platform offers.

## 6. State and handoffs

Agents do not pass conversational messages to each other. They read from and write to a single structured **Delivery Spec** object:

```json
{
  "requirement": { "problem": "", "in_scope": [], "out_of_scope": [], "assumptions": [], "open_questions": [] },
  "stories": [ { "id": "US-1", "story": "", "acceptance_criteria": [ { "id": "US-1.AC1", "criterion": "" } ] } ],
  "tests": [ { "id": "T-1", "criterion_id": "US-1.AC1", "type": "positive|negative|edge", "case": "" } ],
  "gap_report": [ { "type": "", "severity": "high|medium|low", "detail": "", "refs": [] } ],
  "coverage": { "criteria": 0, "fully_covered": 0, "missing": {} },
  "approvals": { "gate1": false, "gate2": false, "gate3": false }
}
```

Passing typed state instead of chat history is what keeps context from drifting across four agents. Each agent sees exactly the fields it needs and nothing else.

Every agent reply is parsed and checked against this shape before it enters the spec (required fields, allowed test types and severities, unique criterion ids). A malformed reply is retried once with the error attached; if it fails again, the run stops with a clear message rather than passing bad state downstream.

`coverage` is computed mechanically after each QA pass: which criteria have positive, negative and edge tests. It can't judge test quality, but it can't miss a criterion either, so it backs up the QA Verifier rather than replacing it.

## 7. Failure modes and mitigations

Designing for failure is the senior part of this exercise. The main risks and how the architecture handles them:

| Failure mode | Why it happens | Mitigation |
| --- | --- | --- |
| **Confident misread of the requirement** | LLMs resolve ambiguity silently | Analyst must list open questions; Gate 1 forces human confirmation |
| **Hallucinated acceptance criteria** not grounded in the requirement | Generation without grounding | QA Verifier checks story→requirement coverage; Gate 2 |
| **Context drift** across the chain | Free-form handoffs accumulate noise | Typed Delivery Spec state (§6) |
| **Cost blowup** | Premium model on every step + loops | Model routing (§5) + bounded feedback loop (max 2) |
| **Over-automation** (human rubber-stamps) | Gates become theater | Verifier surfaces a *specific* gap list, so review is substantive, not vibes |
| **Malformed model output** | Models occasionally wrap or break JSON | Tolerant parsing, schema checks, one retry with the error, then a clear stop |
| **Prompt injection** via requirement text | Untrusted input treated as instruction | Requirement text is handled as data, delimited in the prompt (triple quotes in the input are neutralized so it can't close the block); agents are instructed to treat it as content to analyze, never as instructions |

## 8. What "good" looks like (success criteria)

- A human spends materially less time producing a review-ready delivery package than doing it manually, **without** a drop in coverage.
- The QA Verifier reliably catches injected gaps in the evaluation set (see [evaluation.md](evaluation.md)).
- Average cost-per-run stays low because only one step uses the premium model.

## 9. Extensions (deliberately deferred)

Called out so reviewers see the roadmap, not gaps:
- Estimation agent (story points / effort).
- Integration to write approved stories into a tracker (Jira/Linear) — an action step behind an explicit human approval.
- Retrieval of prior similar stories to improve consistency across a backlog.
- A/B of model tiers to quantify the cost/quality frontier empirically.

---

*This is a v1 reference design intended to be read, challenged, and adjusted. Every model tier, gate placement, and loop bound is a decision you can defend or change — which is the point of the artifact.*
