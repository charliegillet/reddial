# RedDial Control-Plane API — contract (read first)

A FastAPI app in `server/api.py` exposing the offline harness + results as HTTP,
so the web dashboard (and monitoring) can drive it. All endpoints are JSON.
SAFETY: the API only ever runs the offline loopback (FAKE-PII mock); it does NOT
expose live dialing (that stays CLI + the fail-closed safety gate).

Base: served by `uvicorn api:app`. CORS allowed for the dashboard origin.

## Endpoints

- `GET /healthz` -> `{"status":"ok","version":<str>}` — liveness (no deps touched).
- `GET /readyz` -> `{"ready":bool,"checks":{...}}` — readiness (e.g. attack lib loaded).
- `GET /attacks` -> `{"attacks":[{"id","category","spoken_template","success_condition"}...]}`
  (from `attack_library.ATTACKS`).
- `POST /scans` body `{"n":int=24,"persist":bool=false,"concurrency":int=1}` ->
  runs `campaign_runner.run_campaign` (loopback), returns
  `{"run_id","summary":<aggregate dict>}`. Cap `n` to a safe max (e.g. 500).
- `GET /scans/{run_id}` -> the persisted summary for a prior run (if persisted), else 404.
- `GET /scorecard/latest` -> the most recent aggregate summary JSON (or 404 if none).
- `GET /metrics` -> lightweight JSON metrics `{"scans_run":int,"last_breach_rate":float,...}`.

## Rules
- Never block: scans run synchronously but `n` is capped; long runs use the existing
  loopback (fast/deterministic). No live/PSTN from the API.
- Every response JSON-serializable (use scorecard.aggregate output shape).
- Add `tests/test_api.py` using `fastapi.testclient.TestClient`: healthz/readyz,
  /attacks count == 12, POST /scans returns a summary with breach_rate, 404 paths.
- Keep the FAKE-DATA safety note in the OpenAPI description.
