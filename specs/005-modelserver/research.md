# Phase 0 Research: Modelserver

Design decisions resolving the Technical Context and the spec's clarified points. Each entry:
**Decision / Rationale / Alternatives considered**. These bind the Phase 1 contracts and the tasks.

---

## D1 — Lean dependency isolation (keep torch out of the serving image)

**Decision**: Declare two new `uv` dependency groups in the root `pyproject.toml`: a **`modelserver`**
group and a **`training`** group. The `modelserver` group is **self-contained** and enumerates the
FULL serving dependency set (it must, because the image excludes the main app deps): `fastapi`,
`uvicorn`, `onnxruntime`, `numpy`, `tokenizers`, `pydantic`, `pydantic-settings`, `structlog`,
`hvac`, `secure` (add `scikit-learn` only if a classical classifier ships). The `training` group is
offline-only: `torch`, `transformers`, `optimum[onnxruntime]`, `datasets`, `scikit-learn`, `skl2onnx`,
`evaluate`, `jupyter`. `modelserver/Dockerfile` installs **only that group, excluding the project's
own dependencies**, via **`uv sync --only-group modelserver --no-install-project`**. The `api`/`worker`
images are unchanged and install neither group.

**Rationale**: One lockfile (reproducible), one source of truth, and a **truly lean** serving image.
`--only-group` is the key: a plain `--no-default-groups --group modelserver` would STILL install the
project's `[project].dependencies` (sqlalchemy, asyncpg, arq, fastapi-users, sentry, slowapi, …) and
bloat the image — violating FR-009 / Principle VI. `--only-group … --no-install-project` installs
*only* the enumerated serving deps, so the group must list everything serving needs (hence the full
enumeration above, including `pydantic-settings`/`structlog`/`hvac`/`secure`). torch is provably
absent. Image-size gate (< ~500 MB) keeps it honest.

**Alternatives considered**: (a) `--no-default-groups --group modelserver` — **rejected**: still
pulls the whole app dependency set into the serving image. (b) A separate `modelserver/pyproject.toml`
+ its own lock — cleanest isolation but two lockfiles to drift; acceptable fallback if the
single-lock `--only-group` approach proves awkward. (c) Adding onnxruntime to the root `dependencies`
— would bloat the api/worker images; rejected.

---

## D2 — Classifier: train three, ship one, serve lean

**Decision**: Offline notebook trains and compares the three candidates on the **same held-out split**
with **macro-F1**: (1) classical (TF-IDF + LogisticRegression/LinearSVC), (2) PubMedBERT fine-tune →
ONNX, (3) LLM zero-shot baseline (eval-only, no shipped artifact). Ship exactly one; record all three
numbers in `MODEL_CARD.md` and defend the choice in `DECISIONS.md`. A classical model is served via
`joblib` + `scikit-learn`; a transformer is served via `onnxruntime`. Either way the artifact's
SHA-256 is recorded.

**Rationale**: Required by Principle IV and spec US3/FR-012. ADE Corpus v2 is small and well-studied;
a classical baseline often clears macro-F1 ≥ 0.80 and keeps the image tiny — but the comparison decides.

**Alternatives considered**: Shipping a transformer unconditionally (heavier image, may need
quantization to stay < 500 MB); skipping the LLM baseline (loses a defensible comparison point).

---

## D3 — Embedder: BiomedBERT → ONNX, tokenized with the no-torch `tokenizers` lib

**Decision**: Export a BiomedBERT/PubMedBERT-class sentence encoder to ONNX offline (via
`optimum`), with **mean-pooling** over token embeddings to a fixed **768-dim** vector (L2-normalized
for stable cosine similarity). At serve time, tokenize with the HuggingFace **`tokenizers`** Rust
library (ships `tokenizer.json`; **no torch/transformers**), run onnxruntime, mean-pool in numpy.

**Rationale**: Lets the serving image embed BERT text without torch/transformers. 768 dims is the
standard for this model family and is pinned for Spec 6's `vector(768)` column (spec clarification).
L2-normalization makes determinism + similarity checks clean.

**Alternatives considered**: `sentence-transformers` at serve time (pulls torch — violates Principle
VI); a general-purpose embedding API (violates the "no external embedding API" design rationale).

---

## D4 — Artifact integrity: committed manifest + startup SHA-256 validation

**Decision**: Ship `modelserver/models/manifest.json` listing, per artifact: `name`, `version`
(human tag, e.g. `clf-2026.06`), `sha256`, `dim` (embedder), `max_tokens` (512), and `format`
(`onnx`/`joblib`). At startup the service computes each file's SHA-256 and compares to the manifest;
on **mismatch or absence it raises and refuses to boot** (mirrors the app's existing
`run_startup_checks` refuse-to-boot pattern). `MODEL_CARD.md` carries the same hashes for humans.

