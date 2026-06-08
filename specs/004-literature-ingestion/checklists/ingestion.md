# Requirements Quality Checklist: Literature Ingestion

**Purpose**: Release-gate validation of requirement quality (completeness, clarity, consistency, measurability, coverage) for the literature-ingestion spec — "unit tests for the English," run by the author before `/speckit-plan`.
**Created**: 2026-06-08
**Feature**: [spec.md](../spec.md)
**Depth**: Formal release gate · **Audience**: Author (pre-plan) · **Focus**: integration & resilience, data model & dedup, security & isolation, overall completeness/consistency

## Requirement Completeness

- [x] CHK001 - Is each field of the "common document shape" marked required vs optional, so adapters know the minimum they must produce? [Completeness, Spec §FR-004]
- [x] CHK002 - Are requirements defined for deriving/handling the normalized identifier when a record has none of DOI / PubMed ID / source alert-id? [Gap, Spec §FR-006]
- [ ] CHK003 - Is the set of platform-configured sources, and how a source is enabled/disabled, documented as a requirement? [Completeness, Spec §FR-003, Key Entities]
- [x] CHK004 - Are the full set of ingestion-run **status values** (e.g., running, success, partial-success, failed) enumerated, including the "all sources failed" case? [Completeness, Spec §FR-011/§FR-012]
- [x] CHK005 - Are retention/lifecycle requirements defined for documents, provenance links, and run records when a watchlist is deactivated or a client is suspended? [Gap, Spec §FR-022]
- [x] CHK006 - Is the existence (and config location) of the initial-lookback default and per-source result cap specified, even with values left tunable? [Completeness, Spec §FR-021, Assumptions]
- [x] CHK007 - Are requirements defined for how a MeSH item's validity state is represented and surfaced on every watchlist read? [Completeness, Spec §FR-009, §US4-3]
- [x] CHK008 - Is the behavior of a run whose target watchlist becomes ineligible mid-run (e.g., deactivated after trigger) specified? [Gap, Spec §FR-022, Edge Cases]

## Requirement Clarity & Ambiguity

- [x] CHK009 - Is "newer than the watermark" defined against a concrete record attribute (publication/alert date vs source-indexed date)? [Ambiguity, Spec §FR-021]
- [x] CHK010 - Is "partial success" precisely defined in terms of which per-source outcomes produce it? [Clarity, Spec §FR-011]
- [x] CHK011 - Is the source-reliability tier **ordering** explicitly stated so "highest contributing tier" is unambiguous? [Clarity, Spec §FR-005, Key Entities]
- [x] CHK012 - Is the source→tier mapping fully enumerated, including preprint detection and openFDA labels (`peer_reviewed`) vs FAERS (`case_report`)? [Clarity, Spec §FR-005]
- [x] CHK013 - Is which watchlist field each adapter consumes (drugs / keywords / MeSH) unambiguous for all six sources? [Clarity, Spec §FR-002, §FR-010]
- [x] CHK014 - Is "raw source payload(s)" scoped (one vs many per contributing source; size/format expectations)? [Ambiguity, Spec §FR-004]
- [ ] CHK015 - Is "matching records" defined enough to be testable (what makes a source record a match for a watchlist)? [Ambiguity, Spec §FR-002]

## Requirement Consistency

- [ ] CHK016 - Do all dedup statements agree on the key `(client_id, normalized_external_id)` across §FR-004, §FR-006, §US3, Key Entities, and Assumptions (no residual source-inclusive key)? [Consistency]
- [ ] CHK017 - Is the six-source list identical across the overview, §FR-003, §US2, and §SC-002 (incl. openFDA FAERS + labels)? [Consistency]
- [ ] CHK018 - Is "admin-only trigger / reviewer-may-view" stated consistently across §FR-008, §US1-4, and §SC-005? [Consistency]
- [ ] CHK019 - Do the "no parse/embed/classify/draft here" scope boundaries align across the overview, §FR-018, and Assumptions (→ specs 6/7/8/9)? [Consistency]
- [ ] CHK020 - Are the single-source US1 acceptance wording and the multi-source dedup model (contributing sources) non-contradictory? [Consistency, Spec §US1-1 vs §US3]

## Acceptance Criteria & Measurability

