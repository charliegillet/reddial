# RedDial — Operations Runbook

Operate and troubleshoot RedDial. RedDial is **offline-by-default**: the loopback
harness, campaign runner, and control-plane API all run against a self-authored
FAKE-PII mock and need **no keys and place no calls**. Live PSTN dialing is a
separate, deliberately gated path (see [SECURITY.md](SECURITY.md) and
[DEPLOY.md](DEPLOY.md)).

All commands run from `server/` unless noted.

---

## 0. Quick reference

| I want to… | Command |
|---|---|
| Run the offline harness | `make loopback` / `make campaign N=200` |
| Start the control-plane API | `docker compose up --build` (or `uv run uvicorn api:app --port 8080`) |
| Deploy the voice bot | GitHub Actions → **Deploy (Pipecat Cloud)** (manual) or `pcc deploy` |
| Roll back a deploy | `pcc deploy` of a known-good tag (see §4) |
| Kill all dialing NOW | unset `REDDIAL_DIALING_ENABLED` / redeploy (see §6) |
| Check Cekura connectivity | `make cekura-check` |

---

## 1. Run the offline harness (no keys)

```bash
cd server
make install          # uv sync --locked
make test             # curated suite
make loopback         # one deterministic Luhn-verified breach, prints BREACH/grade/turns
make campaign N=200   # batch -> scorecard.{json,html} (+ transcripts/ with --persist)
make efficacy         # one honestly-labeled loopback artifact in results/
```

The loopback is deterministic (byte-identical across runs). It attacks RedDial's
**own mock** — the scorecard is NOT evidence about a real third-party agent.

## 2. Start the control-plane API

The API (`api:app`) exposes the offline harness over HTTP for the dashboard. It
never dials.

```bash
cd server
cp .env.example .env          # offline scans need no live keys
docker compose up --build     # serves on :8080, healthcheck hits /healthz
# or, without Docker:
uv run uvicorn api:app --host 0.0.0.0 --port 8080
```

Verify:

```bash
curl -s localhost:8080/healthz   # {"status":"ok","version":"..."}
curl -s localhost:8080/readyz    # {"ready":true,"checks":{...}}
curl -s localhost:8080/attacks   # 12 attack definitions
```

Container health: `docker compose ps` (look for `healthy`); logs: `docker compose logs -f api`.

## 3. Deploy the voice bot (Pipecat Cloud)

**Preferred — manual GitHub Action:** Actions → **Deploy (Pipecat Cloud)** →
*Run workflow*, choose `role` (`target`/`attacker`/`flower`) and a tag. It re-runs
the lint+test gate, then `uv run pcc deploy` in the `production` environment.

**Manual from a workstation:**

```bash
cd server
make build TAG=v0.1.0 BASE=dailyco/pipecat-base:0.0.8   # pin the base; never :latest in prod
pcc deploy                                              # reads pcc-deploy.toml
```

Runtime secrets live in the Pipecat Cloud secret set, not in the image — push
them with `scripts/setup-secrets.sh pcc` (see §8).

## 4. Roll back a deploy

Pipecat Cloud deploys by image tag, so rollback = redeploy the previous good tag.

```bash
# Identify what's running and recent revisions:
pcc agent status flower-bot
pcc agent logs flower-bot

# Redeploy a known-good tag (rebuild that tag, then deploy):
make build TAG=v0.1.0 && pcc deploy
```

If a bad deploy is actively dialing, do the **kill-switch (§6) first**, then roll
back. Record the incident in §7.

## 5. Read logs

- **Deployed bot:** `pcc agent logs <agent_name>` (agent name from `pcc-deploy.toml`, currently `flower-bot`).
- **Local API:** `docker compose logs -f api`.
- **Offline runs:** stderr/stdout; set `REDDIAL_LOG_LEVEL=DEBUG`. Structured logging
  via `run_context.setup_logging()`. Correlate with `run_id` (per campaign) and
  `call_id` (per call). `--persist` writes transcripts to `transcripts/<run_id>/`.

