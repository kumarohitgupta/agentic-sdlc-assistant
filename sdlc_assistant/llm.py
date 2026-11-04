"""LLM clients: the real Anthropic client, and a mock client for demos and tests."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from importlib import resources
from typing import Protocol


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    seconds: float


class LLMClient(Protocol):
    def complete(self, agent: str, model: str, prompt: str, max_tokens: int) -> Completion: ...


class MissingAPIKey(RuntimeError):
    pass


class AnthropicClient:
    """Calls the Claude Messages API. Streams so long outputs don't hit request timeouts."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise MissingAPIKey(
                "ANTHROPIC_API_KEY is not set. Create a key at https://platform.claude.com, then\n"
                "  export ANTHROPIC_API_KEY=sk-ant-...      (macOS/Linux)\n"
                "  setx ANTHROPIC_API_KEY sk-ant-...        (Windows, then reopen the terminal)\n"
                "or put it in a .env file next to where you run the command.\n"
                "No key? Try the offline demo:  sdlc-assistant demo"
            )
        import anthropic  # imported lazily so mock mode needs no SDK

        self._client = anthropic.Anthropic(api_key=key, max_retries=4)

    def complete(self, agent: str, model: str, prompt: str, max_tokens: int) -> Completion:
        start = time.monotonic()
        with self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()
        text = "".join(block.text for block in message.content if block.type == "text")
        return Completion(
            text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            seconds=time.monotonic() - start,
        )


class MockClient:
    """Replays canned agent outputs from sdlc_assistant/mock_data/.

    Each agent has numbered fixtures (qa_verifier_1.json, qa_verifier_2.json, ...).
    Call N returns fixture N, and the last fixture repeats. The bundled QA fixtures
    report a high-severity gap first and a clean pass second, so the demo exercises
    the feedback loop. Token counts are rough estimates (4 chars per token).
    """

    def __init__(self):
        self._calls: dict[str, int] = {}
        self._root = resources.files("sdlc_assistant") / "mock_data"

    def _fixture(self, agent: str, n: int) -> str:
        names = sorted(
            (p.name for p in self._root.iterdir() if p.name.startswith(agent + "_")),
            key=lambda name: int(name.rsplit("_", 1)[1].split(".")[0]),
        )
        if not names:
            raise FileNotFoundError(f"no mock fixture for {agent}")
        name = names[min(n, len(names)) - 1]
        return (self._root / name).read_text(encoding="utf-8")

    def complete(self, agent: str, model: str, prompt: str, max_tokens: int) -> Completion:
        n = self._calls.get(agent, 0) + 1
        self._calls[agent] = n
        text = self._fixture(agent, n)
        json.loads(text)  # fixtures must be valid JSON
        return Completion(
            text=text,
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            seconds=0.0,
        )
