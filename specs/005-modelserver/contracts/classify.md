# Contract: `POST /classify`

Adverse-event classification. Auth: `X-Service-Token` required. Batch ≤ 128. Deterministic.

## Request
```json
{ "texts": ["patient developed acute liver failure after starting DrugX", "..."] }
```
- `texts`: array of strings, length `0..128`. `> 128` → `422`. Empty array → `200` with `[]`.
- A single text longer than 512 tokens is truncated (logged `input_truncated` warning) and processed.

## Response `200`
```json
{
  "model_version": {"name": "classifier", "version": "clf-2026.06", "sha256": "<hex>"},
  "results": [
    {"confidence": 0.91, "is_adverse": true,
     "model_version": {"name": "classifier", "version": "clf-2026.06", "sha256": "<hex>"}}
  ]
}
```
- `results` length == `texts` length, **in input order** (FR-003).
- `confidence` ∈ `[0,1]`; `is_adverse` = `confidence >= 0.5` (documented default cutoff — FR-001).
- Callers MAY ignore `is_adverse` and apply their own threshold to `confidence` (decision policy is
  the caller's; e.g., a fail-safe triage cutoff).
- Every result is stamped with the **classifier** `model_version` (FR-005b/D9).

## Errors
| Status | When |
|--------|------|
| `401` | missing `X-Service-Token` |
| `403` | invalid `X-Service-Token` |
| `422` | malformed body / `> 128` items |
| `503` | service not ready (cold start, before artifacts validated) |

## Guarantees
- **Deterministic** (FR-004): identical request → identical `confidence`/`is_adverse`.
- **No PII in logs** (FR-020): only `operation`, `batch_size`, `latency_ms`, `model_version`,
  `truncated_count`.
- **Latency target**: classifier p95 < 50 ms single item (FR-021, observable, not CI-gated).
