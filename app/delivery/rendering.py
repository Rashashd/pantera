"""Render an approved report into the self-contained HTML document delivered to the client."""

from __future__ import annotations

import html
from typing import Any


def _esc(value: Any) -> str:
    """HTML-escape a value (None → empty string)."""
    return html.escape(str(value)) if value is not None else ""


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a dict or an object."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def render_report_document(report: Any, findings: Any = ()) -> str:
    """Render a report as one self-contained HTML document (no external assets, no PDF).

    Includes the structured claims with provenance, the corroboration count and every
    corroboration source, the narrative body, and — for batch reports — only the *included*
    findings (dropped/discarded excluded). This same artifact is delivered to the client and
    served by the download endpoint (FR-002/FR-017).
    """
    report_id = _esc(_attr(report, "id", ""))
    report_type = _esc(_attr(report, "report_type", ""))
    status = _esc(_attr(report, "status", ""))
    claims = _attr(report, "structured_fields", None) or []
    corroboration_count = _attr(report, "corroboration_count", 0)
    sources = _attr(report, "corroboration_sources", None) or []
    body = _attr(report, "draft_body", None) or ""

    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>Pantera report {report_id}</title></head><body>",
        f"<h1>Pharmacovigilance Report #{report_id}</h1>",
        f'<p class="meta">Type: {report_type} &middot; Status: {status} &middot; '
        f"Corroborating sources: {_esc(corroboration_count)}</p>",
        "<h2>Claims</h2><ul>",
    ]
    for c in claims:
        parts.append(
            f'<li>{_esc(_attr(c, "text", ""))} '
            f'<span class="provenance">[{_esc(_attr(c, "provenance", ""))}]</span></li>'
        )
    parts.append("</ul>")

    if sources:
        parts.append("<h2>Corroboration sources</h2><ul>")
        for s in sources:
            label = (
                _attr(s, "title", None)
                or _attr(s, "external_id", None)
                or _attr(s, "source", None)
                or s
            )
            parts.append(f"<li>{_esc(label)}</li>")
        parts.append("</ul>")

    # Batch: render only included findings (drop/discard excluded — FR-013a / Edge Cases).
    included = [f for f in findings if _attr(f, "state", "included") in (None, "included")]
    if included:
        parts.append("<h2>Findings</h2><ul>")
        for f in included:
            parts.append(
                f'<li>{_esc(_attr(f, "drug", ""))} &mdash; {_esc(_attr(f, "reaction", ""))} '
                f'({_esc(_attr(f, "bucket", ""))})</li>'
            )
        parts.append("</ul>")

    parts.append("<h2>Narrative</h2>")
    parts.append(f'<div class="narrative">{_esc(body)}</div>')
    parts.append("</body></html>")
    return "\n".join(parts)
