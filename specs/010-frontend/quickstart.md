# Quickstart — Validate the Frontend SPA + New Endpoints (Spec 010)

Runnable validation that the feature works end-to-end. Implementation details live in `tasks.md`,
`contracts/`, and `data-model.md` — this is a run/verify guide.

> Host note (this Windows dev box): integration tests need the gitignored
> `docker-compose.override.yml` (ports 5433/6380) + localhost Vault repoint — see
> `memory/host-integration-test-vault-repoint.md`. Clean CI uses service names.

## Prerequisites

- Stack up: `docker compose up -d` (postgres, redis, vault, modelserver, app).
- Secrets in Vault (`scripts/write_secrets.py`). `langsmith_api_key` is **optional** — leave it empty
  to run with tracing disabled (the app still boots and the cost dashboard still works).
- Migration `0009` applied: `uv run alembic upgrade head` → confirm `llm_usage` exists.
- Node 20+ for the SPA.

## Backend: apply migration & sanity-check

```bash
uv run alembic upgrade head
uv run ruff check app && uv run black --check app   # both MUST pass
uv run pytest tests/unit tests/integration -k "passage or portal or usage or report_findings"
```

## Backend: exercise the new endpoints (against a seeded client + approved report)

```bash
# 1. login → token
TOKEN=$(curl -s -X POST localhost:8000/auth/jwt/login -d 'username=reviewer@x&password=…' | jq -r .access_token)

# 2. FR-006a all-reports (reviewer): every status
curl -s localhost:8000/clients/1/reports?status=all -H "Authorization: Bearer $TOKEN" | jq '.[].status'

# 3. FR-029 passage text — chunk_id comes from a claim's source_ref / corroboration passage_chunk_ids
curl -s localhost:8000/clients/1/passages/123 -H "Authorization: Bearer $TOKEN" | jq '{chunk_id,title,external_id}'
#    unknown/other-client chunk → 404 {"detail":"PASSAGE_UNAVAILABLE"}

# 4. FR-031 per-report findings
curl -s localhost:8000/clients/1/reports/5/findings -H "Authorization: Bearer $TOKEN" | jq '.[].state'

# 5. FR-030 client portal (login as a client-user) — approved+sent only, own client only
CTOKEN=$(curl -s -X POST localhost:8000/auth/jwt/login -d 'username=clientuser@x&password=…' | jq -r .access_token)
curl -s localhost:8000/clients/1/portal/reports -H "Authorization: Bearer $CTOKEN" | jq '.[].status'   # all approved/sent/delivered
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/clients/2/portal/reports -H "Authorization: Bearer $CTOKEN"  # 404 (not own client)

# 6. FR-021/034 cost dashboard (login as admin/manager)
curl -s localhost:8000/clients/1/usage -H "Authorization: Bearer $TOKEN" | jq '{total_cost_usd,call_count,by_call_site}'
```

**Expected:** (2) lists statuses beyond the review set; (3) returns exact passage text or 404
unavailable; (4) lists findings with drug/reaction/bucket/state; (5) client-user sees only own-client
approved+ reports and 404s on another client; (6) per-client totals reconcile with summed `llm_usage`.

## Cost capture round-trip (FR-032/033)

```bash
# Trigger a triage + an expedited draft for the client, then:
psql … -c "select call_site, model, input_tokens, output_tokens, cost_usd, finding_id from llm_usage where client_id=1 order by id desc limit 5;"
```
**Expected:** one row per external LLM call — `call_site` triage/agent, agent rows carry `finding_id`.
With `langsmith_api_key` set, the same calls appear as traces in the LangSmith `pantera` project,
tagged `client_id`/`finding_id`. With it empty, no traces, but rows + dashboard still work.

## Frontend: run & validate

```bash
cd frontend
npm ci
npm run dev            # http://localhost:5173 ; VITE_API_BASE_URL → backend origin
npm run test           # Vitest component/integration (mocked API)
npm run test:e2e       # Playwright reviewer approve/reject happy path (needs the live stack)
npm run build          # production build (fresh-clone smoke)
```

### Manual smoke per role
- **Reviewer** → lands on `/queue`: drafts-only, expedited-first with SLA countdown; open a report →
  all structured claims + body + **all N** citations; click a citation → exact passage drawer; take
  each action (approve / edit-approve / reject-with-comment / discard) → report leaves the queue.
  Open `/reports` → all statuses with a delivery-status label ("Approved (pending delivery)").
- **Manager/Admin** → `/admin`: create a client, add a watchlist + custom severity keyword, trigger a
  manual per-watchlist ingest (202 "queued"); `/admin/usage` shows per-client cost (or an empty state).
- **Client-user** → `/portal`: one page per watchlist listing **approved+sent** reports only,
  read-only (no decision/config controls); cannot reach another client or any in-workflow report.
- **Any role** → reload keeps the session; expired/invalid token returns to `/login` with a clear,
  non-enumerating error.

## Acceptance gate mapping

| Check | Spec |
|---|---|
| All N citations shown; each passage openable | SC-002 / FR-009 / FR-010 / FR-029 |
| Only reviewers can decide; no send without a reviewer decision | SC-003 / FR-016 |
| Each role reaches only permitted surfaces (nav + direct URL) | SC-004 / FR-004 |
| Two reviewers → exactly one decision, other gets conflict | SC-005 / FR-017 |
| Client-user sees only own approved+sent, grouped by watchlist | SC-008 / FR-023 / FR-030 |
| Fresh-clone builds + serves the SPA | SC-009 |
| Component tests across surfaces + one e2e | SC-010 |
| Every LLM call → a client-attributed usage row; dashboard reconciles | SC-011 / FR-032/033/034 |
| Both linters pass on backend changes | constitution |
