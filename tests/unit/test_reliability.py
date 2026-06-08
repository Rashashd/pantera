"""Unit tests for SourceReliability tier ordering and highest-rank resolution."""

from app.ingestion.enums import SourceReliability


def test_rank_ordering():
    """regulatory_alert > peer_reviewed > preprint > case_report."""
    assert SourceReliability.REGULATORY_ALERT.rank > SourceReliability.PEER_REVIEWED.rank
    assert SourceReliability.PEER_REVIEWED.rank > SourceReliability.PREPRINT.rank
    assert SourceReliability.PREPRINT.rank > SourceReliability.CASE_REPORT.rank


def test_highest_rank_from_list():
    """_highest_reliability returns the max-rank value from a list of strings."""
    from app.ingestion.service import _highest_reliability

    result = _highest_reliability(["case_report", "peer_reviewed", "regulatory_alert"])
    assert result == "regulatory_alert"


def test_highest_rank_single():
    """Single element list returns itself."""
    from app.ingestion.service import _highest_reliability

    assert _highest_reliability(["preprint"]) == "preprint"


def test_reliability_values():
    """Enum string values match the expected CHECK constraint strings."""
    assert SourceReliability.REGULATORY_ALERT.value == "regulatory_alert"
    assert SourceReliability.PEER_REVIEWED.value == "peer_reviewed"
    assert SourceReliability.PREPRINT.value == "preprint"
    assert SourceReliability.CASE_REPORT.value == "case_report"
