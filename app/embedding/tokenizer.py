"""Tokenizer loading and token counting utilities."""

from pathlib import Path

from tokenizers import Tokenizer  # type: ignore

from app.core.config import Settings
from app.infra.modelserver_client import ModelserverClient


class TokenizerError(Exception):
    """Raised on tokenizer loading or verification failures."""

    pass


class EmbedderTokenizer:
    """Load and use the embedder's tokenizer for accurate token counting (FR-025)."""

    def __init__(self, tokenizer_path: str) -> None:
        """Load the tokenizer from tokenizer.json."""
        path = Path(tokenizer_path)
        if not path.exists():
            raise TokenizerError(f"Tokenizer not found at {tokenizer_path}")
        try:
            self.tokenizer = Tokenizer.from_file(str(path))
        except Exception as e:
            raise TokenizerError(f"Failed to load tokenizer from {tokenizer_path}: {e}") from e

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using the embedder's tokenizer + special-token reserve (FR-025)."""
        # Encode without special tokens so the +2 reserve isn't double-counted when the
        # tokenizer (e.g. BiomedBERT) already adds CLS/SEP in its encode() output.
        tokens = self.tokenizer.encode(text, add_special_tokens=False)
        return len(tokens.ids) + 2


async def verify_served_model_versions(client: ModelserverClient, settings: Settings) -> None:
    """Verify the modelserver's reported artifact hashes match the pinned versions (FR-025 / H1).

    Checks the embedder, classifier, and reranker /ready SHA-256s against their config pins in a
    SINGLE /ready call. A pin of "" skips that artifact (and if nothing is pinned, /ready is not
    called). Raises TokenizerError on a mismatch or a missing reported hash so the caller can fail
    the run — the modelserver is serving an UNEXPECTED model version (the modelserver self-validates
    its files at its own boot; this catches a wrong *version* being served to this app).
    """
    pins = {
        "embedder": settings.embedder_model_version,
        "classifier": settings.classifier_model_version,
        "reranker": settings.reranker_model_version,
    }
    if not any(pins.values()):
        return
    ready_json = await client.get_ready()
    models = ready_json.get("models", {})
    for name, expected in pins.items():
        if not expected:
            continue
        actual = models.get(name, {}).get("sha256")
        if not actual:
            raise TokenizerError(f"{name} version not reported by modelserver /ready")
        if actual != expected:
            raise TokenizerError(f"{name} version mismatch: expected {expected}, got {actual}")
