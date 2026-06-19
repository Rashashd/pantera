"""Model-integrity boot validation (Cluster 2 / H1): check_model_artifacts must REFUSE boot on a
missing or mismatched app-local artifact (embedder tokenizer SHA, NER package version)."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.startup import ModelIntegrityError, check_model_artifacts

_REAL_TOKENIZER_PATH = "modelserver/models/tokenizer.json"
_REAL_TOKENIZER_SHA = "9355eae89d401cee6b1f7c9acaf4791191e3b22c918e5f616b6baea13b66e748"


def _settings(**overrides) -> SimpleNamespace:
    """Settings-like object with the real pinned defaults; override per test."""
    base = {
        "embedder_tokenizer_path": _REAL_TOKENIZER_PATH,
        "embedder_tokenizer_sha256": _REAL_TOKENIZER_SHA,
        "ner_model_version": "0.5.4",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_passes_with_real_artifacts():
    """Real tokenizer.json (matching SHA) + installed NER 0.5.4 → no raise (happy path)."""
    check_model_artifacts(_settings())


def test_refuses_on_tokenizer_sha_mismatch():
    """A tokenizer whose SHA-256 != the pin refuses boot (swapped/tampered artifact)."""
    with pytest.raises(ModelIntegrityError, match="SHA-256 mismatch"):
        check_model_artifacts(_settings(embedder_tokenizer_sha256="deadbeef", ner_model_version=""))


def test_refuses_on_missing_tokenizer():
    """A missing tokenizer artifact refuses boot (absence)."""
    with pytest.raises(ModelIntegrityError, match="missing"):
        check_model_artifacts(
            _settings(embedder_tokenizer_path="/no/such/tokenizer.json", ner_model_version="")
        )


def test_refuses_on_ner_version_mismatch():
    """A NER package whose version != the pin refuses boot (wrong/swapped model)."""
    with pytest.raises(ModelIntegrityError, match="version mismatch"):
        check_model_artifacts(_settings(embedder_tokenizer_sha256="", ner_model_version="9.9.9"))


def test_refuses_on_missing_ner():
    """An absent NER package refuses boot."""
    with patch(
        "app.core.startup.importlib_metadata.version",
        side_effect=importlib_metadata.PackageNotFoundError("en_ner_bc5cdr_md"),
    ):
        with pytest.raises(ModelIntegrityError, match="not installed"):
            check_model_artifacts(_settings(embedder_tokenizer_sha256=""))


def test_skips_when_pins_empty():
    """Empty pins disable the check — even a bogus path/version does not raise (no-op)."""
    check_model_artifacts(
        _settings(
            embedder_tokenizer_sha256="",
            ner_model_version="",
            embedder_tokenizer_path="/no/such/tokenizer.json",
        )
    )
