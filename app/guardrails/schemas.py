"""Pydantic request/response schemas for the guardrails sidecar /guard contract."""

from typing import Literal

from pydantic import BaseModel

Direction = Literal["input", "output"]
CallSite = Literal["triage", "agent", "intake"]
Action = Literal["allow", "block"]


class GuardRequest(BaseModel):
    """One payload (prompt or model output) to evaluate against the platform rails."""

    text: str
    direction: Direction
    client_id: int  # acting tenant context (used by the cross-client rail)
    call_site: CallSite


class GuardResponse(BaseModel):
    """Rail evaluation result; never echoes the input text or any PII."""

    action: Action
    rail: str | None = None  # injection | jailbreak | topic_scope | cross_client (when blocked)
    reason: str | None = None  # non-PII reason code
    checked: list[str] = []  # rails evaluated for this direction
