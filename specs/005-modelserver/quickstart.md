# Quickstart: Modelserver — build, run, validate

> Validation/run guide only — implementation lives in `tasks.md` + the code. Assumes the existing
> Vespera stack conventions (Vault dev mode, `uv`, docker-compose). See
> [dev-environment](../../memory/dev-environment.md).

## Prerequisites
- `uv` installed; Docker running.
- Vault dev container up with secrets written (the stack's existing flow), **including
  `modelserver_token`**.
- Model artifacts present under `modelserver/models/` (committed; see D15 — Git LFS if large).

## 1. Train & export the models (offline, one-time)
```bash
uv sync --group training         # torch/transformers — DEV ONLY, never in the serving image
uv run jupyter lab               # run notebooks/01_train_export_modelserver.ipynb
```
The notebook: trains 3 classifier candidates, compares **macro-F1**, ships one, exports
`classifier.*` + `embedder.onnx` + `tokenizer.json`, writes `manifest.json` (with SHA-256s),
`MODEL_CARD.md`, and `eval/eval_set.jsonl`.

## 2. Run the lean serving container
```bash
docker compose up -d --wait vault modelserver
docker compose images modelserver     # confirm image < ~500 MB (Principle VI)
curl -s localhost:<port>/health        # {"status":"ok"} (liveness, no inference)
curl -s localhost:<port>/ready         # 200 + model versions once artifacts hash-validated
```
Tamper check (US4): change a byte in `models/classifier.onnx` → container **refuses to boot**.

## 3. Exercise the contracts
```bash
TOK=<modelserver_token>
# classify
curl -s -X POST localhost:<port>/classify -H "X-Service-Token: $TOK" \
  -H 'content-type: application/json' \
  -d '{"texts":["acute hepatic failure after DrugX","patient tolerated therapy well"]}'
# → results in order; confidence∈[0,1]; is_adverse at cutoff 0.5; each stamped with model_version
# embed
curl -s -X POST localhost:<port>/embed -H "X-Service-Token: $TOK" \
  -H 'content-type: application/json' -d '{"texts":["hepatotoxicity in elderly patients"]}'
# → 768-float vector; model_version stamped
# auth
curl -s -o /dev/null -w "%{http_code}" -X POST localhost:<port>/classify \
  -H 'content-type: application/json' -d '{"texts":["x"]}'   # → 401 (no token)
```

## 4. Run the test suite
```bash
uv sync --group modelserver
VESPERA_INTEGRATION=1 uv run pytest tests/unit/test_manifest_hashing.py \
  tests/unit/test_truncation.py tests/unit/test_version_stamp.py \
  tests/integration/test_classify_contract.py tests/integration/test_embed_contract.py \
  tests/integration/test_auth_and_health.py tests/integration/test_batch_limits.py
```
Expect: deterministic outputs, 768-dim embeddings, batch order preserved, `>128`→422, over-long
text truncated (warned), missing/invalid token → 401/403, `/health` no-inference, cold-start `/ready`.

## 5. Run the eval gate (macro-F1 ≥ 0.80)
```bash
uv run python modelserver/eval/run_eval.py     # prints macro-F1; exits non-zero if < 0.80
```
This is the new CI `eval` job (lean: onnxruntime + numpy, no torch, no network).

## 6. Benchmark the SLOs (FR-021, not CI-gated)
```bash
uv run python modelserver/eval/bench.py        # reports classifier/embedder p95 + batch throughput
```
Targets: classifier p95 < 50 ms, embedder p95 < 150 ms, batch ≥ 100 items/sec on a representative box.

## Success = all spec Success Criteria demonstrable
SC-001 (classify), SC-002 (768-dim deterministic embed), SC-003 (macro-F1 ≥ 0.80 + 3-way comparison
recorded), SC-004 (image < 500 MB, no torch), SC-005 (refuse boot on bad artifact), SC-006 (auth),
SC-008 (no PII/secret in logs), SC-009 (latency/throughput observable).
