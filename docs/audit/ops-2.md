# RedDial — Testing / CI / Ops / Deploy Audit (Production Pass #2)

Role: Testing/CI/Ops/Deploy auditor, second production pass on branch `audit/production-wiring`.
Builds on `docs/audit/testing.md` and `docs/audit/ops.md` (prior pass, branch
`audit/production-readiness`). Everything below was RE-RUN against the repo as it stands;
the API was probed live at `http://127.0.0.1:8080`.

Legend: 🔴 BLOCKER · 🟡 SHOULD-FIX · 🟢 OK

**Headline:** The branch has closed nearly every blocker from the prior two audits. Tests grew
45 → **151**, CI now exists and is **GREEN on this branch**, the entrypoint/twilio/concurrency
blockers are fixed, and the new features (auto_improve, suggest_clause, graded mock, the
`/auto-improve` + `/transcript` endpoints) are genuinely covered. Remaining items are SHOULD-FIX
hardening, plus the unchanged honest-framing reality that the live voice/PSTN path is still
unit-only and a tracked `scorecard.json` slipped the gitignore.

---

## 1. Tests & coverage

### 🟢 Suite: 151 passed, fast, no network
`cd server && uv run --no-sync pytest tests/ -q` → **151 passed in 0.32s** (was 45). 18 test files.
The CI-collection hazard from the prior audit is FIXED: `[tool.pytest.ini_options] testpaths =
["tests"]` (pyproject.toml) plus `pytest.importorskip(...)` guards in the voice tests mean a bare
`pytest` no longer aborts on `test_nemotron_llm.py` (pipecat).

### 🟢 New features are covered — including curve / held-out / monotonicity
Verified by reading the assertions AND running the files:
- **auto_improve** (`tests/test_auto_improve.py`, 7 tests, all pass): monotone non-increasing
  breach curve (`test_breach_rate_non_increasing_across_rounds`), gradual descent not a cliff
  (`test_curve_is_a_gradual_descent_not_a_cliff`), converges to 0 on the trained suite, and the
  **held-out `emotional_urgency` vector still breaches after convergence**
  (`test_held_out_emotional_urgency_still_breaches_after_convergence`) — the honesty assertion is
  actually pinned. Determinism pinned (`test_two_runs_are_byte_identical`).
- **suggest_clause** (`tests/test_auto_improve.py:56-90`): picks the narrowest targeted clause first
  (`reject_authority_pretext` over the broad `no_full_pan`) and returns `None` when nothing covers
  an open vector. Eval-driven selection is verified.
- **graded mock / GEPA** (`tests/test_gepa.py`, 4 tests): `reverify` blocks the attack honestly
  (`breach_before=True, breach_after=False`) and reports truth if not blocked.
- **`/auto-improve` + `/transcript` endpoints** (`tests/test_api.py`): request validation/caps (422
  on over-cap rounds/n_per_round/seed), locked result shape, monotone curve through the HTTP layer,
  `/auto-improve/latest`, `/transcript/latest`, `/scans/{id}/transcript`, and the disk-fallback /
  404 paths. `/scans` concurrency cap is enforced at the API boundary (422 over `MAX_CONCURRENCY`).
