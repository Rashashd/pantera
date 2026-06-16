"""Real-wiring fail-safe: guardrails ENABLED + unreachable sidecar → each site fails safe.

Complements test_guardrails_egress (mocked client) by driving the actual triage egress functions
with a real GuardrailsClient pointed at a dead address, proving the wiring escalates/keeps-positive
rather than silently proceeding (quickstart scenario 3 / FR-006). Uses a closed port so the
connection is refused immediately (not a retryable timeout) — fast and deterministic.
"""

from __future__ import annotations

import pytest

import app.triage.llm as triage_llm
from app.core.config import Settings
from app.guardrails.client import GuardrailsUnavailable

pytestmark = pytest.mark.asyncio

_DEAD_URL = "http://127.0.0.1:1"  # nothing listens here → ConnectError


def _settings() -> Settings:
    s = Settings()
    s.guardrails_enabled = True  # explicitly ON for this test (overrides the suite default)
    s.redaction_enabled = False  # skip spaCy; we only exercise the guard outage path
    s.guardrails_url = _DEAD_URL
    s.guardrails_token = "x"
    return s


async def test_triage_resolve_escalates_on_guardrails_outage(monkeypatch):
    """resolve_yes_no raises GuardrailsUnavailable → caller (resolve_adverse) escalates."""
    monkeypatch.setattr(triage_llm, "build_llm_client", lambda s: object())
    monkeypatch.setattr(triage_llm, "_load_prompt", lambda name: "SYSTEM\n<document>")

    async def _should_not_run(*a, **k):
        raise AssertionError("_call_llm must NOT run when the input guard is unavailable")

    monkeypatch.setattr(triage_llm, "_call_llm", _should_not_run)

    with pytest.raises(GuardrailsUnavailable):
        await triage_llm.resolve_yes_no("patient text", "peer_reviewed", _settings(), 1, 1)


async def test_triage_valence_keeps_positive_on_guardrails_outage(monkeypatch):
    """assess_valence swallows the outage and returns its 'positive' fail-safe default (FR-016)."""
    monkeypatch.setattr(triage_llm, "build_llm_client", lambda s: object())
    monkeypatch.setattr(
        triage_llm, "_load_prompt", lambda name: "SYSTEM {source_reliability}\n<document>"
    )

    async def _should_not_run(*a, **k):
        raise AssertionError("_call_llm must NOT run when the input guard is unavailable")

    monkeypatch.setattr(triage_llm, "_call_llm", _should_not_run)

    result = await triage_llm.assess_valence("patient text", "peer_reviewed", _settings(), 1, 1)
    assert result == "positive"
