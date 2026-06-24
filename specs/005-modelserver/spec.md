# Feature Specification: Modelserver — Adverse-Event Classifier & Medical Embedder

**Feature Branch**: `005-modelserver`

**Created**: 2026-06-08

**Status**: Draft

**Input**: User description: "Spec 5 = the modelserver: offline-trained adverse-event classifier (ADE Corpus v2) + medical ONNX sentence embedder, served lean via onnxruntime (no torch), SHA-256-pinned with startup hash validation, service-credential auth, and a classifier macro-F1 eval gate. Prerequisite for Spec 6 embedding and later triage."

## Overview

Specs 1–4 produced the platform, auth/roles, client watchlists, and a per-client corpus of
raw, unparsed documents (the ingestion pipeline). The next stages of Vespera — parsing &
embedding the corpus (Spec 6) and triaging each finding (later specs) — both depend on a
single lean inference service that can answer two questions about biomedical text:

1. **"Is this an adverse event?"** — a cheap, deterministic YES/NO gate run on every candidate finding.
2. **"What is the vector representation of this text?"** — domain-appropriate embeddings for every chunk, so no external embedding API is needed.

This feature delivers that service: the **modelserver**. It is trained offline, exported to
portable artifacts, and served from a lean container that performs inference only. It does
not parse documents, decide severity, draft reports, or call any LLM — those belong to later
specs. It is the prerequisite that unblocks the embedding pipeline and the triage gate.

## Clarifications

### Session 2026-06-08

