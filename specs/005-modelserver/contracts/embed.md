# Contract: `POST /embed`

Medical sentence embeddings. Auth: `X-Service-Token` required. Batch ≤ 128. Deterministic.

## Request
```json
{ "texts": ["DrugX is associated with hepatotoxicity in elderly patients", "..."] }
```
- `texts`: array of strings, length `0..128`. `> 128` → `422`. Empty array → `200` with `[]`.
- A single text longer than 512 tokens is truncated (logged warning) and embedded.

## Response `200`
```json
{
  "model_version": {"name": "embedder", "version": "emb-2026.06", "sha256": "<hex>"},
  "dim": 768,
  "results": [
    {"embedding": [0.0123, -0.0456, "... 768 floats ..."],
     "model_version": {"name": "embedder", "version": "emb-2026.06", "sha256": "<hex>"}}
  ]
}
```
- `results` length == `texts` length, **in input order** (FR-003).
- `embedding` is exactly **768** floats, **L2-normalized** (FR-002).
- Every result is stamped with the **embedder** `model_version` so callers (Spec 6) can store it
  with each vector and re-embed on a version change (FR-005b/D9).

## Errors
Same table as `/classify` (`401`/`403`/`422`/`503`).

## Guarantees
- **Deterministic** (FR-004/SC-002): identical text → identical vector.
- **Semantic sanity**: similar clinical passages embed closer (cosine) to each other than to an
  unrelated passage (US2 acceptance #4).
- **No PII / no embeddings in logs** (FR-020/D16).
- **Latency target**: embedder p95 < 150 ms single item; batch ≥ 100 items/sec (FR-021).
