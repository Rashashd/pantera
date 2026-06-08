# Contract: Model manifest — `modelserver/models/manifest.json`

The committed source of truth for which artifacts are served, their integrity hashes, and their
shapes. Loaded and enforced at startup (D4/FR-010).

## Schema
```json
{
  "artifacts": [
    {"name": "classifier", "file": "classifier.onnx", "format": "onnx",
     "version": "clf-2026.06", "sha256": "<hex>"},
    {"name": "embedder", "file": "embedder.onnx", "format": "onnx",
     "version": "emb-2026.06", "sha256": "<hex>", "dim": 768, "max_tokens": 512},
    {"name": "tokenizer", "file": "tokenizer.json", "format": "tokenizer",
     "version": "emb-2026.06", "sha256": "<hex>"}
  ]
}
```

## Rules
- Every served file MUST have a manifest entry; every manifest entry's file MUST exist.
- At startup the service computes SHA-256 of each `file` and compares to `sha256`. Any
  mismatch/absence → **refuse to boot** (no partial serving — Edge Case "Partial artifacts").
- `dim` (embedder) MUST equal **768**; `max_tokens` MUST equal **512**.
- The `sha256` (+ `version`) is the **model-version identifier** returned in responses (D9/FR-005b).
- `MODEL_CARD.md` MUST carry the same hashes (human-auditable mirror, FR-011).
- A model upgrade = new artifact + new `sha256` + manifest/card bump (a reviewed change), surfaced to
  callers via the response `model_version`.