- Q: What committed macro-F1 threshold should gate the shipped classifier? → A: macro-F1 ≥ 0.80 on held-out ADE Corpus v2 (initial committed floor; may be raised once the shipped model's number is known).
- Q: What performance targets should the modelserver meet? → A: Per-operation p95 latency SLOs on a lean CPU/no-torch container — classifier < 50 ms p95, embedder < 150 ms p95 (single item) — plus a batch throughput SLO of ≥ 100 items/sec, with latency and throughput exposed as observable metrics. (GPU/torch-based faster or stronger models are a documented future improvement.)
- Q: What fixed dimension should the medical embedding vectors have? → A: 768 dimensions (standard for BiomedBERT/PubMedBERT-class models; pinned so Spec 6's vector storage is built correctly the first time).
- Q: Who owns the YES/NO decision cutoff for classification? → A: The modelserver returns the raw confidence in [0, 1] AND a YES/NO computed at a documented default cutoff of 0.5; callers (e.g., later triage) may apply their own fail-safe threshold to the raw confidence. The decision policy lives with the caller, not baked into the model service.
- Q: How should text longer than the model's maximum input length be handled? → A: Contract is that callers send model-sized chunks (chunking is Spec 6's responsibility); the modelserver truncates any over-limit text to the model maximum as a logged safety net and computes the decision/embedding on the truncated text — it does not crash or silently drop input. (Over-large batches/payloads are still rejected as a validation error.)

### Session 2026-06-09

- Q: Should responses include a model-version identifier? → A: Yes — every classification and embedding response includes a model-version identifier (the serving artifact's SHA-256 and/or a version tag) so callers can store it alongside results and detect/refresh stale outputs (e.g., re-embed when the embedder changes). Also strengthens auditability.
- Q: What is the maximum number of items per batch request? → A: 128 items per request; requests exceeding this are rejected with a validation error, and callers split larger workloads into multiple batches.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Classify a finding as adverse / not-adverse (Priority: P1)

A calling service (the backend or the background worker) submits the text of a candidate
finding to the modelserver and receives a deterministic decision — adverse event **YES** or
**NO** — together with a confidence score. This is the cheap first gate that every finding
passes through before any expensive LLM or agent work happens.

**Why this priority**: The adverse-event gate is the single most-used inference call in the
whole product and the foundation of the triage pipeline. Without it, no finding can be
routed. It is the minimum viable slice of the modelserver and is independently demonstrable.

**Independent Test**: Send a known adverse-event passage and a known non-adverse passage to
the classification endpoint; verify the first returns YES and the second NO, each with a
confidence score in [0, 1], and that identical input always yields an identical result.

**Acceptance Scenarios**:

1. **Given** the modelserver is running with a valid classifier artifact, **When** a caller submits a passage describing a serious drug reaction, **Then** the service returns a YES decision with a confidence score.
2. **Given** the modelserver is running, **When** a caller submits a passage with no adverse-event content, **Then** the service returns a NO decision with a confidence score.
3. **Given** the same input text, **When** it is submitted twice, **Then** the decision and confidence are byte-for-byte identical (deterministic inference).
4. **Given** a request with empty or malformed text, **When** it is submitted, **Then** the service rejects it with a validation error and does not return a fabricated decision.
5. **Given** a batch of N passages in one request, **When** it is submitted, **Then** the service returns N decisions in input order.

---

### User Story 2 - Produce medical embeddings for text chunks (Priority: P2)

A calling service submits one or more biomedical text chunks and receives fixed-length
numeric vector embeddings produced by a medical sentence model. These vectors are what the
RAG index (Spec 6) will store and search. No external embedding API is used.

**Why this priority**: Embeddings are required by the very next spec (parse + chunk + embed)
and by all RAG retrieval thereafter. It is foundational but second to the classification
gate because the classifier is what gates every finding immediately.

**Independent Test**: Submit a chunk of clinical text and verify a vector of the documented
fixed dimension is returned; submit the same chunk twice and verify identical vectors; submit
two near-identical chunks and verify their vectors are more similar to each other than to an
unrelated chunk.

**Acceptance Scenarios**:

1. **Given** the modelserver is running with a valid embedder artifact, **When** a caller submits a text chunk, **Then** the service returns a numeric vector of the documented fixed dimension.
2. **Given** the same chunk, **When** it is embedded twice, **Then** the two vectors are identical (deterministic embedding).
3. **Given** a batch of chunks, **When** submitted in one request, **Then** the service returns one vector per chunk, in input order.
4. **Given** two semantically similar clinical passages and one unrelated passage, **When** all three are embedded, **Then** the similar pair's vectors are closer to each other than either is to the unrelated passage.
5. **Given** an empty chunk list, **When** submitted, **Then** the service returns an empty result without error.

---

### User Story 3 - Choose the shipped classifier with committed comparison numbers (Priority: P2)

A machine-learning engineer trains and evaluates candidate adverse-event classifiers offline
against a held-out portion of a labeled adverse-event dataset, compares the approaches on a
single agreed metric, ships exactly one, and records the comparison so the choice is
defensible. The result is a documented model card and a committed evaluation threshold.

**Why this priority**: The constitution requires that every model decision be backed by a
number and defended in `DECISIONS.md`. Shipping an undefended classifier would violate that
principle. It is P2 because a placeholder artifact can serve US1/US2 mechanically before the
final defended model is chosen, but the spec is not complete until the choice is justified.

**Independent Test**: Verify that a model card exists documenting the task, dataset, the
compared approaches with their scores on the agreed metric, the shipped choice, and the
SHA-256 of each served artifact; verify the comparison numbers are reproducible from a
committed evaluation step.

**Acceptance Scenarios**:

1. **Given** the offline training/evaluation step, **When** it is run, **Then** at least the candidate approaches are scored on the same held-out data with the same metric and the numbers are recorded.
2. **Given** the shipped classifier, **When** its choice is reviewed, **Then** a model card documents the dataset (with a content hash/version), the comparison, the chosen approach and why, and the SHA-256 of each served artifact.
3. **Given** the served artifacts, **When** their hashes are computed, **Then** they match the SHA-256 values recorded in the model card.

---

### User Story 4 - Refuse to serve compromised or missing models; authenticate callers (Priority: P2)

A platform operator must be confident the running service is serving the exact, intended
model artifacts and that only authorized internal services can call it. On startup the
modelserver validates each artifact's SHA-256 against the expected value and refuses to boot
on mismatch or absence. Every inference request must present a valid service credential.

**Why this priority**: This is the integrity and access-control boundary mandated by the
constitution (startup hash validation; service-credential auth on the modelserver). A model
that silently changed, or an unauthenticated caller, would undermine the auditability and
isolation guarantees of the whole platform.

**Independent Test**: Tamper with (or remove) an artifact and confirm the service refuses to
start; start cleanly with correct artifacts and confirm a request with a valid credential
succeeds while a request with a missing/invalid credential is rejected.

**Acceptance Scenarios**:

1. **Given** an artifact whose bytes do not match the expected SHA-256, **When** the modelserver starts, **Then** it refuses to boot and reports the mismatch.
2. **Given** a required artifact is missing, **When** the modelserver starts, **Then** it refuses to boot and reports the missing artifact.
3. **Given** correct artifacts, **When** the modelserver starts, **Then** it reports healthy and serves requests.
4. **Given** a running modelserver, **When** a request arrives without a valid service credential, **Then** it is rejected as unauthorized.
5. **Given** a running modelserver, **When** a liveness/health check is made, **Then** it reports status without requiring an inference call.

---

### User Story 5 - Block merges that regress classifier quality (Priority: P3)

The team must be protected from silently shipping a worse classifier. A committed evaluation
gate scores the shipped classifier on a held-out set and fails the build if the score falls
below the declared threshold.

**Why this priority**: Required by the "every decision is backed by a number / regression
blocks merge" principle, but it depends on US3 having produced a shipped model and a number,
so it is sequenced last.

**Independent Test**: Run the evaluation gate against the shipped artifact; confirm it passes
at or above the declared threshold and that artificially lowering the threshold bound (or
swapping in a degraded model) causes the gate to fail the build.

**Acceptance Scenarios**:

1. **Given** a declared classifier threshold in the committed thresholds file, **When** the eval gate runs on the shipped model, **Then** it passes only if the measured score meets or exceeds the threshold.
2. **Given** a model that scores below the threshold, **When** the eval gate runs, **Then** the build fails.

---

### Edge Cases

- **Oversized input**: an over-large *request* (too many items / payload beyond the limit) is rejected with a clear validation error rather than exhausting memory. A single *text* longer than the model's maximum length is truncated to the model maximum (with a logged warning) and processed — not rejected and not silently dropped; producing model-sized chunks is the caller's job (Spec 6).
- **Cold start**: the first request after boot must not return before models are loaded; readiness is distinct from liveness.
- **Partial artifacts**: only one of the two artifacts (classifier / embedder) is present or valid — the service refuses to boot rather than serving half its contract.
- **Unsupported language / non-clinical text**: the classifier still returns a YES/NO + confidence (it never errors on valid text); behavior on out-of-domain text is documented, not crashed.
- **Concurrent load**: multiple callers issue inference simultaneously — results remain correct and deterministic per input.
- **Credential rotation**: a rotated/expired service credential is rejected; a valid replacement is accepted without a code change.
- **Dataset licensing/version drift**: the offline training data is pinned by version/hash so the model card's numbers remain reproducible.

## Requirements *(mandatory)*

### Functional Requirements

#### Inference contract

- **FR-001**: The system MUST expose an adverse-event classification capability that accepts biomedical text and returns, per input, the raw confidence score in the range [0, 1] AND a binary decision (adverse YES / NO) computed at a documented default cutoff of 0.5. Callers MUST be able to apply their own threshold to the raw confidence; the decision policy (e.g., a fail-safe triage cutoff) is owned by the caller, not fixed inside the modelserver.
- **FR-002**: The system MUST expose a medical embedding capability that accepts biomedical text and returns, per input, a fixed-length numeric vector of exactly 768 dimensions (constant for all embeddings).
- **FR-003**: Both capabilities MUST accept a batch of up to 128 inputs in a single request and return one result per input, preserving input order. Requests exceeding 128 items MUST be rejected with a validation error; callers split larger workloads into multiple batches.
- **FR-004**: Inference MUST be deterministic: identical input MUST always produce identical output (same decision/confidence, same vector).
- **FR-005**: The system MUST validate every request body and reject empty, malformed, or over-large requests (more than 128 items in a batch / payload beyond the configured limit) with a clear validation error, never a fabricated result.
- **FR-005a**: For a single text input longer than the model's maximum input length, the system MUST truncate it to the model maximum and compute the decision/embedding on the truncated text, emitting a structured warning — it MUST NOT crash or silently drop the input. Producing model-sized chunks is the caller's responsibility (the Spec 6 parsing/chunking step); modelserver truncation is a safety net.
- **FR-005b**: Every classification and embedding response MUST include a model-version identifier (the serving artifact's SHA-256 and/or a version tag) identifying which model produced the result, so callers can persist it alongside stored results and detect when a model change requires refreshing (e.g., re-embedding).
- **FR-006**: The system MUST NOT parse documents, assign severity, draft reports, or call any external LLM — its sole responsibility is classification and embedding inference.

#### Models & artifacts

- **FR-007**: Both the adverse-event classifier and the medical embedder MUST be trained/prepared offline and served from portable, pre-built artifacts; the serving path MUST perform inference only (no training at serve time).
- **FR-008**: The serving runtime MUST NOT include torch or any deep-learning training framework; deep-learning models MUST be served via an ONNX runtime only (per constitution: no-torch serving containers).
- **FR-009**: The served container image MUST stay lean (target under ~500 MB) and run only the minimal inference dependencies.
- **FR-010**: Each served artifact MUST have a recorded SHA-256 hash; the serving process MUST validate every artifact's hash at startup and MUST refuse to boot on mismatch or absence.
- **FR-011**: A model card MUST document, for each artifact: the task, the training/evaluation dataset (pinned by version or content hash), the comparison of candidate approaches on a single agreed metric, the shipped choice and its rationale, and the artifact's SHA-256.

#### Classifier selection & evaluation

- **FR-012**: The offline workflow MUST evaluate the candidate classifier approaches on the same held-out data with the same metric, record the numbers, and ship exactly one approach.
- **FR-013**: A committed evaluation threshold of **macro-F1 ≥ 0.80** on held-out data MUST exist for the shipped classifier; an evaluation gate MUST fail the build if the measured macro-F1 falls below this threshold.
- **FR-014**: The shipped classifier's evaluation MUST be reproducible from a committed evaluation step (same data, same metric, recorded result).

#### Access, integrity & operability

- **FR-015**: Every inference request MUST require a valid service credential; requests without a valid credential MUST be rejected as unauthorized.
- **FR-016**: The service credential and any other secrets MUST be obtained from the platform secret store at startup (no secret values in code, image, or any committed file), consistent with the platform's existing secrets handling.
- **FR-017**: The system MUST expose a liveness/health signal that reports status without performing an inference call, and MUST distinguish "started" from "ready to serve" (models loaded and validated).
- **FR-018**: The system MUST handle concurrent inference requests correctly, preserving determinism and per-input correctness under load.
- **FR-019**: Calling services MUST reach the modelserver over an authenticated service-to-service call with a request timeout and bounded retry behavior on transient failure (no retry on client/validation errors), consistent with the platform's external-call resilience standard.
- **FR-020**: The system MUST emit structured operational logs for requests and startup validation, and MUST NOT log patient identifiers, raw secret values, or full request payloads.
- **FR-021**: The system MUST meet per-operation latency targets on a lean CPU (no-torch) container — classifier p95 < 50 ms and embedder p95 < 150 ms for single-item inference — and a batch-mode throughput of ≥ 100 items/sec. Per-operation latency and throughput MUST be exposed as observable metrics so the targets can be verified.

### Key Entities *(include if feature involves data)*

- **Classifier artifact**: the portable, offline-trained adverse-event detector served for YES/NO decisions; identified by a SHA-256 hash and described in the model card.
- **Embedder artifact**: the portable medical sentence model served to produce fixed-dimension vectors; identified by a SHA-256 hash and described in the model card.
- **Model card**: the record describing each artifact — task, dataset (pinned), candidate comparison, shipped choice + rationale, output shape, and SHA-256.
- **Classification result**: per input — raw confidence score in [0, 1] + an adverse decision (YES/NO) at the documented default cutoff (0.5), which callers may override with their own threshold; plus the model-version identifier that produced it.
- **Embedding result**: per input — a numeric vector of exactly 768 dimensions (constant for all embeddings); plus the model-version identifier that produced it.
- **Evaluation threshold**: the committed minimum score for the shipped classifier's agreed metric that gates merges.
- **Service credential**: the secret an authorized caller presents to use the inference endpoints.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A caller can obtain an adverse-event YES/NO decision with a confidence score for a passage of biomedical text through a single request, demonstrated on at least one known-positive and one known-negative example.
- **SC-002**: A caller can obtain a fixed-dimension medical embedding for a text chunk through a single request, and identical input yields identical output 100% of the time.
- **SC-003**: The shipped classifier meets or exceeds macro-F1 ≥ 0.80 on held-out data, and at least the candidate approaches are scored on the same data with the same metric, with the numbers recorded.
- **SC-004**: The serving image stays under the lean size target (~500 MB) and contains no training framework.
- **SC-005**: When any served artifact is altered or absent, the service refuses to start 100% of the time; with correct artifacts it starts and reports ready.
- **SC-006**: 100% of inference requests lacking a valid service credential are rejected; valid-credential requests succeed.
- **SC-007**: The evaluation gate blocks a build whenever the shipped classifier's measured score is below the committed threshold.
- **SC-008**: No patient identifier or secret value appears in any modelserver log during a representative run.
- **SC-009**: On a lean CPU (no-torch) deployment, single-item classification completes within 50 ms at p95 and single-item embedding within 150 ms at p95, and batch-mode processing sustains ≥ 100 items/sec, with these latency/throughput figures observable in metrics.

## Assumptions

- **Adverse-event dataset**: A formally labeled adverse-event corpus (e.g., the ADE Corpus referenced in the project brief) is the basis for the classifier; it is pinned by version/hash so the model card numbers are reproducible. The exact corpus is an implementation detail of the offline notebook, not this spec.
- **Agreed classifier metric**: Macro-F1 on held-out data is the single comparison metric, consistent with the project's evaluation criteria. The committed gate threshold is **macro-F1 ≥ 0.80** (clarified 2026-06-08); it is recorded in the committed thresholds file and may be raised once the shipped model's number is known.
- **Candidate approaches**: The classifier comparison considers a classical model, a PubMedBERT-derived ONNX model, and an LLM zero-shot baseline, per the project brief; exactly one ships and the choice is defended in `DECISIONS.md`.
- **Embedder**: A biomedical sentence model exported to ONNX provides domain-appropriate vectors; its output dimension is fixed at 768 (clarified 2026-06-08), consistent with BiomedBERT/PubMedBERT-class models named in the brief. No comparison against a general embedding model is required for this domain (per project design rationale).
- **Embedder evaluation**: Full RAG retrieval quality (hit@k, MRR, faithfulness) is evaluated where the RAG pipeline is built (Spec 6), not here; this spec only guarantees the embedding service contract (fixed dimension, determinism, basic semantic sanity).
- **Separate container**: The modelserver runs as its own container (justified by the no-torch constraint), consistent with the platform's modular-monolith-plus-justified-services architecture.
- **Secrets handling**: The modelserver obtains its service credential and any secrets from the platform's existing secret store at startup, matching how the rest of the platform handles secrets.
- **Calling contract**: Backend/worker callers reach the modelserver over authenticated service-to-service calls with timeouts and bounded retries; building those callers' downstream uses (embedding the corpus, triage) is the scope of later specs.
- **Out of scope**: document parsing/chunking, severity rules, report drafting, LLM valence classification, the agent, the frontend, and scheduling — all later specs.
- **Future improvement (out of scope for this spec)**: a GPU-accelerated serving path and/or larger, stronger torch-based classifier and embedder models for higher accuracy and lower latency. This would relax the current no-torch/CPU/~500 MB lean-container constraints and therefore requires a deliberate constitution amendment (Principle VI) before adoption; the CPU/ONNX path specified here remains the supported default.
