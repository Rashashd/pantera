# Implementation Plan: Modelserver — Adverse-Event Classifier & Medical Embedder

**Branch**: `005-modelserver` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-modelserver/spec.md`

## Summary

Stand up Vespera's first **separate inference container** and first **evaluation gate**. The
modelserver is a lean, stateless FastAPI service that exposes exactly two inference capabilities
over authenticated service-to-service HTTP/JSON: (1) **adverse-event classification** — returns a
raw confidence in `[0,1]` plus a YES/NO at a documented default cutoff of `0.5`, decision policy
owned by the caller; and (2) **medical embeddings** — returns fixed **768-dim** vectors for
biomedical text. Both accept batches up to **128** items, are **deterministic**, stamp every
result with a **model-version identifier** (artifact SHA-256), and truncate over-long single texts
to the model max (**512 tokens**) as a logged safety net (chunking is the caller's / Spec 6's job).

Models are **trained offline** (a notebook, comparing classical / PubMedBERT-ONNX / LLM zero-shot
on **macro-F1**, shipping exactly one and defending it in `DECISIONS.md`) and **served lean**: the
serving image runs only `onnxruntime` + `numpy` + a no-torch fast `tokenizers` (+ `sklearn` only if
a classical model ships) — **no torch**, image target **< 500 MB**. At startup the service
validates each artifact's **SHA-256** against a committed manifest and **refuses to boot** on
mismatch/absence; every request requires a **service credential** (`modelserver_token`) fetched
from Vault. A committed **`eval_thresholds.yaml`** + a CI eval job enforce **macro-F1 ≥ 0.80** on a
held-out set, blocking merges on regression. A thin reusable caller (`app/infra/modelserver_client.py`,
`httpx` + `tenacity`) satisfies the FR-019 calling contract and lets later specs (Spec 6 embedding,
triage) consume the service unchanged. The modelserver is **stateless** — no database, **no
migration**, no per-client data — so multi-tenant isolation is preserved by storing nothing and
never logging payloads/PII.

## Technical Context

**Language/Version**: Python 3.12+ (managed by `uv`).

**Primary Dependencies**:
- *Serving (lean, new container — a self-contained `modelserver` uv group)*: FastAPI, uvicorn,
  **onnxruntime**, **numpy**, **tokenizers** (HuggingFace Rust tokenizers — no torch), Pydantic v2,
  pydantic-settings, structlog, `hvac` (Vault), `secure`. **No torch, no transformers at serve
  time.** `scikit-learn` is included **only if** the shipped classifier is the classical model
  (served via joblib); a transformer classifier is served via ONNX and needs no sklearn. The image
  installs **only this group, excluding the app's own dependencies** —
  `uv sync --only-group modelserver --no-install-project` (see research D1; `--only-group` is
  required so the api's heavy deps don't leak into the lean image).
- *Offline training (dev-only group, NEVER in the serving image)*: jupyter, **torch**,
  **transformers**, **optimum[onnxruntime]**, **datasets**, scikit-learn, skl2onnx, evaluate.
- *Caller side (existing app)*: `httpx` (already a runtime dep), `tenacity` (already present).

**Storage**: **None.** The modelserver is stateless — no Postgres, no Redis, **no Alembic
migration**. Model artifacts, tokenizer, and a manifest ship on disk inside the image. (Embeddings
are *stored* later by Spec 6; this spec only produces them.)

**Testing**: `uv run pytest`. Unit tests cover identifier/manifest/hashing/truncation/version
logic and the caller client with a stubbed transport. Service tests run the modelserver app
in-process (ASGI transport) against **tiny committed fixture artifacts** (a tiny ONNX/joblib model
+ tokenizer) so CI needs no large download and no network. A dedicated **eval** step scores the
shipped classifier's ONNX on a committed held-out set and asserts macro-F1 ≥ 0.80.

**Target Platform**: Linux container — a **new `modelserver` service** in the existing
docker-compose modular monolith, alongside `vault`/`postgres`/`redis`/`api`/`worker`.

**Project Type**: Web service (modular monolith) + one justified separate inference container.

**Performance Goals**: On a lean CPU (no-torch) container — **classifier p95 < 50 ms**, **embedder
p95 < 150 ms** for single-item inference; **batch throughput ≥ 100 items/sec**. Per-operation
latency/throughput exposed as observable metrics; verified via a benchmark script (not hard-gated
in CI to avoid runner-variance flakiness — see research D11).

**Constraints**: No torch / ONNX-only serving (Principle VI); image **< ~500 MB**; **deterministic**
inference (fixed CPU provider, no sampling); batch cap **128**; max input **512 tokens** (truncate
with warning); **service-credential auth** on every request; **startup SHA-256 validation** refuses
boot on mismatch/absence; `structlog` with **no payloads/PII/secrets** in logs; files ≤ ~300 lines
with a one-sentence docstring; classifier-path coverage ≥ 95%, overall ≥ 80%.

**Scale/Scope**: Moderate. Batches ≤ 128/request; callers split larger jobs. Two artifacts
(classifier + embedder). One new container, one new caller client, one new thresholds file, CI
additions (Vault secret + eval job). No DB changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Relevance | Status |
|-----------|-----------|--------|
| I. Human-in-the-Loop | No drafting/sending; pure inference. Caller owns the YES/NO cutoff (decision policy out of the model service) | ✅ N/A |
| II. Grounding | No reports/claims; produces the classifier signal + embeddings later grounding depends on | ✅ N/A (enabling) |
| III. Triage Fails Safe | Returns raw confidence so the later triage cutoff can be tuned toward escalation; modelserver does not bake a policy | ✅ Enabling |
| IV. Backed by a Number | **Realizes this principle**: introduces `eval_thresholds.yaml` + the macro-F1 ≥ 0.80 gate; 3-way classifier comparison defended in `DECISIONS.md`; classifier-path ≥ 95% coverage | ✅ Central |
| V. Multi-Tenant Isolation (NON-NEGOTIABLE) | Service is **stateless** — stores nothing, no `client_id` data, processes only the text passed in; **never logs payloads/PII**; cannot leak across tenants because it persists nothing | ✅ Enforced |
| VI. Lean, Reproducible, Justified | **No torch in serving** (onnxruntime/numpy/tokenizers only), image < 500 MB; the separate container is an explicitly-allowed justified service (no-torch tech constraint); torch/transformers confined to the offline training group; **no MCP**; `uv` lockfile | ✅ Aligned |
| VII. Own Every Line (Spec-Driven) | spec → clarify×2 → checklist → plan → tasks → implement; Conventional Commits; PRs < 400 lines (training/export, serving, caller+CI as separate PRs) | ✅ Aligned |

**Security & startup standards applied**: `modelserver_token` fetched from Vault at startup (no
secret on disk/in image/in logs); **startup validation refuses to boot** on artifact SHA-256
mismatch/absence (satisfies the constitution's startup-validation requirement); service-credential
checked with a constant-time compare; security headers via `secure` middleware; caller calls
wrapped in `tenacity` (timeout, no retry on 4xx).

**Guardrails note (tracked deferral, not a violation)**: The constitution mandates the NeMo
Guardrails sidecar on **external/LLM-facing** calls. The modelserver runs **local ONNX inference**
on text the platform already holds — it is not an LLM and makes no external/LLM call. Injection
scanning (NeMo) and PII redaction (Presidio) interpose in their own later specs before text reaches
an LLM/agent; this service stores nothing and keeps payloads out of logs.

**Result**: PASS — no violations. Complexity Tracking table intentionally empty (the new container
and the offline torch dependency are explicitly sanctioned by Principle VI).

## Project Structure

### Documentation (this feature)

```text
specs/005-modelserver/
├── plan.md              # This file
├── research.md          # Phase 0 output (design decisions D1–D16)
├── data-model.md        # Phase 1 output (artifact/manifest/contract entities — NO DB tables)
├── quickstart.md        # Phase 1 output (build/run/validate guide)
├── contracts/           # Phase 1 output
│   ├── classify.md          # POST /classify request/response contract
│   ├── embed.md             # POST /embed request/response contract
│   ├── health-info.md       # GET /health (liveness) + GET /ready|/info (readiness + versions)
│   ├── model-manifest.md    # committed manifest schema (id, version, sha256, dim, max_tokens)
│   └── modelserver-client.md# the app-side caller contract (httpx + tenacity, FR-019)
├── checklists/
│   ├── requirements.md      # spec-quality gate (from /speckit-specify)
│   └── quality.md           # requirements QA (from /speckit-checklist)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

