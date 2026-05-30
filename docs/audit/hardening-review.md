# Devil's-Advocate Review — Production-Hardening Work

**Branch:** `feat/production-hardening` · **Date:** 2026-05-30 · **Method:** adversarial,
evidence-based, run under `uv run` from `server/`. Verdict scale 🔴/🟡/🟢.

> **TL;DR:** The hardening is real and honest — CI is genuinely green (129 passed, 80.78%
> coverage), the omit list is **not** gaming coverage, the API is provably offline-only, and
> docs/dashboard correctly preserve the "loopback is not real-world evidence" caveat. It makes
> the offline harness **operable and presentable**. But the core production gap — *never proven
> against a real third-party agent* — is **unchanged**, and nothing in this work claims
> otherwise. One concrete new bug: the `/scans` `concurrency` field is uncapped.
>
> **Did hardening advance prod-readiness? PARTIAL. Overclaimed? No (one docstring inaccuracy).
> Top fix: cap `concurrency` in `ScanRequest`.**

---

## 1. CI will actually be GREEN — 🟢

Ran the exact gate from `server/`:

- `uv run ruff check .` → `All checks passed!`
- `uv run pytest tests/ -q --cov=. --cov-fail-under=70` → **129 passed**, **TOTAL 80.78%**,
  `Required test coverage of 70% reached.`

**Coverage omit list is HONEST — not gaming.** `pyproject.toml:38-48` omits
`nvidia_stt.py, nemotron_llm.py, target_bot.py, attacker_bot.py, bot-gpt.py, bot-nemotron.py,
mock_backend.py, tests/*, test_nemotron_llm.py`. I verified each is genuinely untestable here:
- `nvidia_stt.py` / `nemotron_llm.py` — top-level `websockets`/`pipecat`/`loguru` imports,
  need live NIM/ASR (verified imports, file heads).
- `attacker_bot.py` / `target_bot.py` — Pipecat pipelines needing NIM+Twilio keys.
- `bot-gpt.py` / `bot-nemotron.py` / `mock_backend.py` — the **vanilla flower-shop starter**;
  `mock_backend.py` is pure data dicts (4 control-flow lines) imported only by the other
  omitted starter/bot files (`grep` confirms no product module imports it).

Crucially, **no testable product logic is hidden**: `api.py` 99%, `scorecard.py` 100%,
`safety_controls.py` 95%, `leak_classifier.py` 91%, `posture.py` 91%, `campaign_runner.py` 74%,
`loopback.py` 82% are all *in* the floor. The 70% bar with an 81% actual is honest headroom.

**pyright is genuinely non-blocking:** `ci.yml:40-42` `uv run pyright` + `continue-on-error: true`,
with an honest comment about ~30 preexisting voice-layer errors. The authoritative gate is the
test/coverage step (always runs).

**docker-build would build:** `server/Dockerfile` pins `ARG PIPECAT_BASE=dailyco/pipecat-base:0.0.8`
(no `:latest`), `uv.lock` is present (734 KB, `twilio` resolved 3×), and the image runs
`uv sync --locked --no-install-project --no-dev`. `ci.yml:74-83` builds with no push. Valid.

## 2. API safety — 🟡 (offline-only confirmed; one uncapped input)

**Offline-only: CONFIRMED.** `grep -niE "place_outbound|pstn|twilio|dial|outbound" api.py`
returns only docstring/description text — **zero code paths**. `create_scan` (`api.py:156-162`)
hard-forces `mode="loopback"`; there is no parameter or branch that can reach PSTN/Twilio.
Live dialing stays CLI-only behind `safety_controls.py`. Strong.

**`n` IS capped** at `MAX_SCAN_N=500` (`api.py:33,156` `min(max(1, req.n), MAX_SCAN_N)`).

