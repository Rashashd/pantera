# Contract: App-side caller — `app/infra/modelserver_client.py`

The single reusable async client other parts of the platform use to call the modelserver. Satisfies
FR-019. This spec ships and unit-tests it; wiring it into the api request path is Spec 6 / triage.

## Surface (illustrative)
```python
class ModelserverClient:
    async def classify(self, texts: list[str]) -> list[ClassificationResult]: ...
    async def embed(self, texts: list[str]) -> list[EmbeddingResult]: ...
```
- Built from the shared `app/infra/http.py` `httpx.AsyncClient` factory; base URL + `X-Service-Token`
  (from `settings.modelserver_token`) injected.
- Returns typed Pydantic objects (no raw dicts leaked to callers).

## Resilience (FR-019 / constitution)
- Per-call **timeout**.
- `tenacity` retry: `stop_after_attempt(3)`, exponential backoff, **retry only on
  timeouts/connection errors/5xx — never on 4xx** (a `422`/`401`/`403` is a caller bug, not transient).
- On exhausted retries, raise a typed error for the caller to handle.

## Batching responsibility
- Callers split workloads into ≤ 128-item batches before calling (the client MAY expose a helper that
  chunks a large list into ≤128 batches and concatenates results in order).

## Not in scope here
- No api endpoint wires this in yet; no embedding persistence (Spec 6); no triage decisions (later).
