# Evaluation

How to tell whether the system actually works, rather than just runs. A portfolio project that includes an evaluation method reads as more senior than one that only shows output.

## Method

We use a small, fixed set of feature requests as an evaluation harness (see [`../evals/eval-cases.md`](../evals/eval-cases.md)). Each case is run through the full pipeline, and the output is scored against a rubric by a human reviewer. A subset of cases has **deliberately planted gaps** (a requirement element with no matching story, or an acceptance criterion with no test) to measure whether the QA Verifier catches them.

Keeping the set small and fixed (5–8 cases) is intentional: it makes runs comparable over time and cheap to repeat whenever a prompt or model tier changes.

## Rubric

Each run is scored on four dimensions, 1–5:

| Dimension | 1 (poor) | 5 (strong) |
| --- | --- | --- |
| **Requirement quality** | Misreads intent; no open questions surfaced | Faithful; ambiguities flagged, not invented |
| **Story completeness** | Misses scope; vague criteria | Full coverage; testable Gherkin criteria |
| **Test coverage** | Happy path only | Positive + negative + edge, mapped to criteria |
| **Gap detection** | Misses planted gaps | Catches planted gaps with correct severity |

## Gap-detection score

The headline metric. Across the planted-gap cases:

```
gap_detection_rate = (planted gaps correctly flagged) / (total planted gaps)
```

This isolates the value of the QA Verifier — the step the whole design bets on.

## Results table (template)

Fill this in as you run the cases. This is what an interviewer will want to see.

| Case | Req. quality | Story compl. | Test cov. | Gap detection | Notes |
| --- | --- | --- | --- | --- | --- |
| EC-1 | | | | | |
| EC-2 | | | | | |
| EC-3 | | | | | |
| EC-4 (planted gap) | | | | | |
| EC-5 (planted gap) | | | | | |
| **Avg** | | | | | |

## What to do with the results

- If **requirement quality** is weak, the problem is upstream and everything inherits it — fix the Analyst prompt first.
- If **gap detection** is weak, either the Verifier model tier is too low or its prompt isn't specific about *what* to check — this is the step worth spending model budget on.
- Track cost-per-run alongside quality so you can speak to the cost/quality tradeoff, not just quality in isolation.
