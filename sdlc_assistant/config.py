"""Model routing and pricing.

Every agent runs on the cheapest tier that meets its quality bar; only the
QA Verifier uses the premium tier. Override any model with an environment
variable (e.g. SDLC_MODEL_QA_VERIFIER=claude-sonnet-5-5) or a CLI flag.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Tier -> default Claude model. Change these in one place to re-route the chain.
TIER_MODELS = {
    "low": "claude-haiku-5-5",
    "mid": "claude-sonnet-5-5",
    "high": "claude-opus-5-5",
}

# Agent -> tier. This table *is* the routing decision described in docs/design-doc.md §5.
AGENT_TIERS = {
    "requirements_analyst": "mid",
    "story_writer": "low",
    "test_designer": "mid",
    "qa_verifier": "high",
}

# USD per million tokens (input, output). Source: Anthropic pricing page, Nov 2026.
# Used only to report cost per run; update if prices change.
PRICING = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

# Output caps. Real runs on a 7-story feature used ~12k tokens for tests, so
# leave headroom. Kept at or under 20k so the n8n workflow (non-streaming) works too.
MAX_TOKENS = {
    "requirements_analyst": 4000,
    "story_writer": 12000,
    "test_designer": 20000,
    "qa_verifier": 16000,
}


def _env_key(agent: str) -> str:
    return f"SDLC_MODEL_{agent.upper()}"


@dataclass
class Settings:
    models: dict[str, str] = field(default_factory=dict)
    max_loops: int = 2
    auto_approve: bool = False
    mock: bool = False

    @classmethod
    def build(cls, overrides: dict[str, str | None] | None = None, **kwargs) -> "Settings":
        models = {}
        for agent, tier in AGENT_TIERS.items():
            chosen = (overrides or {}).get(agent) or os.environ.get(_env_key(agent))
            models[agent] = chosen or TIER_MODELS[tier]
        return cls(models=models, **kwargs)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    if model not in PRICING:
        return None
    price_in, price_out = PRICING[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
