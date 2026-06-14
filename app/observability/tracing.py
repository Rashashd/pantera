"""LangSmith tracing setup; degrades gracefully when key is absent (FR-032/035)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import structlog

from app.core.config import Settings

_log = structlog.get_logger(__name__)


def configure_tracing(settings: Settings) -> None:
    """Set LangSmith env vars if key is present; no-op when empty (FR-032)."""
    if not settings.langsmith_api_key:
        return
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    _log.info("observability.tracing.enabled", project=settings.langsmith_project)


def traceable(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a function with langsmith.traceable; no-op if langsmith is missing/disabled."""
    try:
        import langsmith  # noqa: F401
        from langsmith import traceable as _traceable

        return _traceable(func)
    except Exception:
        return func
