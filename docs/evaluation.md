# Evaluation

How to tell whether the system actually works, rather than just runs.

## Method

A small, fixed set of feature requests is the evaluation harness ([`../evals/cases.json`](../evals/cases.json), described in [`../evals/eval-cases.md`](../evals/eval-cases.md)). Each case runs through the full pipeline, and the output is scored against a rubric by a human reviewer. Two cases have **deliberately planted gaps** — something the request implies but doesn't say — to measure whether the QA Verifier catches them.

Keeping the set small and fixed (6 cases) is intentional: runs stay comparable over time and cheap to repeat whenever a prompt or model tier changes.

## Running it

```bash
sdlc-assistant eval                 # all six cases, gates auto-approved
sdlc-assistant eval --only EC-4,EC-5   # just the planted-gap cases
```

Each case's full Delivery Spec lands in `runs/eval-<timestamp>/`, with a `results.md` table that records, per case: open questions raised, stories, criteria with full test coverage, high-severity gaps remaining, loops used, cost, and — for EC-4 and EC-5 — whether the planted gap was flagged by the QA Verifier on its first pass. The planted-gap check is a keyword match, so read the gap report before you quote the number.

Gates are auto-approved in eval mode so the runs are comparable. That makes the QA Verifier's first-pass report the honest measure: no human has fixed anything yet.

You can also run the eval from GitHub: **Actions → CI → Run workflow → live eval**, with an `ANTHROPIC_API_KEY` repository secret. Results are attached to the run as an artifact.

## Rubric

Each run is scored by a human on four dimensions, 1–5:

| Dimension | 1 (poor) | 5 (strong) |
| --- | --- | --- |
| **Requirement quality** | Misreads intent; no open questions surfaced | Faithful; ambiguities flagged, not invented |
| **Story completeness** | Misses scope; vague criteria | Full coverage; testable Gherkin criteria |
| **Test coverage** | Happy path only | Positive + negative + edge, mapped to criteria |
| **Gap detection** | Misses planted gaps | Catches planted gaps with correct severity |

## Gap-detection score

The headline metric. Across the planted-gap cases:

```
gap_detection_rate = (planted gaps flagged on the QA Verifier's first pass) / (total planted gaps)
```

This isolates the value of the QA Verifier — the step the whole design bets on. To test the routing claim directly, rerun with the verifier on a cheaper model and compare:

```bash
sdlc-assistant eval --only EC-4,EC-5 --model-qa-verifier claude-haiku-5-5
```

## Results

| Case | Req. quality | Story compl. | Test cov. | Gap detection | Cost | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| EC-1 | | | | — | | |
| EC-2 | | | | — | | |
| EC-3 | | | | — | | |
| EC-4 (planted gap) | | | | | | |
| EC-5 (planted gap) | | | | | | |
| EC-6 | | | | — | | |
| **Avg** | | | | | | |

*Not yet filled in: run `sdlc-assistant eval` and score each spec.*

## What to do with the results

- If **requirement quality** is weak, the problem is upstream and everything inherits it — fix the Analyst prompt first.
- If **gap detection** is weak, either the Verifier model tier is too low or its prompt isn't specific about *what* to check — this is the step worth spending model budget on.
- Track cost per run (it's in every run log) alongside quality so the cost/quality tradeoff is measured, not asserted.
