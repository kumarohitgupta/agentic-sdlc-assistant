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

### Live run 1 — 3 Nov 2026

Five of the six cases, run with `sdlc-assistant eval` on the default routing (Sonnet 5.5 → Haiku 5.5 → Sonnet 5.5 → Opus 5.5), gates auto-approved. EC-6 is still to run.

| Case | Open questions | Stories | Criteria with +/−/edge tests | Tests | QA loops | High gaps left | Cost | vs. all-Opus |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EC-1 Password reset | 12 | 7 | 25/25 | 80 | 0 | 0 | $0.32 | −40% |
| EC-2 CSV export | 11 | 4 | 15/15 | 57 | 1 (tests) | 0 | $0.50 | −35% |
| EC-3 Notifications | 13 | 5 | 20/20 | 69 | 0 | 0 | $0.24 | −41% |
| EC-4 Bulk upload *(planted gap)* | 11 | 5 | 30/30 | 126 | 2 (stories) | 0 | $1.37 | −49% |
| EC-5 Two-factor login *(planted gap)* | 12 | 6 | 19/19 | 59 | 0 | 0 | $0.27 | −41% |
| **Total** | | | **109/109** | **391** | | | **$2.70** | **−44%** |

"vs. all-Opus" is the same token counts priced as if every step ran on Opus 5.5.

**Planted gaps.** The QA Verifier flagged both on its first pass:
- **EC-4 (row validation rules):** flagged on the first pass, which reported two high-severity gaps. The feedback loop sent the work back to the Story Writer twice, and the final stories cover row validation.
- **EC-5 (lost-device recovery):** flagged at medium. The QA Verifier pointed out that a user who loses their phone can neither log in nor turn 2FA off. The Requirements Analyst had also listed recovery as an open question. Because recovery was not in scope, no loop ran, and the final stories don't cover it. In normal use a reviewer answers that question at Gate 1; in eval mode nobody does. This is deliberate: the system flags missing scope for a human rather than adding it on its own.

**Feedback loop.** Both routes fired: EC-2 had a test-only gap and re-ran just the Test Designer, while EC-4 had scope gaps and re-ran the Story Writer, with the new stories passing Gate 2 again.

**Cost.** Opus is one step of four but about half of each run's cost, which is the intended concentration. Most of the rest is the Test Designer's long output. EC-4 includes about $0.30 of retries from the original output caps, since raised.

**Not yet measured:** the human rubric scores below, EC-6, and the same cases with a cheaper QA Verifier (`--model-qa-verifier claude-haiku-5-5`), which is what would show whether the premium tier earns its cost.

### Rubric scores (human review)

| Case | Req. quality | Story compl. | Test cov. | Gap detection | Notes |
| --- | --- | --- | --- | --- | --- |
| EC-1 | | | | — | |
| EC-2 | | | | — | |
| EC-3 | | | | — | |
| EC-4 (planted gap) | | | | | |
| EC-5 (planted gap) | | | | | Flagged at medium; not auto-fixed (see above) |
| EC-6 | | | | — | |
| **Avg** | | | | | |

## What to do with the results

- If **requirement quality** is weak, the problem is upstream and everything inherits it — fix the Analyst prompt first.
- If **gap detection** is weak, either the Verifier model tier is too low or its prompt isn't specific about *what* to check — this is the step worth spending model budget on.
- Track cost per run (it's in every run log) alongside quality so the cost/quality tradeoff is measured, not asserted.
