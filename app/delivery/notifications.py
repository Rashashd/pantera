"""Internal-staff alerts (delivery failure, SLA escalation, budget threshold) routed via n8n."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import UserType
from app.delivery.n8n_client import N8nClient

_log = structlog.get_logger(__name__)


async def _staff_recipients(session: AsyncSession, roles: tuple[str, ...]) -> list[str]:
    """Active staff emails for the given roles (staff act across all clients — D11/CHK032)."""
    return list(
        (
            await session.execute(
                select(User.email).where(
                    User.user_type == UserType.STAFF.value,
                    User.is_active == True,  # noqa: E712
                    User.role.in_(roles),
                )
            )
        )
        .scalars()
        .all()
    )


async def notify_staff(
    session: AsyncSession,
    n8n: N8nClient,
    *,
    notification_type: str,
    roles: tuple[str, ...],
    client_id: int | None,
    context: dict[str, Any],
) -> list[str]:
    """Route one internal-staff notification through n8n; returns the recipients targeted.

    The payload carries only ids/codes/recipient emails — never document text or PII (FR-024).
    A send failure is swallowed (best-effort alert) so a flaky routing layer never breaks a sweep.
    """
    recipients = await _staff_recipients(session, roles)
    if not recipients:
        _log.warning("notify.no_recipients", notification_type=notification_type, roles=roles)
        return []
    payload = {
        "channel": "notification",
        "notification_type": notification_type,
        "recipients": recipients,
        "client_id": client_id,
        **context,
    }
    try:
        await n8n.send(payload)
    except Exception as exc:  # noqa: BLE001 — best-effort alert; do not break the caller
        _log.warning(
            "notify.send_failed", notification_type=notification_type, error=type(exc).__name__
        )
    return recipients


async def notify_delivery_failure(
    session: AsyncSession, n8n: N8nClient, *, report_id: int, client_id: int, reason: str
) -> list[str]:
    """Alert manager+admin that a report's delivery failed (FR-004a/006a)."""
    return await notify_staff(
        session,
        n8n,
        notification_type="delivery_failed",
        roles=("manager", "admin"),
        client_id=client_id,
        context={"report_id": report_id, "reason": reason},
    )


async def notify_sla_escalation(
    session: AsyncSession, n8n: N8nClient, *, report_id: int, client_id: int, tier: int
) -> list[str]:
    """SLA escalation: Tier-1 → the client's reviewers; Tier-2 → manager+admin (FR-012)."""
    roles = ("reviewer",) if tier == 1 else ("manager", "admin")
    return await notify_staff(
        session,
        n8n,
        notification_type=f"sla_tier{tier}",
        roles=roles,
        client_id=client_id,
        context={"report_id": report_id, "tier": tier},
    )


async def notify_budget_threshold(
    session: AsyncSession, n8n: N8nClient, *, watchlist_id: int, client_id: int, state: str
) -> list[str]:
    """Notify manager+admin that a watchlist crossed a budget threshold (FR-019, US6)."""
    return await notify_staff(
        session,
        n8n,
        notification_type="budget_threshold",
        roles=("manager", "admin"),
        client_id=client_id,
        context={"watchlist_id": watchlist_id, "state": state},
    )