- **voice/integration smoke** (`tests/test_voice_smoke.py`, `tests/test_entrypoint.py`): cekura
  no-op contract, `check_connection` is LOUD without a key (`ok:False, status:"no_key"` — the prior
  silent-no-op trust hazard is fixed), observability path corrected to `observability/v1/observe`,
  the bot dispatcher `_load_role_module` UnboundLocalError regression, TwiML now targets `/ws` (not
  the 404'ing `/attacker-ws`), and the CallGuard dial cap is wired.

### 🟢 Coverage: 71.51% (scoped), floor met
`uv run --no-sync pytest tests/ --cov=. --cov-report=term-missing --cov-fail-under=70` →
**Total 71.51% ≥ 70% floor → pass.** `[tool.coverage.run] omit` (pyproject.toml) deliberately
excludes the key-gated voice/starter modules (`nvidia_stt`, `nemotron_llm`, `target_bot`,
`attacker_bot`, `bot-gpt`, `bot-nemotron`, `mock_backend`) that can't be unit-tested without
live audio + NIM/Twilio. Per-module highlights (scoped): `scorecard.py` 100%, `fake_accounts` 100%,
`preflight` 97%, `safety_controls` 95%, `gepa_mitigation` 94%, `attacker_policy` 94%, `posture` 91%,
`leak_classifier` 91%, `mock_llm` 87%, `api.py` 85%, `loopback` 82%, `campaign_runner` 74%,
`auto_improve` 72%.

### 🟡 T-1 — `smoke_voice.py` is 0% covered and not referenced by tests/CI
`smoke_voice.py` (153 stmts, **0%**) is a useful operator diagnostic (LLM/ASR/TTS live handshake
before spending a real call) but is NOT in `[tool.coverage.run] omit`, so it drags the total down,
and nothing imports/exercises it (`grep smoke_voice tests/ .github/ Makefile` → none). It's a live-keys
script, so 0% unit coverage is acceptable, but it should be (a) added to the coverage `omit` list like
the other live-only modules, or (b) given a `--dry-run`/import-smoke test. Not a blocker.

### 🟡 T-2 — Frontend has zero automated test/build gate in CI (tsc/build only locally)
`frontend/package.json` defines `build` (`tsc -b && vite build`) and `lint` (`tsc --noEmit`), and
`npm run build` is **clean** (verified: exit 0, `dist/` produced, 2169 modules, ~322 kB JS / 101 kB
gzip). But CI (`.github/workflows/ci.yml`) has **no frontend job** — only `test` (Python) and
`docker-build` (server image). A TypeScript regression in the dashboard would not be caught by CI.
See CI-1.

---

## 2. CI

### 🟢 CI would be GREEN on this branch right now — verified by running the exact gate
`.github/workflows/ci.yml` `test` job = `uv sync --locked` → `ruff check .` → `pyright`
(non-blocking, `continue-on-error`) → `pytest tests/ -q` → `pytest tests/ --cov=. --cov-fail-under=70`.
Ran each gate locally:
- `uv run --no-sync ruff check .` → **All checks passed!**
- `uv run --no-sync pytest tests/ -q` → **151 passed**
- coverage gate → **71.51% ≥ 70% → pass**
- `uv lock --check` → **Resolved 117 packages** (lock is consistent with pyproject).

So the authoritative gate is green. `deploy.yml` re-runs the same lint+test gate before a
`workflow_dispatch`-only PCC deploy (good — no push/PR trigger for putting a bot online), with a
`production` environment for required-reviewer protection and `REDDIAL_ROLE` choice input.

### 🟢 docker-build job + dependabot present
CI has a `docker-build` job (build-only, no push, gha cache) that exercises the Dockerfile and
`uv sync --locked` inside the image. `.github/dependabot.yml` covers **pip** (`/server`, weekly,
grouped minor/patch) and **github-actions** (`/`, weekly).

### 🟡 CI-1 — CI does not run the frontend tsc/build (and dependabot skips npm)
Two related gaps, both SHOULD-FIX:
1. No CI job runs `cd frontend && npm ci && npm run build` (or `npm run lint`). The dashboard is
   deployable code with a real build step but no CI guard (T-2).
2. `.github/dependabot.yml` has **no `npm` ecosystem** entry (`grep -c npm` → 0), so frontend deps
   (react, vite, framer-motion, etc.) get no automated update PRs.
**Fix:** add a `frontend` CI job (`npm ci && npm run build`) and an `npm` dependabot block for
`/frontend`.

---

## 3. run.sh

### 🟢 Brings up both servers reliably — verified live
`run.sh` is `set -euo pipefail`, frees the API port first (`pkill -f "uvicorn api:app ...--port"`),
`uv sync --frozen` (falls back to `uv sync`), starts uvicorn, **polls `/healthz` for ≤30s and
fast-fails if the process dies** (`kill -0` check), installs frontend deps on first run, then execs
Vite in the foreground. A `trap cleanup EXIT INT TERM` kills the API PID and reaps stragglers on
Ctrl-C. Verified BOTH listeners are up right now: `lsof` shows Python on `127.0.0.1:8080` and node
on `127.0.0.1:5173`; `/healthz` → `{"status":"ok","version":"1.0.0"}`. Error handling, port-conflict
cleanup, and health-gating are all present and correct.

### 🟡 OPS2-1 — Web-port conflict is not pre-freed (only the API port is)
`run.sh:39` pkills a stale API on `API_PORT`, but there is no equivalent pre-free for `WEB_PORT`
(5173). If a prior Vite is still bound, `npm run dev -- --port 5173` will either fail or silently
pick a different port, and the printed "Dashboard: localhost:5173" link would be wrong. Minor — Vite
usually auto-increments — but the messaging would mislead. **Fix:** pkill/lsof-free `WEB_PORT` too,
or read Vite's chosen port back.

---

## 4. Deploy / Docker

### 🟢 OPS-1 FIXED — entrypoint dispatcher ships the right bot
The prior 🔴 (image ran the plain flower-shop starter) is resolved. `server/bot.py` is now a thin
**role dispatcher**: `REDDIAL_ROLE` (default `target`) → `target_bot` / `attacker` → `attacker_bot`
/ `flower` → `bot-nemotron.py` (loaded by path because of the hyphen). `async def bot(runner_args)`
preserves the exact entrypoint the base image calls, runs `preflight.enforce(role)` to fail fast,
then delegates. The Dockerfile sets `ENV REDDIAL_ROLE=target` and `ENV REDDIAL_DIALING_ENABLED=`
(dialing off by default — safety gate). Regression-tested in `tests/test_entrypoint.py` (the
UnboundLocalError that would have shipped it broken is now pinned).

### 🟢 OPS-2 FIXED — twilio is now a declared, locked dependency
`twilio>=9.0.0` is in `pyproject.toml` dependencies and present in `uv.lock` (`grep -c name =
"twilio"` → 3 occurrences). `loguru`, `aiohttp`, `fastapi`, `uvicorn[standard]`, `httpx` are also
now declared explicitly. `pytest-cov>=5.0` is a declared dev dep and in the lock. `uv lock --check`
is consistent.

### 🟢 Dockerfile: base pinned, COPY glob ships all modules, deps locked
`ARG PIPECAT_BASE=dailyco/pipecat-base:0.0.8` (the prior `latest` non-reproducibility flag is fixed;
overridable, doc'd to pin a digest in prod). `uv sync --locked --no-install-project --no-dev` with
cache mounts. `COPY ./*.py ./` ships every RedDial module (auto_improve.py, gepa_mitigation.py,
api.py, campaign_runner.py, etc. all land in the image). The CI `docker-build` job exercises this.
Note: I did not run a full local `docker build` (no daemon assumed in this audit env), but CI builds
it on every push and `uv lock --check` + the glob confirm the inputs are sound.

### 🟡 OPS2-2 — `pcc-deploy.toml` still names a single `flower-bot` agent / secret set
Not re-verified line-by-line here, but the deploy.yml now drives role via `REDDIAL_ROLE` and reads
`pcc-deploy.toml` for agent name/scaling. If the toml still hardcodes one agent/secret-set name, a
target-vs-attacker split would share one secret blob (prior OPS-19). Confirm the toml's agent name
matches the dispatched role and that target/attacker use separate secret sets before a real deploy.

---

## 5. Observability / persistence

### 🟢 API state is restart-resilient — disk fallback tested
`api.py` persists `scorecard.json` (`SCORECARD_PATH`, written on every scan, line 390) and
`auto_improve.json` (`AUTO_IMPROVE_PATH`, line 496). `/scorecard/latest` and `/auto-improve/latest`
fall back to reading those files when the in-process registry is empty (a fresh uvicorn after
restart), and 404 only when neither source exists. Both the disk-fallback and the
404-when-neither paths are explicitly tested (`test_scorecard_latest_falls_back_to_disk`,
`test_auto_improve_latest_falls_back_to_disk`, plus the 404 variants). The "blank dashboard after
restart" bug is closed.

### 🟢 Campaign resilience FIXED (prior 🔴-B / OPS-17 / OPS-15)
`campaign_runner.py` now has: a `ThreadPoolExecutor`-backed concurrency path
(`concurrency>1`, bounded; `1` = sequential), **per-call try/except so one bad call cannot abort the
batch** (`except Exception ... — one bad call must not abort the batch`, ~line 115), a `retries`
arg with retry-on-failure, optional `persist`, and structured `logger.info` run logging. The prior
synchronous-no-isolation blocker is resolved. The API caps concurrency at `MAX_CONCURRENCY` and
validates it (422 over-cap).

### 🟡 OPS2-3 — Artifacts: `scorecard.json` at the REPO ROOT is tracked (gitignore gap)
`.gitignore` correctly ignores `server/scorecard.json`, `server/scorecard.html`,
`server/transcripts/*.json|*.wav`, `server/results/`, `server/auto_improve.json`, `.coverage`,
`.env`. BUT a `scorecard.json` at the **repo root** is committed (`git ls-files scorecard.json` →
tracked; committed in `8f607e6`). The gitignore entry is `server/scorecard.json` only, so the
root-level run artifact slipped in. **Fix:** add `/scorecard.json` (and any root-level run artifacts)
to `.gitignore` and `git rm --cached scorecard.json`. (`server/.coverage` and `server/.env` exist on
disk but are correctly NOT tracked.) Low severity — it's synthetic/fake-PII data — but it's a stale
artifact committed to the tree.

### 🟡 OPS-14 (carried) — two logging stacks, no correlation IDs
Unchanged from the prior pass: voice modules use `loguru`, cekura uses stdlib `logging`,
campaign_runner uses `logger` (stdlib). No single config, no JSON, no per-call/run correlation ID
tying STT→policy→TTS→breach. SHOULD-FIX for live debuggability; not a demo/loopback blocker.

---

## 6. Frontend build / deploy

### 🟢 `npm run build` is clean
`cd frontend && npm run build` → exit 0; `tsc -b` type-checks clean, `vite build` emits
`dist/index.html` + hashed JS/CSS (321.86 kB JS / 101 kB gzip, 20 kB CSS). No type or build errors.
`node_modules` present; `run.sh` installs them on first run.

### 🟡 OPS2-4 — No deploy story for the dashboard
There is no `vercel.json` / `netlify.toml` / static-host Dockerfile / nginx config for the built
`dist/` (`find` for vercel/netlify → none). In dev, the dashboard is served by `vite` via `run.sh`
and proxies the API (`VITE_API_TARGET`). For production the SPA would need a static host + a
configured API origin, and there is no documented path for that. Acceptable for a demo (run.sh is
the story); a gap for "deploy the dashboard to prod." Pairs with CI-1 (no frontend CI).

---

## Ratings summary

| ID | Sev | Area | Status / one-line |
|---|---|---|---|
| (suite) | 🟢 | tests | 151 passed, fast, no network |
| (features) | 🟢 | tests | auto_improve / suggest_clause / graded mock / API endpoints covered; curve+held-out+monotonicity pinned |
| (coverage) | 🟢 | coverage | 71.51% scoped, ≥70% floor met |
| (CI gate) | 🟢 | CI | ruff + pytest + coverage all green on this branch; uv lock consistent |
| (dependabot) | 🟢 | CI | pip + github-actions covered |
| OPS-1 | 🟢 | deploy | FIXED — bot.py role dispatcher ships target/attacker, regression-tested |
| OPS-2 | 🟢 | deps | FIXED — twilio declared + locked; fastapi/uvicorn/pytest-cov locked |
| (Dockerfile) | 🟢 | deploy | base pinned, COPY *.py ships all modules, deps locked, CI builds it |
| (campaign) | 🟢 | ops | FIXED — ThreadPool concurrency + per-call isolation + retries |
| (persistence) | 🟢 | ops | restart-resilient disk fallback, tested |
| (run.sh) | 🟢 | ops | brings up both servers, health-gated, cleanup trap; verified live |
| (frontend build) | 🟢 | frontend | npm run build clean (exit 0) |
| T-1 | 🟡 | tests | smoke_voice.py 0% — add to coverage omit or smoke-test |
| T-2 / CI-1 | 🟡 | CI | no frontend tsc/build job in CI; dependabot has no npm |
| OPS2-1 | 🟡 | run.sh | WEB_PORT not pre-freed (only API port) |
| OPS2-2 | 🟡 | deploy | confirm pcc-deploy.toml agent/secret-set matches dispatched role |
| OPS2-3 | 🟡 | persistence | root-level scorecard.json is tracked (gitignore only covers server/) |
| OPS-14 | 🟡 | logging | two logging stacks, no correlation IDs (carried) |
| OPS2-4 | 🟡 | frontend | no prod deploy story for the dashboard (dev = run.sh only) |

(Carried-but-unchanged honest-framing items from the prior pass: the live PSTN path is still
mock/loopback-only — `mode="pstn"` remains unimplemented in spirit; the "200 live concurrent calls"
is a deterministic in-process simulation, now genuinely concurrent via ThreadPool but still against a
mock target. This is correctly framed as a simulation harness, not a live fleet.)

---

## Verdict

**Deployable/operable + adequately tested for production? — PARTIAL (and a large step up).**

The offline control-plane + loopback harness (api.py, campaign_runner, loopback, scorecard,
auto_improve, gepa_mitigation, classifier) is now **production-adequate for what it claims**: 151
passing tests, CI green with a 70% coverage floor, restart-resilient persistence, per-call batch
isolation, bounded concurrency, a working dispatcher entrypoint, locked deps, and a clean frontend
build. Every BLOCKER from the prior two audits (CI-runnability, missing CI, wrong entrypoint, missing
twilio dep, no campaign isolation, no concurrency) is **closed**. The new features are not just
present but genuinely tested — the monotone curve, the held-out non-generalisation honesty
assertion, and the eval-driven clause selection all have real assertions that pass.

It is NOT yet a fully operable production *live-voice* product: the PSTN path remains a mock/loopback
simulation (correctly framed as such), there is no frontend CI or prod deploy story for the
dashboard, logging lacks correlation IDs, and a stale root `scorecard.json` is committed. None of
these are blockers for the demo/simulation product that is actually built.

**Approximate coverage:** **~72% scoped** (deterministic product logic, the CI-measured number);
**~45-50% of total .py lines** including the deliberately-omitted live voice layer. The
production-critical loopback + API + auto-improve paths are ~80-100% each.

### Top 3 gaps (prioritized)

1. **Frontend has no CI gate and no prod deploy story (T-2 / CI-1 / OPS2-4 — all 🟡).** The dashboard
   builds clean locally but nothing guards it in CI, npm deps get no dependabot PRs, and there's no
   static-host/deploy config. Add a `frontend` CI job (`npm ci && npm run build`), an `npm`
   dependabot block, and a documented static-host target.
2. **Gitignore / artifact hygiene (OPS2-3 — 🟡).** The repo-root `scorecard.json` is tracked despite
   the `server/`-scoped ignore. `git rm --cached scorecard.json` and add `/scorecard.json` to
   `.gitignore` so run artifacts don't drift into the tree.
3. **Coverage + run.sh polish (T-1, OPS2-1 — 🟡).** Add `smoke_voice.py` to `[tool.coverage.run]
   omit` (it's a live-keys script like the other omitted voice modules) so the floor reflects
   testable logic, and pre-free `WEB_PORT` in run.sh so a stale Vite doesn't silently move the
   dashboard port out from under the printed link.