**🟡 FINDING — `concurrency` is NOT capped.** `ScanRequest.concurrency` (`api.py:78`) has
`ge=1` but **no upper bound**, and it flows straight into
`ThreadPoolExecutor(max_workers=concurrency)` (`campaign_runner.py:120`). I verified
`POST /scans {"n":2,"concurrency":300}` returns **200** — accepted. A request like
`{"n":500,"concurrency":500}` can spawn up to ~500 threads on a synchronous endpoint. The
module docstring (`api.py:10-11`) even claims *"`n` is hard-capped … requests never block for
long"* while silently leaving the thread fan-out uncapped — a minor doc/behavior mismatch.
Severity is **low** (offline, fake data, single-user tool, frontend hardcodes 4) but it is a
real unvalidated-input/resource-exhaustion vector at the trust boundary. **Fix:** add
`le=<small N>` to the `concurrency` field (or `min()` it like `n`).

**CORS `allow_origins=["*"]`** (`api.py:55`): acceptable for an offline FAKE-data tool with
`allow_credentials=False` and no secrets/live actions — but **flagged** as it would be unsafe
if this API ever gained authenticated or live capability. No injection (no SQL/shell/eval; all
input is Pydantic-typed; `run_id` only used as dict key / 404 path).

## 3. Frontend honesty + correctness — 🟢

- **FAKE-DATA banner present & prominent:** `App.tsx:60-63` — "⚠ ALL DATA IS FAKE — Stripe test
  BIN … Offline loopback against a mock we own. No real PII, no live dialing from this console."
- **Does not imply real-world efficacy:** `App.tsx:80-82` — "Results are a loopback scorecard,
  **not proof against a real agent**." Footer (`:178`) "offline harness · all data synthetic."
  No string anywhere claims live calls.
- **API client contract matches `api.py`/`scorecard.py` exactly.** Cross-checked
  `frontend/src/api.ts` interfaces against `scorecard.aggregate()` output (`scorecard.py:95-117`)
  and `campaign_runner` additions (`run_id`, `failed_calls`, `time_note`): `breach_rate`,
  `leak_rate`, `max_grade`, `max_score`, `distinct_fields_leaked`, `by_vector`
  (`runs/leaks/breaches/fields/leak_rate`), `evidence_samples`
  (`attack_id/fields/evidence_span/seconds_to_first_leak/turns_to_first_leak`),
  `median_time_to_leak_s`, `total_calls` — **all field names align**.
- **No obvious runtime bug** (static review; cannot `npm` build here). `evidence_span` rendered
  in `<pre>` (`App.tsx:169`) is React-escaped (no XSS). Grade fallback `"—"` → `--ink-faint`
  is handled (`:39-40`). Optional fields guarded with `??`.

## 4. deploy.yml / secrets — 🟢

- **Manual-only:** `deploy.yml:5-6` `on: workflow_dispatch` only — no push/PR trigger by design.
- **Gated on tests:** `deploy` job `needs: gate` (`:51`); `gate` re-runs lint + `pytest tests/`
  (`:30-47`) since `workflow_dispatch` doesn't auto-run CI. Correct.
- **`production` environment** (`:55`) — supports required-reviewer protection rules.
- **`setup-secrets.sh` never echoes values.** `get_env_value` (`:69-82`) parses without printing;
  pcc path passes the value via **env var** (`REDDIAL_SECRET_VALUE`, `:95-96`) to keep it out of
  `argv`/process list — a genuinely thoughtful touch. `gh secret set --body` (`:114`) doesn't
  echo. Closing message "(no secret values were printed)".
- **Fails closed on missing `.env`:** `:33-37` exits 1 with a remediation hint. `set -euo pipefail`.
- Minor: `gh secret set --body "${val}"` puts the value in the local `gh` process argv (visible to
  local `ps` only, not logs/CI) — acceptable for a local operator script; the pcc path is stricter.
  No leakage in CI logs (deploy workflow reads secrets from the `production` environment, not argv).

## 5. docker-compose / RUNBOOK / SECURITY — 🟢

- **Compose forces the safe role + dialing OFF:** `docker-compose.yml:29-30`
  `REDDIAL_ROLE: target` and `REDDIAL_DIALING_ENABLED: ""` (overrides `.env`), runs `api:app`
  only (`:23`), comment states it never dials. `Dockerfile` also defaults
  `ENV REDDIAL_DIALING_ENABLED=` (empty) and `REDDIAL_ROLE=target`. No dangerous default.