**Rationale**: Directly satisfies the constitution's startup-validation requirement and spec
FR-010/US4. A committed manifest makes the expected hash auditable and review-diffable.

**Alternatives considered**: Hard-coding hashes in Python (less reviewable); skipping validation
(violates the constitution).

---

## D5 — Service-credential auth via Vault `modelserver_token`

**Decision**: The modelserver loads `modelserver_token` from Vault at startup (the `Settings` field
and `load_secrets_from_vault` mapping already exist in `app/core`). Every `/classify` and `/embed`
request must present it (header `X-Service-Token`, validated with `hmac.compare_digest`). Missing →
**401**, present-but-wrong → **403**. The token is a **required** secret for the *modelserver*
(refuse boot if empty); the api/worker only need it when they call (Spec 6+).

**CI impact**: Add `"modelserver_token": "ci-test-token"` to the inline Vault writer in `ci.yml` so
the modelserver can boot in CI (per the project's "new required secret ⇒ update ci.yml writer" lesson).
The app `_REQUIRED_SECRETS` tuple is **not** changed (the api doesn't call modelserver in this spec).

**Rationale**: Reuses the established Vault/hvac path; no new secret mechanism. Constant-time compare
prevents timing attacks.

**Alternatives considered**: mTLS (overkill for in-compose service-to-service); no auth (violates
FR-015 and constitution service-to-service auth).

---

## D6 — Determinism

**Decision**: Pin `onnxruntime` to the **CPUExecutionProvider**, set intra/inter-op threads
deterministically, no dropout/sampling at inference, fixed tokenizer config, L2-normalized
embeddings. Document that identical input → identical output bytes.

**Rationale**: FR-004/SC-002 require determinism; it also makes contract tests exact-match.

**Alternatives considered**: GPU provider (non-deterministic across hardware, and torch/GPU is
out of scope — see D-future).

---

## D7 — Endpoints, transport & health/readiness (resolves CHK047)

**Decision**: HTTP/JSON REST (FastAPI), matching the rest of the platform. Endpoints:
`POST /classify`, `POST /embed`, `GET /health` (liveness — returns `{"status":"ok"}` with **no**
inference, mirroring `app/api/health.py`), `GET /ready` (returns `200` only after artifacts are
loaded + hash-validated; `503` during cold start) and includes the model-version identifiers.

**Rationale**: Consistent with the platform; separates liveness from readiness (FR-017, CHK034).

**Alternatives considered**: gRPC (extra dependency/tooling, no benefit at this scale).

---

## D8 — Batch (≤128) + over-long truncation (512 tokens)

**Decision**: Requests accept a list of up to **128** texts; **> 128 → 422** validation error
(Pydantic `max_length`). Each text is tokenized with `truncation=True, max_length=512`; when the
**pre-truncation** token count exceeds 512 the service emits a structured `warning`
(`event="input_truncated"`, with counts but **not** the text) and proceeds on the truncated text.
Empty list → empty result `200`.

**Rationale**: Spec FR-003/FR-005/FR-005a clarifications; chunking is the caller's/Spec 6's job, the
modelserver only protects itself.

**Alternatives considered**: Rejecting over-long text (breaks the "never crash, callers own chunking"
contract); silent truncation (loses observability).

---

## D9 — Model-version identifier in every response (resolves CHK048)

**Decision**: Responses are **per-result version-stamped**. `/classify` results each carry
`model_version` = the **classifier** artifact's `sha256` (and human `version` tag); `/embed` results
each carry `model_version` = the **embedder** artifact's identifiers. The top-level response also
echoes the relevant `model_version` once for convenience. Classifier and embedder versions are
**reported separately** (they are distinct artifacts).

**Rationale**: FR-005b; lets Spec 6 persist the embedder version alongside each vector and re-embed
when it changes; strengthens auditability. Per-result keeps batches unambiguous.

**Alternatives considered**: Version only on the health endpoint (callers can't bind it to a stored
result — CHK048 gap); a single merged version (conflates two independently-upgradable artifacts).

---

## D10 — Eval gate: `eval_thresholds.yaml` + `run_eval.py` + CI job

**Decision**: Create repo-root **`eval_thresholds.yaml`** (the project's first) with
`classifier: { metric: macro_f1, min: 0.80 }`. `modelserver/eval/run_eval.py` loads the shipped
classifier artifact (onnxruntime/joblib), scores **macro-F1** on committed `eval/eval_set.jsonl`,
prints the number, and **exits non-zero if below threshold**. A new CI job (`eval`) installs only the
lean `modelserver` group and runs it — **no torch, no network**, reproducible.

**Rationale**: Principle IV + spec FR-013/US5/SC-007. Scoring the *exported* artifact (not retraining)
keeps CI lean and reproducible.

**Alternatives considered**: Retraining in CI (slow, needs torch — rejected); hard-coding the number
in a test (not a committed, tunable threshold).

---

## D11 — Performance SLOs: measure & expose, benchmark-verify, don't hard-gate in CI

**Decision**: Bind per-request latency in `structlog` and expose simple counters/timers (operation,
count, p50/p95 from a rolling window) via the `/ready`/info payload or a lightweight `/metrics`.
Provide `quickstart.md` benchmark steps that assert classifier p95 < 50 ms, embedder p95 < 150 ms,
batch ≥ 100/s on a representative box. **Do not** hard-fail CI on p95 (shared runners vary), but the
benchmark is a documented, repeatable SLO check.

**Rationale**: FR-021/SC-009 require the targets be *observable and verifiable*; CI latency gating is
notoriously flaky on shared runners.

**Alternatives considered**: Hard p95 CI gate (flaky false-failures); no measurement (FR-021 unmet).

---

## D12 — Max input length = 512 tokens (resolves CHK046)

**Decision**: Fix the model max input at **512 tokens** (BERT-family standard), recorded in
`manifest.json` (`max_tokens`) and used by the tokenizer truncation in D8. Truncation tests assert at
this boundary.

**Rationale**: Makes FR-005a testable; matches the embedder/classifier architecture.

**Alternatives considered**: Leaving it model-implicit (untestable — CHK046 gap).

---

## D13 — Caller client (`app/infra/modelserver_client.py`) (satisfies FR-019)

**Decision**: A thin async client using `httpx.AsyncClient` (reuse `app/infra/http.py` factory) +
`tenacity` (timeout, ≤3 exponential retries, **never on 4xx**), sending the `X-Service-Token`, with
typed Pydantic returns. It is the single reusable surface later specs consume; this spec adds it and
unit-tests it against a stub transport but does **not** wire it into the api request path (that's
Spec 6/triage).

**Rationale**: FR-019 is a requirement on callers; shipping the client now proves the contract and
prevents each later spec from re-inventing it.

**Alternatives considered**: Deferring the client entirely (FR-019 unverified; risk of inconsistent
re-implementation later).

---

## D14 — Reliability/availability (resolves CHK040)

**Decision**: **No formal uptime SLO** for the capstone. The service is **stateless and restartable**;
resilience is the caller's responsibility via timeout + bounded retry (D13/FR-019). Documented as an
intentional scope decision.

**Rationale**: Appropriate for the build's scope; statelessness makes restart cheap and safe.

**Alternatives considered**: An uptime SLO + HA (out of scope for a single-node capstone).

---

## D15 — Artifact distribution from a fresh clone

**Decision**: Commit the artifacts under `modelserver/models/` so `docker compose up` works from a
fresh clone. Keep them small: prefer the classical classifier if competitive; **quantize** the
embedder ONNX (dynamic INT8 via onnxruntime) to shrink it. If any artifact exceeds GitHub's 100 MB
limit, track it with **Git LFS** (documented in `RUNBOOK`/quickstart). Image-size gate (< 500 MB)
still applies to the running container.

**Rationale**: The brief requires a fresh-clone `docker compose up`; small/quantized artifacts keep
the repo and image lean.

**Alternatives considered**: Download-at-build from a model host (adds a network dependency to the
build, breaks offline/fresh-clone determinism).

---

## D16 — Logging & privacy

**Decision**: `structlog` JSON; bind `operation`, `batch_size`, `latency_ms`, `model_version`.
**Never** log request text, embeddings, the token, or any PII. Truncation/auth events log counts and
outcomes only.

**Rationale**: Principle V + FR-020/SC-008. The modelserver receives clinical text, so payload-free
logging is mandatory.

**Alternatives considered**: Debug-logging payloads (PII risk — rejected).

---

## Resolved spec-checklist items

- **CHK040** → D14 (no uptime SLO, intentional). **CHK046** → D12 (512 tokens). **CHK047** → D7
  (HTTP/JSON REST + endpoints). **CHK048** → D9 (per-result, separate classifier/embedder versions).

## Future improvement (tracked, out of scope)

GPU-accelerated serving and/or larger torch-based models for higher accuracy/lower latency — requires
a deliberate **constitution amendment** (Principle VI no-torch) before adoption; the CPU/ONNX path
here remains the supported default (spec Assumptions).
