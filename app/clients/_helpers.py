"""Shared exceptions and pure helpers for the clients domain (no I/O beyond a savepoint flush)."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Fixed warning threshold: spend at or above 80% of budget warns before the soft cap (FR-010, D12).
WARNING_FRACTION = Decimal("0.80")

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class NameConflict(Exception):
    """Raised when a client/watchlist name collides (case-insensitive) → 409."""


class WatchlistEmpty(Exception):
    """Raised when an operation would leave an active watchlist with zero items → 400 (FR-016)."""


class InvalidEmail(Exception):
    """Raised when an email address fails basic format validation (FR-017)."""


class ScopeRequired(Exception):
    """Raised when a scoped client-user has neither min_severity nor watchlist_ids (FR-014)."""


class CrossClientWatchlist(Exception):
    """Raised when a watchlist_id belongs to a different client (FR-014)."""


def current_period_start() -> date:
    """First day of the current UTC calendar month — the budget period boundary (research D4)."""
    now = datetime.now(UTC)
    return date(now.year, now.month, 1)


def derive_budget_state(budget: Decimal | None, spend: Decimal) -> str:
    """Derive budget state from cap and current-period spend; null budget ⇒ always ok (D4)."""
    if budget is None:
        return "ok"
    if spend >= budget:
        return "soft_capped"
    if spend >= WARNING_FRACTION * budget:
        return "warning"
    return "ok"


def _normalize(value: str) -> str:
    """Idempotency key for an item value: trimmed and lowercased."""
    return value.strip().lower()


def validate_email_address(value: str | None) -> str | None:
    """Basic RFC-5321 shape check; raise InvalidEmail on failure (FR-017)."""
    if value is None:
        return None
    v = value.strip()
    if not _EMAIL_RE.fullmatch(v):
        raise InvalidEmail
    return v


def _validate_scope(
    client_scope: str, *, min_severity: str | None, watchlist_ids: list[int]
) -> None:
    """Raise ScopeRequired when a scoped user has no visibility constraints (FR-014)."""
    if client_scope == "scoped" and not min_severity and not watchlist_ids:
        raise ScopeRequired


async def _try_flush(session: AsyncSession) -> bool:
    """Flush inside a savepoint; return False on a unique violation (race-safe).

    The DB unique indexes are the real guard; this turns a lost concurrent race into a clean
    caller decision (409 / idempotent no-op) instead of an unhandled 500.
    """
    try:
        async with session.begin_nested():
            await session.flush()
        return True
    except IntegrityError:
        return False
