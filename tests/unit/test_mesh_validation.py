"""Unit tests: MeSH validate() — valid/invalid/unvalidated + missing-artifact degradation (T039)."""

from __future__ import annotations

from unittest.mock import patch

from app.ingestion.enums import MeshValidity
from app.ingestion.mesh import load_mesh_terms, validate_mesh


class TestValidateMesh:
    """validate_mesh() returns the correct (validity, canonical) pair (FR-009)."""

    def test_valid_term_exact_case(self):
        """A known heading returns VALID and the stripped input as canonical."""
        validity, canonical = validate_mesh("Warfarin")
        assert validity == MeshValidity.VALID
        assert canonical == "Warfarin"

    def test_valid_term_case_insensitive(self):
        """Lookup is case-insensitive: 'warfarin' matches 'Warfarin' in the list."""
        validity, canonical = validate_mesh("warfarin")
        assert validity == MeshValidity.VALID
        assert canonical == "warfarin"

    def test_valid_term_with_whitespace(self):
        """Leading/trailing whitespace is stripped before comparison."""
        validity, canonical = validate_mesh("  Warfarin  ")
        assert validity == MeshValidity.VALID
        assert canonical == "Warfarin"

    def test_invalid_term(self):
        """A term not in the list → INVALID, no canonical."""
        validity, canonical = validate_mesh("NotARealMeSHTerm_XYZ")
        assert validity == MeshValidity.INVALID
        assert canonical is None

    def test_empty_string_is_invalid(self):
        validity, canonical = validate_mesh("")
        assert validity == MeshValidity.INVALID
        assert canonical is None

    def test_multi_word_valid_term(self):
        """Multi-word headings (common in MeSH) are matched correctly."""
        validity, canonical = validate_mesh("Adverse Drug Reaction Reporting Systems")
        assert validity == MeshValidity.VALID

    def test_unvalidated_when_artifact_missing(self):
        """When load_mesh_terms() raises, validate_mesh degrades to UNVALIDATED (FR-009)."""
        with patch(
            "app.ingestion.mesh.load_mesh_terms",
            side_effect=FileNotFoundError("missing"),
        ):
            validity, canonical = validate_mesh("Warfarin")
        assert validity == MeshValidity.UNVALIDATED
        assert canonical is None

    def test_unvalidated_when_arbitrary_exception(self):
        """Any exception from load_mesh_terms → UNVALIDATED (defensive)."""
        with patch(
            "app.ingestion.mesh.load_mesh_terms",
            side_effect=RuntimeError("disk error"),
        ):
            validity, canonical = validate_mesh("Warfarin")
        assert validity == MeshValidity.UNVALIDATED
        assert canonical is None


class TestLoadMeshTerms:
    """load_mesh_terms() returns a non-empty frozenset of lowercase strings."""

    def test_returns_frozenset(self):
        terms = load_mesh_terms()
        assert isinstance(terms, frozenset)

    def test_non_empty(self):
        terms = load_mesh_terms()
        assert len(terms) > 0

    def test_all_lowercase(self):
        terms = load_mesh_terms()
        for t in terms:
            assert t == t.lower(), f"term {t!r} is not lowercase"

    def test_no_comment_lines_included(self):
        terms = load_mesh_terms()
        for t in terms:
            assert not t.startswith("#"), f"comment line leaked: {t!r}"

    def test_known_term_present(self):
        terms = load_mesh_terms()
        assert "warfarin" in terms
