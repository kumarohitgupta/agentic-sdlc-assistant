"""Command line: `sdlc-assistant run | demo | eval`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from importlib import resources
from pathlib import Path

from . import __version__
from .agents import AgentOutputError
from .config import AGENT_TIERS, Settings
from .gates import AutoApprove, ConsoleGate
from .llm import AnthropicClient, MissingAPIKey, MockClient
from .pipeline import Pipeline


def load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env support (KEY=value lines) so users needn't export variables."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _read_feature(args) -> str:
    if args.feature:
        return args.feature
    if args.feature_file:
        return Path(args.feature_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print("Describe the feature in a few sentences, then press Enter twice:")
    lines = []
    while True:
        line = input()
        if not line.strip() and lines:
            break
        lines.append(line)
    return "\n".join(lines)


def _settings(args, mock: bool) -> Settings:
    overrides = {agent: getattr(args, f"model_{agent}", None) for agent in AGENT_TIERS}
    return Settings.build(overrides, max_loops=args.max_loops,
                          auto_approve=getattr(args, "auto_approve", False), mock=mock)


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", default="runs", help="folder for run outputs (default: runs/)")
    p.add_argument("--max-loops", type=int, default=2, help="cap on QA feedback loops (default: 2)")
    for agent, tier in AGENT_TIERS.items():
        p.add_argument(f"--model-{agent.replace('_', '-')}", dest=f"model_{agent}",
                       help=f"override the {agent.replace('_', ' ')} model (default tier: {tier})")


def cmd_run(args) -> int:
    feature = _read_feature(args)
    client = MockClient() if args.mock else AnthropicClient()
    gate = AutoApprove() if args.auto_approve else ConsoleGate()
    spec = Pipeline(client, gate, _settings(args, args.mock), args.out).run(feature)
    return 0 if spec["status"] == "approved" else 2


def cmd_demo(args) -> int:
    print("Offline demo: canned agent outputs, no API key or cost. "
          "The QA Verifier flags a gap on the first pass, so you'll see the feedback loop run.\n")
    feature = (resources.files("sdlc_assistant") / "mock_data" / "feature_request.txt").read_text(encoding="utf-8")
    print("Feature request:\n" + feature)
    gate = AutoApprove() if args.auto_approve else ConsoleGate()
    spec = Pipeline(MockClient(), gate, _settings(args, True), args.out).run(feature)
    return 0 if spec["status"] == "approved" else 2


def _contains(blob: str, keywords: list[str]) -> bool:
    low = blob.lower()
    return any(k.lower() in low for k in keywords)


def cmd_eval(args) -> int:
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if args.only:
        wanted = {c.strip().upper() for c in args.only.split(",")}
        cases = [c for c in cases if c["id"].upper() in wanted]
    client = MockClient() if args.mock else AnthropicClient()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = Path(args.out) / f"eval-{stamp}"
    rows = []
    for case in cases:
        print(f"\n######## {case['id']} — {case['title']}")
        pipe = Pipeline(client, AutoApprove(), _settings(args, args.mock), out_root)
        spec = pipe.run(case["request"])
        gaps = spec["gap_report"]
        cov = spec["coverage"] or {"criteria": 0, "fully_covered": 0}
        row = {
            "case": case["id"],
            "open_questions": len(spec["requirement"]["open_questions"]) if spec["requirement"] else 0,
            "stories": len(spec["stories"]),
            "criteria": cov["criteria"],
            "fully_covered": cov["fully_covered"],
            "tests": len(spec["tests"]),
            "gaps_high": sum(g["severity"] == "high" for g in gaps),
            "gaps_total": len(gaps),
            "loops": spec["run"]["loops"],
            "cost_usd": spec["run"]["total_cost_usd"],
            "run_dir": str(pipe.run_dir),
        }
        planted = case.get("planted_gap")
        if planted:
            first_qa = json.dumps(pipe.first_gap_report or [])
            row["planted_gap_flagged_by_qa"] = _contains(first_qa, planted["keywords"])
            row["planted_gap_covered_in_final_stories"] = _contains(json.dumps(spec["stories"]), planted["keywords"])
        rows.append(row)

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "results.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    lines = [
        "| Case | Open Qs | Stories | Criteria fully tested | Tests | High gaps (final) | Loops | Planted gap flagged by QA | Planted gap covered at end | Cost |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        flagged = {True: "yes", False: "no"}.get(r.get("planted_gap_flagged_by_qa"), "—")
        covered = {True: "yes", False: "no"}.get(r.get("planted_gap_covered_in_final_stories"), "—")
        cost = f"${r['cost_usd']:.3f}" if r["cost_usd"] is not None else "n/a"
        lines.append(f"| {r['case']} | {r['open_questions']} | {r['stories']} | {r['fully_covered']}/{r['criteria']} "
                     f"| {r['tests']} | {r['gaps_high']} | {r['loops']} | {flagged} | {covered} | {cost} |")
    planted_rows = [r for r in rows if "planted_gap_flagged_by_qa" in r]
    if planted_rows:
        rate = sum(r["planted_gap_flagged_by_qa"] for r in planted_rows) / len(planted_rows)
        lines.append(f"\nPlanted-gap detection rate (flagged by QA on first pass): {rate:.0%}")
    table = "\n".join(lines)
    (out_root / "results.md").write_text(table + "\n", encoding="utf-8")
    print("\n" + table + f"\n\nSaved to {out_root}/results.md — keyword matching is a first pass; "
          "confirm by reading each gap report before quoting the numbers.")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="sdlc-assistant",
                                     description="Turn a feature request into a verified Delivery Spec.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the pipeline on a feature request (needs ANTHROPIC_API_KEY)")
    src = run.add_mutually_exclusive_group()
    src.add_argument("--feature", help="the feature request text")
    src.add_argument("--feature-file", help="path to a text/markdown file with the feature request")
    run.add_argument("--auto-approve", action="store_true", help="approve every gate automatically (demo/CI only)")
    run.add_argument("--mock", action="store_true", help="use canned outputs instead of calling Claude")
    _add_common(run)
    run.set_defaults(func=cmd_run)

    demo = sub.add_parser("demo", help="offline walkthrough with canned outputs — no API key needed")
    demo.add_argument("--auto-approve", action="store_true", help="don't stop at the gates")
    _add_common(demo)
    demo.set_defaults(func=cmd_demo)

    ev = sub.add_parser("eval", help="run the evaluation cases unattended and tabulate results")
    ev.add_argument("--cases", default="evals/cases.json")
    ev.add_argument("--only", help="comma-separated case ids, e.g. EC-4,EC-5")
    ev.add_argument("--mock", action="store_true", help="smoke-test the harness without API calls")
    _add_common(ev)
    ev.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except MissingAPIKey as err:
        print(f"\n{err}", file=sys.stderr)
        return 1
    except AgentOutputError as err:
        print(f"\nAgent output problem: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130
    except Exception as err:
        if type(err).__module__.startswith("anthropic"):
            hint = ""
            if "authentication" in type(err).__name__.lower():
                hint = " Check that ANTHROPIC_API_KEY is correct and active."
            elif "notfound" in type(err).__name__.lower():
                hint = " A model id may be wrong for your account; override it with --model-<agent>."
            print(f"\nClaude API error: {err}.{hint}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
