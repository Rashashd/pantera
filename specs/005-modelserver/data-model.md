# Phase 1 Data Model: Modelserver

> **The modelserver is stateless — there is NO database and NO Alembic migration.** "Entities" here
> are on-disk artifacts, the committed manifest, the request/response payloads, and the eval/threshold
> files. Embeddings are *persisted* by Spec 6, not here.

## Artifact entities (on disk, in the image)

### Classifier artifact
- **File**: `modelserver/models/classifier.onnx` *or* `classifier.joblib` (format per D2).
- **Produces**: adverse-event detection — raw confidence in `[0,1]`.
- **Identity**: SHA-256 (recorded in `manifest.json` + `MODEL_CARD.md`).
- **Validation**: hash must match manifest at startup, else refuse boot.

### Embedder artifact
- **File**: `modelserver/models/embedder.onnx` (+ `tokenizer.json`).
- **Produces**: fixed **768-dim** L2-normalized vector per input.
- **Identity**: SHA-256 (manifest + card). `dim = 768`, `max_tokens = 512`.
- **Validation**: hash match at startup (both the ONNX and the tokenizer file are hashed).

### Model card
- **File**: `modelserver/models/MODEL_CARD.md`.
- **Contents (required, FR-011)**: task; dataset pinned by version/hash; 3-way macro-F1 comparison
  (classical / PubMedBERT-ONNX / LLM zero-shot); shipped choice + rationale; per-artifact SHA-256;
  embedder output shape (768) + max tokens (512).

## Manifest (committed) — `modelserver/models/manifest.json`

| Field | Type | Notes |
|-------|------|-------|
| `artifacts[]` | array | one entry per served artifact |
| `artifacts[].name` | string | `classifier` \| `embedder` \| `tokenizer` |
| `artifacts[].file` | string | filename under `models/` |
| `artifacts[].format` | string | `onnx` \| `joblib` \| `tokenizer` |
| `artifacts[].version` | string | human tag, e.g. `clf-2026.06` |
| `artifacts[].sha256` | string | expected hex digest (startup-validated) |
| `artifacts[].dim` | int? | embedder only → `768` |
| `artifacts[].max_tokens` | int? | model max input → `512` |

The **model-version identifier** returned in responses (FR-005b) = the relevant artifact's `sha256`
(plus `version` tag) — classifier vs embedder reported separately (D9).

## Request / response payloads (validated Pydantic, batch ≤ 128)

### Classification
- **Request**: `{ "texts": [string, ...] }` — `1..128` items (empty list allowed → empty result).
- **Result per item**: `{ "confidence": float[0..1], "is_adverse": bool (confidence ≥ 0.5),
  "model_version": {"name":"classifier","version":string,"sha256":string} }`.
- **Rules**: deterministic; decision computed at the documented default cutoff `0.5`; callers may
  re-threshold the raw `confidence` (decision policy is the caller's — FR-001).

### Embedding
- **Request**: `{ "texts": [string, ...] }` — `1..128` items (empty list allowed → empty result).
- **Result per item**: `{ "embedding": float[768], "model_version":
  {"name":"embedder","version":string,"sha256":string} }`.
- **Rules**: deterministic; exactly 768 dims; L2-normalized.

### Validation & errors
| Condition | Behavior |
|-----------|----------|
| `> 128` items | `422` validation error (FR-003/FR-005) |
| empty/malformed body | `422` (never a fabricated result) |
| single text `> 512` tokens | truncated to 512, processed, `warning` logged (FR-005a) |
| missing service token | `401` |
| invalid service token | `403` |
| artifact hash mismatch/absent | service refuses to boot (no requests served) |

## Evaluation entities

### Eval set — `modelserver/eval/eval_set.jsonl`
- One JSON object per line: `{ "text": string, "label": 0|1 }` (held-out; not used in training).

### Thresholds — `eval_thresholds.yaml` (repo root, NEW)
```yaml
classifier:
  metric: macro_f1
  min: 0.80   # spec FR-013 / SC-003 (initial committed floor)
```

## Observability fields (logs/metrics, no PII)
`operation` (`classify`|`embed`), `batch_size`, `latency_ms`, `model_version`, `truncated_count`,
`auth_result`. **Never** `texts`, `embedding`, token, or any PII (D16/FR-020/SC-008).

## Relationships / lifecycle
- Stateless request→response; **no persistence, no `client_id`** (isolation preserved by storing
  nothing — Principle V).
- Artifact lifecycle: trained offline → exported → hashed into manifest → committed → hash-validated
  at boot → served. A new model = new artifact + new sha256 + manifest/card update → callers detect
  the version change (D9) and refresh downstream (Spec 6 re-embed).
