"""Unit tests for render_report_document (US1/FR-002): content + batch included-only + escaping."""

from types import SimpleNamespace

from app.delivery.rendering import render_report_document


def _report(**overrides):
    base = dict(
        id=42,
        report_type="batch",
        status="approved",
        structured_fields=[
            {"text": "Hepatotoxicity observed in 3 cases", "provenance": "drafted_grounded"},
            {"text": "Reviewer-confirmed causality", "provenance": "reviewer_attested"},
        ],
        corroboration_count=3,
        corroboration_sources=[{"title": "PMID-111"}, {"title": "PMID-222"}, {"title": "PMID-333"}],
        draft_body="Narrative summary of the safety signal.",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestRenderReportDocument:
    def test_self_contained_html(self):
        html = render_report_document(_report())
        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html and "</html>" in html

    def test_includes_claims_and_provenance(self):
        html = render_report_document(_report())
        assert "Hepatotoxicity observed in 3 cases" in html
        assert "drafted_grounded" in html
        assert "reviewer_attested" in html

    def test_includes_corroboration_count_and_all_sources(self):
        html = render_report_document(_report())
        assert "Corroborating sources: 3" in html
        assert "PMID-111" in html and "PMID-222" in html and "PMID-333" in html

    def test_includes_narrative_body(self):
        html = render_report_document(_report())
        assert "Narrative summary of the safety signal." in html

    def test_batch_renders_only_included_findings(self):
        findings = [
            {"drug": "DrugIncluded", "reaction": "rashA", "bucket": "serious", "state": "included"},
            {"drug": "DrugDropped", "reaction": "rashB", "bucket": "serious", "state": "dropped"},
            {
                "drug": "DrugDiscarded",
                "reaction": "rashC",
                "bucket": "serious",
                "state": "discarded",
            },
        ]
        html = render_report_document(_report(), findings)
        assert "DrugIncluded" in html
        assert "DrugDropped" not in html
        assert "DrugDiscarded" not in html

    def test_escapes_html_in_body(self):
        html = render_report_document(_report(draft_body="<script>alert(1)</script>"))
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