- [ ] CHK021 - Is every functional requirement traceable to at least one measurable success criterion or acceptance scenario? [Traceability, Spec §FR-*/§SC-*]
- [x] CHK022 - Is there a measurable criterion for **incremental** behavior (a re-run fetches only newer records, not full backfill)? [Gap, Spec §SC-010]
- [ ] CHK023 - Is §SC-002 ("verified per source type") backed by per-source acceptance scenarios for all six? [Coverage, Spec §SC-002, §US2]
- [x] CHK024 - Can "one paper stored exactly once per client" be objectively verified by a stated criterion? [Measurability, Spec §FR-006, §SC-003]
- [ ] CHK025 - Is the 95%+ write-path coverage target stated in a way that's objectively checkable for this spec's write paths? [Measurability, Spec §SC-009]

## Scenario & Edge-Case Coverage

- [x] CHK026 - Are exception-flow requirements complete for every named failure mode (timeout, rate-limit, malformed response, missing credential, individual unparseable record)? [Coverage, Spec §FR-012/§FR-014, Edge Cases]
- [x] CHK027 - Are recovery requirements defined (watermark NOT advanced on a source's failure, so its window is retried next run)? [Recovery, Spec §FR-021]
- [x] CHK028 - Are concurrent/overlapping-run requirements specified to prevent duplicate creation (race safety at the storage layer)? [Edge Case, Spec Edge Cases]
- [x] CHK029 - Are zero-result vs all-sources-failed outcomes distinctly specified (success-empty run vs failed run)? [Coverage, Spec §FR-015 vs §FR-011/§FR-012]
- [x] CHK030 - Is behavior specified for sources that lack a usable date for windowing? [Gap, Spec §FR-021, Edge Cases]
- [x] CHK031 - Are requirements defined for a missing/stale bundled MeSH artifact at validation time? [Gap, Spec §FR-009, Edge Cases]
- [x] CHK032 - Is the first-run vs subsequent-run distinction (initial lookback vs watermark) covered by an acceptance scenario? [Coverage, Spec §SC-010]

## External Integration & Resilience (NFR)

- [ ] CHK033 - Is the uniform adapter contract's required output specified well enough that adding/removing a source needs no document-shape change? [Completeness, Spec §FR-003]
- [ ] CHK034 - Are per-source rate-limit/usage-limit obligations stated concretely (and where limits are configured), beyond "respect limits"? [Clarity, Spec §FR-013]
- [x] CHK035 - Are retry boundaries explicit (transient retried with backoff; permanent/4xx never retried)? [Clarity, Spec §FR-013]
- [x] CHK036 - Is the dependency on PubMed's native MeSH expansion documented as an external behavior the spec relies on? [Dependency, Spec §FR-010, Assumptions]

## Security & Multi-Tenant Isolation

- [x] CHK037 - Are tenant-isolation requirements stated for BOTH writes (trigger) and reads (documents, runs, watermarks)? [Coverage, Spec §FR-007]
- [x] CHK038 - Are source-credential requirements complete (Vault-only, CI secret-writer obligation, missing-credential → recorded failed source not crash)? [Completeness, Spec §FR-017]
- [x] CHK039 - Is the audit requirement unambiguous (exactly one entry per trigger, with actor + target watchlist)? [Clarity, Spec §FR-016, §SC-008]
- [x] CHK040 - Is PII handling at ingestion addressed, given raw openFDA FAERS payloads are stored before spec-12 redaction — does it align with the constitution's redaction principle? [Ambiguity, Spec §FR-023]

## Dependencies & Assumptions

- [x] CHK041 - Is the dependency on (and modification of) the spec-3 watchlist write path for save-time MeSH validation documented and bounded? [Assumption, Spec Assumptions]
- [x] CHK042 - Is the durability risk of the in-process background-task run model acknowledged (what happens to a run's status if the app restarts mid-run)? [Assumption, Spec §FR-024, Assumptions]
- [x] CHK043 - Is the "new Vault secret ⇒ also add to CI secret writer" obligation captured as a requirement, not only an assumption? [Traceability, Spec §FR-017]
- [x] CHK044 - Are all out-of-scope deferrals (cross-client dedup, RxNorm, parsing, scheduling, guardrails/redaction) explicitly enumerated so none is silently assumed in-scope? [Completeness, Spec Assumptions]
