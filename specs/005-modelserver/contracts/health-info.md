# Contract: `GET /health` (liveness) & `GET /ready` (readiness + versions)

## `GET /health` — liveness
- **No auth, no inference.** Mirrors `app/api/health.py`.
- `200` → `{"status": "ok"}` as soon as the process is up.
- Used by the PaaS/compose liveness probe.

## `GET /ready` — readiness
- `200` **only after** both artifacts are loaded and their SHA-256 validated against the manifest;
  `503` during cold start (before validation completes) — FR-017/CHK034.
- Body includes the served model versions (so operators/callers can confirm what's live):
```json
{
  "status": "ready",
  "models": {
    "classifier": {"version": "clf-2026.06", "sha256": "<hex>", "format": "onnx"},
    "embedder":   {"version": "emb-2026.06", "sha256": "<hex>", "dim": 768, "max_tokens": 512}
  }
}
```
- Optionally exposes rolling latency/throughput counters (p50/p95 per operation) for FR-021
  observability.

## Startup behavior (not an endpoint, but contract-relevant)
- On boot: load `modelserver_token` from Vault (refuse boot if empty); compute each artifact's
  SHA-256 and compare to `manifest.json`; **refuse to boot on mismatch or absence** (FR-010/US4).
- Until `/ready` returns `200`, `/classify` and `/embed` return `503`.
