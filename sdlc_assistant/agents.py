"""The four agents: prompt rendering, JSON extraction and schema checks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .config import MAX_TOKENS, cost_usd
from .llm import Completion, LLMClient

PROMPT_FILES = {
    "requirements_analyst": "requirements-analyst.txt",
    "story_writer": "story-writer.txt",
    "test_designer": "test-designer.txt",
    "qa_verifier": "qa-verifier.txt",
}


class AgentOutputError(RuntimeError):
    """The model's reply could not be parsed into the expected shape, even after a retry."""


def _prompt_dir() -> Path:
    # Repo checkout (editable install): <repo>/prompts. Wheel install: bundled copy.
    repo = Path(__file__).resolve().parent.parent / "prompts"
    if repo.is_dir():
        return repo
    return Path(str(resources.files("sdlc_assistant") / "prompts"))


def load_prompt(agent: str) -> str:
    return (_prompt_dir() / PROMPT_FILES[agent]).read_text(encoding="utf-8")


def render(template: str, **values: Any) -> str:
    out = template
    for key, value in values.items():
        if not isinstance(value, str):
            value = json.dumps(value, indent=2, ensure_ascii=False)
        # Neutralize triple quotes so input text can't close the data delimiter.
        value = value.replace('"""', "'''")
        out = out.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{(\w+)\}\}", out)
    if leftover:
        raise ValueError(f"prompt has unfilled placeholders: {leftover}")
    return out


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences or stray prose around it."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON object or array found")
    start = min(starts)
    closer = "}" if cleaned[start] == "{" else "]"
    end = cleaned.rfind(closer)
    if end <= start:
        raise ValueError("unterminated JSON")
    return json.loads(cleaned[start : end + 1])


# ---- schema checks -------------------------------------------------------

def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def check_requirement(data: Any) -> dict:
    _require(isinstance(data, dict), "expected a JSON object")
    _require(isinstance(data.get("problem"), str) and data["problem"].strip(), '"problem" must be a non-empty string')
    for key in ("in_scope", "out_of_scope", "assumptions", "open_questions"):
        _require(isinstance(data.get(key), list), f'"{key}" must be a list')
    _require(len(data["in_scope"]) > 0, '"in_scope" must not be empty')
    return data


def check_stories(data: Any) -> list:
    _require(isinstance(data, list) and data, "expected a non-empty JSON array of stories")
    seen = set()
    for story in data:
        _require(isinstance(story, dict), "each story must be an object")
        for key in ("id", "story", "acceptance_criteria"):
            _require(key in story, f'story missing "{key}"')
        _require(isinstance(story["acceptance_criteria"], list) and story["acceptance_criteria"],
                 f'{story["id"]}: "acceptance_criteria" must be a non-empty list')
        for i, ac in enumerate(story["acceptance_criteria"], 1):
            if isinstance(ac, str):  # tolerate the older string-only form
                ac = {"id": f'{story["id"]}.AC{i}', "criterion": ac}
                story["acceptance_criteria"][i - 1] = ac
            _require(isinstance(ac, dict) and ac.get("id") and ac.get("criterion"),
                     f'{story["id"]}: each criterion needs "id" and "criterion"')
            _require(ac["id"] not in seen, f'duplicate criterion id {ac["id"]}')
            seen.add(ac["id"])
    return data


def check_tests(data: Any) -> list:
    _require(isinstance(data, list) and data, "expected a non-empty JSON array of tests")
    for test in data:
        _require(isinstance(test, dict), "each test must be an object")
        for key in ("id", "criterion_id", "type", "case"):
            _require(key in test, f'test missing "{key}"')
        _require(test["type"] in ("positive", "negative", "edge"),
                 f'{test["id"]}: type must be positive, negative or edge')
    return data


def check_gaps(data: Any) -> list:
    _require(isinstance(data, list), "expected a JSON array (use [] for no gaps)")
    for gap in data:
        _require(isinstance(gap, dict), "each gap must be an object")
        for key in ("type", "severity", "detail"):
            _require(key in gap, f'gap missing "{key}"')
        gap["severity"] = str(gap["severity"]).lower()
        _require(gap["severity"] in ("high", "medium", "low"), "severity must be high, medium or low")
        gap.setdefault("refs", [])
    return data


CHECKS = {
    "requirements_analyst": check_requirement,
    "story_writer": check_stories,
    "test_designer": check_tests,
    "qa_verifier": check_gaps,
}


# ---- calling an agent ----------------------------------------------------

@dataclass
class AgentCall:
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    seconds: float
    attempts: int

    @property
    def cost(self) -> float | None:
        return cost_usd(self.model, self.input_tokens, self.output_tokens)


def run_agent(client: LLMClient, agent: str, model: str, **values: Any) -> tuple[Any, AgentCall]:
    """Render the agent's prompt, call the model, parse and check the reply.

    On a malformed reply, retries once with the parse error appended, so a
    single formatting slip doesn't kill the run.
    """
    prompt = render(load_prompt(agent), **values)
    total_in = total_out = 0
    seconds = 0.0
    last_error = ""
    last_text = ""
    for attempt in (1, 2):
        ask = prompt
        if attempt == 2:
            ask = (prompt + "\n\nYour previous reply could not be used: " + last_error
                   + "\nReply again with ONLY valid JSON in the required shape.")
        done: Completion = client.complete(agent, model, ask, MAX_TOKENS[agent])
        total_in += done.input_tokens
        total_out += done.output_tokens
        seconds += done.seconds
        last_text = done.text
        try:
            data = CHECKS[agent](extract_json(done.text))
            return data, AgentCall(agent, model, total_in, total_out, seconds, attempt)
        except (ValueError, json.JSONDecodeError) as err:
            last_error = str(err)
    raise AgentOutputError(
        f"{agent} returned output that isn't valid ({last_error}). First 500 chars:\n{last_text[:500]}"
    )
