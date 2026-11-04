"""The orchestrator: runs the agents in order, enforces the gates, owns the feedback loop.

It holds no domain logic — that lives in the prompts — so agent behavior stays
inspectable and swappable (docs/design-doc.md §4).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .agents import CHECKS, AgentCall, run_agent
from .config import PRICING, TIER_MODELS, Settings, cost_usd
from .gates import Decision
from .llm import LLMClient
from .render import coverage, coverage_md, gaps_md, requirement_md, spec_md, stories_md, tests_md

STORY_LEVEL_GAPS = {"uncovered_requirement", "scope_drift", "inconsistency"}


class Rejected(Exception):
    pass


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())[:5]
    return "-".join(words) or "run"


def _feedback(gaps: list, types: set | None = None) -> str:
    chosen = [g for g in gaps if types is None or g["type"] in types]
    return json.dumps(chosen, indent=2, ensure_ascii=False) if chosen else "(none)"


class Pipeline:
    def __init__(self, client: LLMClient, gate, settings: Settings, out_dir: Path | str = "runs", log=print):
        self.client = client
        self.gate = gate
        self.settings = settings
        self.out_root = Path(out_dir)
        self.log = log
        self.calls: list[AgentCall] = []
        self.first_gap_report: list | None = None
        self.loops = 0

    # ---- helpers ---------------------------------------------------------

    def _call(self, agent: str, label: str, **values: Any) -> Any:
        model = self.settings.models[agent]
        self.log(f"→ {label} ({model}) …")
        data, call = run_agent(self.client, agent, model, **values)
        self.calls.append(call)
        cost = f", ${call.cost:.4f}" if call.cost is not None else ""
        retry = ", retried once" if call.attempts > 1 else ""
        self.log(f"  done in {call.seconds:.1f}s ({call.input_tokens:,} in / {call.output_tokens:,} out{cost}{retry})")
        return data

    def _save(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.spec["run"] = self._run_log()
        (self.run_dir / "delivery-spec.json").write_text(
            json.dumps(self.spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (self.run_dir / "delivery-spec.md").write_text(spec_md(self.spec), encoding="utf-8")

    def _run_log(self) -> dict:
        calls = [{
            "agent": c.agent, "model": c.model, "input_tokens": c.input_tokens,
            "output_tokens": c.output_tokens, "seconds": round(c.seconds, 2),
            "attempts": c.attempts, "cost_usd": c.cost,
        } for c in self.calls]
        costs = [c["cost_usd"] for c in calls]
        total = round(sum(costs), 6) if calls and None not in costs else None
        premium = TIER_MODELS["high"]
        baseline = None
        if premium in PRICING and calls:
            baseline = round(sum(cost_usd(premium, c["input_tokens"], c["output_tokens"]) for c in calls), 6)
        return {
            "models": self.settings.models,
            "mock": self.settings.mock,
            "loops": self.loops,
            "max_loops": self.settings.max_loops,
            "calls": calls,
            "total_cost_usd": total,
            "all_premium_cost_usd": baseline,
        }

    def _gate(self, gate: str, title: str, body: str, data: Any, agent: str, allow_revise: bool = True) -> Decision:
        decision = self.gate.review(gate, title, body, data, allow_revise=allow_revise)
        if decision.action == "reject":
            self.spec["status"] = f"rejected at {gate}"
            self._save()
            raise Rejected(gate)
        if decision.action == "edit":
            try:
                decision.edited = CHECKS[agent](decision.edited)
            except ValueError as err:
                self.log(f"Edited JSON doesn't fit the expected shape ({err}); asking again.")
                return self._gate(gate, title, body, data, agent, allow_revise)
        return decision

    def _story_phase(self, feedback: str) -> None:
        """Story Writer + Gate 2, repeated until a human approves the stories."""
        while True:
            stories = self._call("story_writer", "Story Writer",
                                 requirement=self.spec["requirement"], feedback=feedback)
            decision = self._gate("gate2", "Approve the user stories", stories_md(stories), stories, "story_writer")
            if decision.action == "revise":
                feedback = decision.feedback
                continue
            self.spec["stories"] = decision.edited if decision.action == "edit" else stories
            self.spec["approvals"]["gate2"] = True
            self._save()
            return

    # ---- the run ---------------------------------------------------------

    def run(self, feature_request: str) -> dict:
        feature_request = feature_request.strip()
        if not feature_request:
            raise ValueError("The feature request is empty.")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_dir = self.out_root / f"{stamp}-{_slug(feature_request)}"
        self.loops = 0
        self.spec = {
            "feature_request": feature_request,
            "status": "in progress",
            "requirement": None,
            "stories": [],
            "tests": [],
            "gap_report": [],
            "coverage": None,
            "approvals": {"gate1": False, "gate2": False, "gate3": False},
        }
        try:
            self._run(feature_request)
        except Rejected as gate:
            self.log(f"\nStopped: rejected at {gate}. Nothing downstream was run. Partial spec saved to {self.run_dir}")
        return self.spec

    def _run(self, feature_request: str) -> None:
        # Phase 1 — requirement + Gate 1
        feedback = "(none)"
        while True:
            req = self._call("requirements_analyst", "Requirements Analyst",
                             feature_request=feature_request, feedback=feedback)
            decision = self._gate("gate1", "Approve the requirement", requirement_md(req), req, "requirements_analyst")
            if decision.action == "revise":
                feedback = decision.feedback
                continue
            self.spec["requirement"] = decision.edited if decision.action == "edit" else req
            self.spec["approvals"]["gate1"] = True
            self._save()
            break

        # Phase 2 — stories + Gate 2
        self._story_phase("(none)")

        # Phase 3 — tests, QA, bounded feedback loop
        test_feedback = "(none)"
        while True:
            self.spec["tests"] = self._call("test_designer", "Test Designer",
                                            stories=self.spec["stories"], feedback=test_feedback)
            gaps = self._call("qa_verifier", "QA Verifier", requirement=self.spec["requirement"],
                              stories=self.spec["stories"], tests=self.spec["tests"])
            self.spec["gap_report"] = gaps
            if self.first_gap_report is None:
                self.first_gap_report = gaps
            self.spec["coverage"] = coverage(self.spec["stories"], self.spec["tests"])
            self._save()
            high = [g for g in gaps if g["severity"] == "high"]
            if not high or self.loops >= self.settings.max_loops:
                if high:
                    self.log(f"  {len(high)} high-severity gap(s) remain after {self.loops} loop(s); handing to a human.")
                break
            self.loops += 1
            self.log(f"  {len(high)} high-severity gap(s) — feedback loop {self.loops}/{self.settings.max_loops}")
            if any(g["type"] in STORY_LEVEL_GAPS for g in high):
                # Scope problem: stories must change, so they go back through Gate 2.
                self._story_phase(_feedback(gaps, STORY_LEVEL_GAPS))
                test_feedback = _feedback(gaps, {"untested_criterion"})
            else:
                # Only tests are thin: regenerate tests against the same approved stories.
                test_feedback = _feedback(gaps)

        # Gate 3 — final sign-off on a pre-checked package
        body = ("### Tests\n" + tests_md(self.spec["tests"]) + "\n\n### QA gap report\n" + gaps_md(gaps)
                + "\n\n### Mechanical coverage check\n" + coverage_md(self.spec["coverage"]))
        self._gate("gate3", "Final sign-off", body, None, "qa_verifier", allow_revise=False)
        self.spec["approvals"]["gate3"] = True
        self.spec["status"] = "approved"
        self._save()
        self.log(f"\nApproved. Delivery Spec saved to {self.run_dir}/delivery-spec.md (and .json)")