- **Ports:** only `8080:8080` exposed (the offline API). No live-bot/media ports.
- **Docs do NOT overclaim.** `SECURITY.md:91-93` forbids presenting the offline scorecard as
  real-agent evidence ("loopback efficacy is stamped `proves_real_world_efficacy = false`").
  `RUNBOOK.md:37-38` "attacks RedDial's **own mock** — the scorecard is NOT evidence about a real
  third-party agent." The fail-closed gate is documented as enforced in `safety_controls.py`, not
  prose (`SECURITY.md:44-59`, `RUNBOOK.md:104-119`), and the kill-switch is OFF by default.
  `RUNBOOK.md:155` even keeps the **unresolved `/attacker-ws` 404 TODO** visible. Honest.

## 6. Did this advance prod-readiness, or chrome over the same gap? — Honest answer

**It is operability/presentation chrome over an unchanged core gap — and it says so.** The API +
dashboard make the OFFLINE harness drivable over HTTP and viewable, plus CI/CD/ops/docs make it
*shippable as an internal tool*. That is real, useful hardening. But every number the dashboard
shows still comes from the attacker beating the project's **own** keyword-matched mock. The
PRODUCTION_READINESS verdict's Blocker #4 ("never called a real agent"; PSTN
`raise NotImplementedError`) and the `/attacker-ws` 404 TODO are **untouched** by this work.
Critically, **nothing here implies otherwise** — the banner, the run-panel note, and both docs
all repeat the caveat. So: advances **operability**, not **product proof**.

## 7. Single most important thing still wrong/missing

**The product has still never placed a call against an agent the team didn't write, and this
hardening doesn't change that.** Live efficacy (`efficacy_run.py --mode live` against a consented
non-self agent, with `/attacker-ws` registered and a captured transcript) remains the one blocker
that separates "alpha that's safe to pilot" from "production-ready." Everything new is plumbing
around that hole. (Secondary, and the only concrete *new* defect: the uncapped `concurrency`
field in §2.)

---

## Per-area grades

| Area | Grade | Evidence |
|---|---|---|
| CI green + honest coverage | 🟢 | 129 passed, 80.78%, omit list verified non-gaming |
| API offline-only | 🟢 | zero PSTN/Twilio code paths in `api.py` |
| API input validation | 🟡 | `concurrency` uncapped (`api.py:78` → `campaign_runner.py:120`) |
| Frontend honesty/contract | 🟢 | banner + caveats present; field shapes match exactly |
| deploy.yml / secrets | 🟢 | manual, test-gated, `production` env, no secret echo |
| compose / RUNBOOK / SECURITY | 🟢 | safe role, dialing OFF, no overclaim, TODO kept visible |
| Core product proof | 🔴 (unchanged) | still never called a real agent; PSTN `NotImplementedError` |

**Did hardening advance prod-readiness?** PARTIAL (operability/ops yes; product proof no).
**Anything overclaimed?** No — only one docstring inaccuracy (`api.py:10-11` implies all scan
work is bounded while `concurrency` isn't).
**Top fix:** cap `concurrency` in `ScanRequest` (`le=` or `min()`), and correct the docstring.

---

## Maintainer resolution (post-review)

- **🟡 unbounded `concurrency` — FIXED.** `ScanRequest.concurrency` now has `le=MAX_CONCURRENCY`
  (16) and `create_scan` also `min()`-clamps it defensively before the thread pool. Over-cap
  requests now 422. Added `test_scan_concurrency_is_capped`. The api.py docstring's "bounded work"
  claim is now true for both `n` and `concurrency`.
- 🟢 findings stand (CI green, honest coverage omit, offline-only API, honest frontend/docs).
- 🔴 unchanged & correctly unclaimed: real-world efficacy still requires one operator live run.

Suite: 130 passed; ruff clean; coverage ~81% (floor 70%).