## 6. Dialing kill-switch (fail-closed)

Outbound dialing is **refused** unless ALL hold (enforced in `safety_controls.py`):

1. `REDDIAL_DIALING_ENABLED=1` (the kill-switch; **default OFF**)
2. destination is E.164 **and** in `REDDIAL_DIAL_ALLOWLIST`
3. per-call `consent=True`
4. under `REDDIAL_MAX_CALLS` cap + `REDDIAL_MIN_CALL_INTERVAL_S` rate limit

**To stop all dialing immediately:**

- Local/CLI: unset `REDDIAL_DIALING_ENABLED` (or set empty) in the shell/`.env`.
- Deployed: remove/blank `REDDIAL_DIALING_ENABLED` in the Pipecat Cloud secret set
  and redeploy, or empty `REDDIAL_DIAL_ALLOWLIST` (an empty allowlist refuses every
  number). The kill-switch is OFF by default in the Dockerfile, so a fresh deploy
  of the default config cannot dial.

## 7. Incident handling

1. **Stop the bleed:** apply the kill-switch (§6).
2. **Roll back** to the last good tag (§4).
3. **Pull evidence:** `pcc agent logs`, the affected `transcripts/<run_id>/`, the scorecard.
4. **Record:** what changed, blast radius, fix. File a vuln report if security-relevant
   (see [SECURITY.md](SECURITY.md)).

---

## 8. Secrets

Push secrets from a local `.env` (never commit `.env`):

```bash
scripts/setup-secrets.sh pcc    # -> Pipecat Cloud secret set (runtime bot secrets)
scripts/setup-secrets.sh gh     # -> GitHub Actions (deploy workflow: PIPECAT_CLOUD_API_KEY)
DRY_RUN=1 scripts/setup-secrets.sh   # preview, change nothing
```

The script fails if `.env` is missing and never prints secret values.

---

## 9. Common failures

| Symptom | Cause | Fix |
|---|---|---|
| Startup aborts with a config error | **Preflight** (`preflight.py`) found a missing `[REQUIRED]` var (e.g. `NVIDIA_ASR_URL`, `NEMOTRON_LLM_URL`, `GRADIUM_API_KEY`) | Set the var. Don't paper over with `REDDIAL_SKIP_PREFLIGHT=1` in prod. |
| `KeyError: GRADIUM_API_KEY` on a voice run | Missing required key | Fill `.env` / the pcc secret set; re-push with `setup-secrets.sh pcc`. |
| Dialing call "refused" / nothing happens | Safety gate failing closed (§6) | Confirm kill-switch on, number E.164 + allowlisted, `consent=True`, under caps. Working as designed. |
| Cekura calls silently do nothing | No key, or wrong path/DNS/timeout | `make cekura-check` for a LOUD status. Set `CEKURA_API_KEY`; verify `CEKURA_OBSERVABILITY_PATH`. |
| **Cekura 402 Payment Required** | Account out of quota/credits/unpaid | Top up the Cekura account or unset `CEKURA_API_KEY` to no-op gracefully. `check_connection()` surfaces 402 explicitly rather than hiding it. |
| `ModuleNotFoundError` importing `attacker_bot`/`target_bot` | Voice/optional deps not synced | `uv sync --locked` (installs `twilio`, `loguru`, `pipecat`, etc.). |
| Live call connects but media never flows | `/attacker-ws` route not registered (known TODO) | Register the websocket route in the runner before the live call (see PRODUCTION_READINESS.md). |
| Bare `pytest` aborts at collection | It tries to collect `test_nemotron_llm.py` (needs pipecat) | Use `make test` / `pytest tests/` (testpaths is set in pyproject). |
| CI docker-build job fails | Dockerfile / `uv.lock` drift | Reproduce locally: `make build`; re-`uv lock` if deps changed. |
| CI type-check shows errors but CI still passes | pyright is intentionally **non-blocking** (~30 preexisting errors) | Expected. Burn down the backlog, then drop `continue-on-error` in `ci.yml`. |
