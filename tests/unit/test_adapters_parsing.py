"""Unit tests for adapter fixture → RawRecord parsing (no live network, D16)."""

from __future__ import annotations

from pathlib import Path


def _fixture(source: str, filename: str) -> str:
    """Read a recorded adapter fixture from tests/fixtures/<source>/."""
    p = Path(__file__).parent.parent / "fixtures" / source / filename
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# T017: PubMed adapter parsing
# ---------------------------------------------------------------------------


class TestPubmedAdapterParsing:
    def test_parses_efetch_xml_to_raw_records(self):
        """PubMed adapter XML parser produces correct RawRecords from the fixture."""
        from app.ingestion.adapters.pubmed import _parse_efetch_xml
        from app.ingestion.enums import SourceName

        xml = _fixture("pubmed", "efetch_response.xml")
        records = _parse_efetch_xml(xml)

        assert len(records) == 2

        r0 = records[0]
        assert r0.source == SourceName.PUBMED
        assert r0.pmid == "40123456"
        assert r0.doi == "10.1000/jcard.2026.001"
        assert r0.source_external_id == "40123456"
        assert "Hepatotoxicity" in r0.title
        assert r0.summary is not None and "DrugX" in r0.summary
        assert r0.published_at is not None
        assert r0.published_at.year == 2026
        assert r0.published_at.month == 5
        assert isinstance(r0.raw_payload, dict)

        r1 = records[1]
        assert r1.pmid == "40123457"
        assert r1.doi is None
        assert "Warfarin" in r1.title

    def test_parses_missing_date_gracefully(self):
        """A PubMed record without a PubDate produces published_at=None."""
        from app.ingestion.adapters.pubmed import _parse_efetch_xml

        xml = """<?xml version="1.0" ?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
      <PMID Version="1">99000001</PMID>
      <Article PubModel="Print">
        <Journal><JournalIssue CitedMedium="Print"><PubDate></PubDate></JournalIssue></Journal>
        <ArticleTitle>No date article</ArticleTitle>
        <ArticleIdList><ArticleId IdType="pubmed">99000001</ArticleId></ArticleIdList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList><ArticleId IdType="pubmed">99000001</ArticleId></ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""
        records = _parse_efetch_xml(xml)
        assert len(records) == 1
        assert records[0].published_at is None

    def test_empty_xml_returns_no_records(self):
        """An empty PubmedArticleSet produces an empty list."""
        from app.ingestion.adapters.pubmed import _parse_efetch_xml

        xml = '<?xml version="1.0" ?><PubmedArticleSet></PubmedArticleSet>'
        assert _parse_efetch_xml(xml) == []


# ---------------------------------------------------------------------------
# T023: Other adapters parsing unit tests
# ---------------------------------------------------------------------------


class TestEuropePMCAdapterParsing:
    def test_parses_search_json(self):
        from app.ingestion.adapters.europepmc import _parse_search_response
        from app.ingestion.enums import SourceName

        data = _fixture("europepmc", "search_response.json")
        import json

        records = _parse_search_response(json.loads(data))
        assert len(records) == 2
        r0 = records[0]
        assert r0.source == SourceName.EUROPEPMC
        assert r0.pmid == "40234567"
        assert r0.doi == "10.1016/j.jhepatol.2026.03.001"
        assert "DILI" in r0.title
        assert r0.published_at is not None
        assert r0.published_at.year == 2026

        r1 = records[1]
        assert r1.pmid is None  # preprint has no PMID
        assert "Preprint" in r1.title

    def test_empty_results(self):
        from app.ingestion.adapters.europepmc import _parse_search_response

        records = _parse_search_response({"resultList": {"result": []}})
        assert records == []


class TestOpenFDAAdapterParsing:
    def test_parses_faers_json(self):
        import json

        from app.ingestion.adapters.openfda import _parse_faers_response
        from app.ingestion.enums import SourceName

        data = _fixture("openfda", "faers_response.json")
        records = _parse_faers_response(json.loads(data))
        assert len(records) == 1
        r = records[0]
        assert r.source == SourceName.OPENFDA_FAERS  # tier == case_report (via adapter)
        assert "US-FDA-20260001" in r.source_external_id

    def test_parses_label_json(self):
        import json

        from app.ingestion.adapters.openfda import _parse_label_response
        from app.ingestion.enums import SourceName

        data = _fixture("openfda", "label_response.json")
        records = _parse_label_response(json.loads(data))
        assert len(records) == 1
        r = records[0]
        assert r.source == SourceName.OPENFDA_LABEL  # tier == peer_reviewed (via adapter)


class TestFDAMedWatchAdapterParsing:
    def test_parses_rss_xml(self):
        from app.ingestion.adapters.fda_medwatch import _parse_rss
        from app.ingestion.enums import SourceName

        xml = _fixture("fda_medwatch", "rss_response.xml")
        records = _parse_rss(xml)
        assert len(records) == 1
        r = records[0]
        assert r.source == SourceName.FDA_MEDWATCH  # tier == regulatory_alert (via adapter)
        assert "Warfarin" in r.title
        assert r.published_at is not None


class TestEMAAdapterParsing:
    def test_parses_json_response(self):
        import json

        from app.ingestion.adapters.ema import _parse_response
        from app.ingestion.enums import SourceName

        data = _fixture("ema", "dhpc_response.json")
        records = _parse_response(json.loads(data))
        assert len(records) == 1
        r = records[0]
        assert r.source == SourceName.EMA  # tier == regulatory_alert (via adapter)
        assert "EMA-DHPC-2026-001" in r.source_external_id


class TestMHRAAdapterParsing:
    def test_parses_json_response(self):
        import json

        from app.ingestion.adapters.mhra import _parse_response
        from app.ingestion.enums import SourceName

        data = _fixture("mhra", "drug_alert_response.json")
        records = _parse_response(json.loads(data))
        assert len(records) == 1
        r = records[0]
        assert r.source == SourceName.MHRA  # tier == regulatory_alert (via adapter)
        assert "MHRA-DSU-2026-001" in r.source_external_id
