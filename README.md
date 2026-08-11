# Agentic SDLC Delivery Assistant

A multi-agent system that turns a raw feature request into a review-ready delivery package — refined requirements, user stories with acceptance criteria, test cases, and an automated QA gap report — with a human approval gate at every phase.

**Status:** Built and running. The pipeline is implemented as a working no-code workflow in n8n with task-optimized model routing across Claude Haiku, Sonnet, and Opus, and three human-in-the-loop approval gates. See [Implementation](docs/implementation.md).

> **What this is:** a reference design *and* a working prototype for applying multi-agent orchestration to the software delivery lifecycle (SDLC). It demonstrates how to structure task-optimized agents, route work across cheaper and stronger models to control cost, and keep a human in the loop where judgment matters.
>
> **What this is not:** a production developer tool or a replacement for a delivery team. It is a portfolio-grade prototype and design study.

---

## My role & key decisions

I designed and built this system end to end. The decisions I'd point to in a review:

- **Four single-responsibility agents instead of one prompt** — for output quality, cost control, and independent verification. A do-everything prompt is cheaper to wire but worse on all three.
- **Task-optimized model routing** — each step runs on the cheapest model tier that meets its bar, and the premium model is reserved for the one step where judgment matters most (QA verification). This keeps average cost-per-run low without sacrificing quality where it counts.
- **Human approval gates at the three highest-leverage points** — after requirements, after stories, and at final sign-off — so no AI output advances unverified, and a wrong call is caught where it's cheap to unwind.
- **Typed state hand-offs, not chat** — agents pass a structured Delivery Spec rather than free-form conversation, which prevents context drift across the chain.

The design draws on my work on AI strategy for software delivery, where competitive benchmarking showed the largest quality gaps sit in **planning and verification** rather than in code generation — which is exactly the gap this system targets.

## The problem

AI coding assistants are fast at *writing* code, but most of the cost and risk in software delivery sits **upstream** — in turning a vague request into well-formed requirements, stories, and tests — and **downstream**, in verifying that what was built actually covers what was asked. The largest quality gaps in AI-native delivery consistently appear in **planning and verification**, not in raw code generation.

This project targets exactly those two gaps: it treats the front half of the SDLC as an orchestration problem — a small team of specialized agents, each doing one job well, with a verification agent whose only purpose is to catch gaps before a human signs off.

## What it produces

Given a one-paragraph feature request, the pipeline outputs a structured **Delivery Spec** containing:

1. A cleaned, disambiguated **requirement** (with open questions flagged)
2. **User stories** with Gherkin-style acceptance criteria
3. **Test cases** — positive, negative, and edge — mapped to each acceptance criterion
4. A **QA gap report** — where stories don't cover the requirement, or tests don't cover the stories

A human reviews and approves at three checkpoints, so nothing advances on unverified AI output.

## Architecture

```
Feature request
      │
      ▼
[1] Requirements Analyst  (Sonnet) ──► HITL Gate 1 (approve requirement)
      │
      ▼
[2] Story Writer          (Haiku)  ──► HITL Gate 2 (approve stories)
      │
      ▼
[3] Test Designer         (Sonnet)
      │
      ▼
[4] QA Verifier           (Opus)   ──► HITL Gate 3 (final sign-off)
      │
      ▼
  Delivery Spec
```

![Architecture](assets/architecture-diagram.svg)

Full reasoning is in **[docs/design-doc.md](docs/design-doc.md)**; the as-built details are in **[docs/implementation.md](docs/implementation.md)**.

## Screenshots

| | |
| --- | --- |
| ![Pipeline canvas](assets/canvas.png) | The full four-agent pipeline in n8n, with the Wait + If approval gate |
| ![Model routing](assets/model-routing.png) | Different Claude tiers assigned per node (the cost-routing decision) |
| ![Approval gate](assets/approval-form.png) | A human-in-the-loop approval form pausing the pipeline mid-run |
| ![QA output](assets/qa-verifier-output.png) | The QA Verifier catching coverage gaps the earlier agents left |

## Repository map

| Path | What's inside |
| --- | --- |
| [`docs/design-doc.md`](docs/design-doc.md) | The core design artifact: architecture, agent design, model routing, HITL rationale, failure modes |
| [`docs/implementation.md`](docs/implementation.md) | How it's actually built in n8n, the as-built routing, and results from a real run |
| [`docs/business-case.md`](docs/business-case.md) | Why this matters commercially — cost, speed, and quality framing |
| [`docs/evaluation.md`](docs/evaluation.md) | Evaluation methodology, rubric, and results table |
| [`docs/build-guide.md`](docs/build-guide.md) | Step-by-step: rebuild the working flow in a no-code tool |
| [`prompts/`](prompts/) | The system prompt for each of the four agents |
| [`examples/`](examples/) | A sample input feature request and the Delivery Spec it produces |
| [`evals/`](evals/) | The evaluation case set used to measure quality |

## Design principles

- **One job per agent.** Narrow agents are easier to prompt, cheaper to run, and easier to debug.
- **Route by task difficulty.** Structuring goes to a cheap model; verification goes to a strong one.
- **Verify before a human sees it.** A dedicated QA agent catches gaps so the human reviews a *checked* draft.
- **Human-in-the-loop where judgment lives.** Approval gates sit where a wrong call is expensive to unwind.
- **Pass structured state, not chat.** Typed hand-offs prevent context drift across the chain.

## License

MIT — see [LICENSE](LICENSE).