A new lean **`modelserver/`** container, an offline **`notebooks/`** training/export workflow that
emits the artifacts + `MODEL_CARD.md` + the eval golden set, a new repo-root **`eval_thresholds.yaml`**,
a thin **caller client** under `app/infra/`, a new docker-compose service + Dockerfile, and CI
additions (Vault secret + eval job). No existing app module changes except the additive caller
client, `Settings` already carrying `modelserver_token`, and CI.

```text
modelserver/                          # NEW lean container (onnxruntime + numpy + tokenizers; NO torch)
├── pyproject-marker NOTE             # deps declared as a uv group "modelserver"; installed alone in image
├── main.py                           # FastAPI app + lifespan (load+validate artifacts, load token)
├── config.py                         # pydantic-settings (vault addr/token, model dir, batch/token caps)
├── startup.py                        # load_secret(modelserver_token) + SHA-256 verify vs manifest → refuse boot
├── auth.py                           # service-credential dependency (constant-time compare)
├── inference/
│   ├── classifier.py                 # onnxruntime/sklearn session; predict → (confidence, decision)
│   ├── embedder.py                   # tokenizer + onnxruntime session; mean-pool → 768-dim vector
│   └── tokenize.py                   # shared no-torch tokenization + 512-token truncation (warns)
├── schemas.py                        # Pydantic request/response (batch ≤128, version-stamped results)
├── routes.py                         # POST /classify, POST /embed, GET /health, GET /ready
├── manifest.py                       # load committed manifest; expose model-version identifiers
├── models/
│   ├── classifier.onnx (or .joblib)  # shipped adverse-event detector
│   ├── embedder.onnx                 # medical sentence embedder (768-dim)
│   ├── tokenizer.json                # fast tokenizer (no torch) for the embedder/transformer
│   ├── manifest.json                 # {name, version, sha256, dim, max_tokens} per artifact
│   └── MODEL_CARD.md                 # task, dataset(pinned), 3-way comparison, choice, SHA-256
├── eval/
│   ├── eval_set.jsonl                # committed held-out examples (text + label)
│   └── run_eval.py                   # load classifier.onnx, score macro-F1, compare to threshold
└── Dockerfile                        # lean image: install ONLY the modelserver uv group

notebooks/                            # NEW offline training/export (torch/transformers — dev only)
└── 01_train_export_modelserver.ipynb # train 3 candidates, compare macro-F1, export ONNX + card + hashes

app/infra/
└── modelserver_client.py            # NEW thin async client (httpx + tenacity, timeout, token header)

eval_thresholds.yaml                  # NEW (repo root) — first committed eval gate; classifier macro-F1 ≥ 0.80

docker-compose.yml                    # ADD: modelserver service (build Dockerfile, VAULT_ADDR/TOKEN env, port)
pyproject.toml                        # ADD: uv group "modelserver" (serving) + group "training" (offline)

.github/workflows/ci.yml              # ADD: modelserver_token to inline Vault writer; NEW eval job (macro-F1)

tests/
├── unit/
│   ├── test_manifest_hashing.py      # sha256 compute/compare; boot-refusal on mismatch/absence
│   ├── test_truncation.py            # >512 tokens truncates + warns; ≤512 untouched
│   ├── test_version_stamp.py         # every result carries the correct model-version id
│   └── test_modelserver_client.py    # caller: token header, timeout, retry-not-on-4xx (stub transport)
└── integration/
    ├── test_classify_contract.py     # batch order, [0,1] confidence, default-0.5 decision, determinism
    ├── test_embed_contract.py        # 768-dim, determinism, batch order, empty-batch, semantic sanity
    ├── test_auth_and_health.py       # missing/invalid token → 401/403; /health no-inference; /ready gating
    └── test_batch_limits.py          # >128 items rejected; cold-start readiness; over-long truncation path
```

**Structure Decision**: Keep the serving container **physically separate and lean** (`modelserver/`)
with its own minimal dependency set so torch never enters the inference image (Principle VI). Train
**offline** in `notebooks/` using torch/transformers confined to a dev-only `training` uv group; the
notebook emits portable artifacts (`*.onnx`/`*.joblib` + `tokenizer.json`), a `manifest.json` with
SHA-256s, a `MODEL_CARD.md`, and the committed `eval/eval_set.jsonl`. Serving loads + hash-validates
those artifacts at startup. The caller surface is a single reusable `app/infra/modelserver_client.py`
so Spec 6 and the triage spec consume the contract unchanged. The eval gate (`eval_thresholds.yaml`
+ `modelserver/eval/run_eval.py`) is the project's first realization of Principle IV and runs as a
new CI job using only onnxruntime+numpy (lean, reproducible, no torch).

## Complexity Tracking

> No constitution violations — table intentionally empty. The separate `modelserver` container and
> the offline torch/transformers dependency are explicitly **sanctioned** by Principle VI (no-torch
> *serving*; training offline). Serving deps are deliberately minimal (onnxruntime + numpy +
> tokenizers) and image size is gated (< ~500 MB) to keep the sanctioned container honest.
