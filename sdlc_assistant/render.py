"""Plain-text and Markdown views of the Delivery Spec, plus a deterministic coverage check."""

from __future__ import annotations

TEST_TYPES = ("positive", "negative", "edge")


def coverage(stories: list, tests: list) -> dict:
    """Which acceptance criteria have positive / negative / edge tests.

    This is a mechanical check that runs alongside the QA Verifier: it can't
    judge whether a test is *good*, but it can't miss a criterion either.
    """
    by_criterion: dict[str, set] = {}
    for story in stories:
        for ac in story["acceptance_criteria"]:
            by_criterion[ac["id"]] = set()
    unknown = []
    for test in tests:
        cid = test["criterion_id"]
        if cid in by_criterion:
            by_criterion[cid].add(test["type"])
        else:
            unknown.append(test["id"])
    missing = {cid: [t for t in TEST_TYPES if t not in kinds]
               for cid, kinds in by_criterion.items() if set(TEST_TYPES) - kinds}
    full = len(by_criterion) - len(missing)
    return {
        "criteria": len(by_criterion),
        "fully_covered": full,
        "missing": missing,
        "tests_with_unknown_criterion": unknown,
    }


def _bullets(items: list) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none)"


def requirement_md(req: dict) -> str:
    return (
        f"**Problem:** {req['problem']}\n\n"
        f"**In scope**\n{_bullets(req['in_scope'])}\n\n"
        f"**Out of scope**\n{_bullets(req['out_of_scope'])}\n\n"
        f"**Assumptions**\n{_bullets(req['assumptions'])}\n\n"
        f"**Open questions**\n{_bullets(req['open_questions'])}"
    )


def stories_md(stories: list) -> str:
    parts = []
    for story in stories:
        lines = [f"**{story['id']}** — {story['story']}"]
        lines += [f"  - `{ac['id']}` {ac['criterion']}" for ac in story["acceptance_criteria"]]
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def tests_md(tests: list) -> str:
    rows = ["| ID | Criterion | Type | Case |", "| --- | --- | --- | --- |"]
    for t in tests:
        case = str(t["case"]).replace("|", "\\|").replace("\n", " ")
        rows.append(f"| {t['id']} | {t['criterion_id']} | {t['type']} | {case} |")
    return "\n".join(rows)


def gaps_md(gaps: list) -> str:
    if not gaps:
        return "No gaps found."
    order = {"high": 0, "medium": 1, "low": 2}
    lines = []
    for g in sorted(gaps, key=lambda g: order.get(g["severity"], 3)):
        refs = f" ({', '.join(g['refs'])})" if g.get("refs") else ""
        lines.append(f"- **{g['severity'].upper()}** · {g['type']}{refs}: {g['detail']}")
    return "\n".join(lines)


def coverage_md(cov: dict) -> str:
    text = f"{cov['fully_covered']} of {cov['criteria']} acceptance criteria have positive, negative and edge tests."
    if cov["missing"]:
        text += "\n" + "\n".join(f"- `{cid}` missing: {', '.join(kinds)}" for cid, kinds in cov["missing"].items())
    if cov["tests_with_unknown_criterion"]:
        text += "\n- Tests pointing at a criterion id that doesn't exist: " + ", ".join(cov["tests_with_unknown_criterion"])
    return text


def spec_md(spec: dict) -> str:
    run = spec["run"]
    cost_lines = []
    for call in run["calls"]:
        cost = f"${call['cost_usd']:.4f}" if call["cost_usd"] is not None else "n/a"
        cost_lines.append(
            f"| {call['agent']} | `{call['model']}` | {call['input_tokens']:,} | {call['output_tokens']:,} | {cost} |"
        )
    total = run.get("total_cost_usd")
    baseline = run.get("all_premium_cost_usd")
    cost_summary = ""
    if total is not None and baseline:
        cost_summary = (f"\n\n**Total:** ${total:.4f} · same tokens on the premium model for every step: "
                        f"${baseline:.4f} ({(1 - total / baseline) * 100:.0f}% saved by routing)")
    mode = " (mock mode: canned outputs, estimated tokens)" if run.get("mock") else ""
    approvals = ", ".join(f"{k}: {'approved' if v else 'not approved'}" for k, v in spec["approvals"].items())
    sections = [
        "# Delivery Spec",
        f"**Status:** {spec['status']} · {approvals} · QA feedback loops used: {run['loops']}",
        "## Feature request\n\n" + "\n".join("> " + line for line in spec["feature_request"].splitlines()),
        "## 1. Requirement\n\n" + requirement_md(spec["requirement"]) if spec.get("requirement") else "",
        "## 2. User stories\n\n" + stories_md(spec["stories"]) if spec.get("stories") else "",
        "## 3. Test cases\n\n" + tests_md(spec["tests"]) if spec.get("tests") else "",
        ("## 4. QA gap report\n\n" + gaps_md(spec["gap_report"]) + "\n\n**Mechanical coverage check:** "
         + coverage_md(spec["coverage"])) if spec.get("coverage") else "",
        "## Run log" + mode + "\n\n| Agent | Model | Input tokens | Output tokens | Cost |\n| --- | --- | --- | --- | --- |\n"
        + "\n".join(cost_lines) + cost_summary,
    ]
    return "\n\n".join(s for s in sections if s) + "\n"
