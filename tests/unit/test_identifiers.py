"""Unit tests: normalize_id precedence + unidentifiable record handling (T036, US3)."""

from __future__ import annotations

from app.ingestion.enums import SourceName
from app.ingestion.identifiers import normalize_id


class TestNormalizeIdPrecedence:
    """DOI > PMID > source:id ordering (D4)."""

    def test_doi_wins_over_pmid(self):
        result = normalize_id(
            doi="10.1000/xyz123",
            pmid="99999",
            source=SourceName.PUBMED,
            source_external_id="PM99999",
        )
        assert result == "doi:10.1000/xyz123"

    def test_doi_wins_over_source_id(self):
        result = normalize_id(
            doi="10.1000/xyz123",
            pmid=None,
            source=SourceName.EUROPEPMC,
            source_external_id="EPM-001",
        )
        assert result == "doi:10.1000/xyz123"

    def test_pmid_wins_over_source_id_when_no_doi(self):
        result = normalize_id(
            doi=None,
            pmid="12345678",
            source=SourceName.PUBMED,
            source_external_id="PM12345678",
        )
        assert result == "pmid:12345678"

    def test_source_id_used_when_no_doi_or_pmid(self):
        result = normalize_id(
            doi=None,
            pmid=None,
            source=SourceName.OPENFDA_FAERS,
            source_external_id="US-FDA-9876",
        )
        assert result == "openfda_faers:us-fda-9876"

    def test_empty_doi_falls_through_to_pmid(self):
        result = normalize_id(
            doi="   ",
            pmid="55555",
            source=SourceName.PUBMED,
            source_external_id="PM55555",
        )
        assert result == "pmid:55555"

    def test_empty_pmid_falls_through_to_source_id(self):
        result = normalize_id(
            doi=None,
            pmid="  ",
            source=SourceName.FDA_MEDWATCH,
            source_external_id="MW-2026-001",
        )
        assert result == "fda_medwatch:mw-2026-001"

    def test_returns_none_when_all_identifiers_empty(self):
        """Unidentifiable record → None; runner should count it as errored (D4)."""
        result = normalize_id(
            doi=None,
            pmid=None,
            source=SourceName.PUBMED,
            source_external_id="",
        )
        assert result is None

    def test_returns_none_when_source_id_only_whitespace(self):
        result = normalize_id(
            doi=None,
            pmid=None,
            source=SourceName.EMA,
            source_external_id="   ",
        )
        assert result is None

    def test_doi_lowercased_and_stripped(self):
        result = normalize_id(
            doi="  10.1000/ABC  ",
            pmid=None,
            source=SourceName.PUBMED,
            source_external_id="PM001",
        )
        assert result == "doi:10.1000/abc"

    def test_pmid_lowercased(self):
        result = normalize_id(
            doi=None,
            pmid="PMID:12345",
            source=SourceName.EUROPEPMC,
            source_external_id="X",
        )
        assert result == "pmid:pmid:12345"

    def test_source_id_lowercased(self):
        result = normalize_id(
            doi=None,
            pmid=None,
            source=SourceName.EMA,
            source_external_id="DHPC-UPPER",
        )
        assert result == "ema:dhpc-upper"

    def test_same_doi_different_sources_yields_same_key(self):
        """Cross-source dedup: same DOI from PubMed and EuropePMC → same normalized key."""
        doi = "10.1016/j.phar.2026.01.001"
        key_pubmed = normalize_id(
            doi=doi,
            pmid="111111",
            source=SourceName.PUBMED,
            source_external_id="PM111111",
        )
        key_europe = normalize_id(
            doi=doi,
            pmid=None,
            source=SourceName.EUROPEPMC,
            source_external_id="MED-111111",
        )
        assert key_pubmed == key_europe == f"doi:{doi}"
