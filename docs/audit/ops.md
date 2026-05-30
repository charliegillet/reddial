# RedDial — Ops / Deployment / Dependencies / Integrations Audit

Scope: production-readiness of build/packaging, configuration, integration robustness,
observability, scalability, and the deploy story. Branch `audit/production-readiness`.
Method: read README.md, PLAN.md, docs/DEVILS_ADVOCATE_REVIEW.md, docs/REFERENCES.md,
the Dockerfile/pyproject/pcc-deploy/uv.lock, all server modules, ran the test suite
(`45 passed`) and the core import check (OK), and grepped every `os.getenv/environ`,
hardcoded host, and dependency.

Legend: 🔴 BLOCKER (breaks a real deploy/live call) · 🟡 SHOULD-FIX · 🟢 OK.

---

## 1. Build / packaging

### 🔴 OPS-1 — The deployed entrypoint runs the plain starter, NOT RedDial
`server/Dockerfile:23` copies `./*.py` (good — every RedDial module lands in the image),
but the `dailyco/pipecat-base` image runs a **fixed entrypoint `bot.py`**, and
`server/bot.py` is **byte-identical to `bot-nemotron.py`** — the unmodified flower-shop
starter with no `account_lookup`, no `FAKE_ACCOUNTS`, no weak guardrail (verified:
`diff -q bot.py bot-nemotron.py` → identical; `grep account_lookup bot.py` → nothing).
The RedDial vulnerable target lives in `target_bot.py:286` and the attacker in
`attacker_bot.py`. `pcc-deploy.toml:1` deploys agent `flower-bot` from `flower-bot-secrets`.
So `pc cloud deploy` ships the sponsor's starter bot, not the RedDial target or attacker.
The PLAN's "historical `COPY ./bot.py` bug" (PLAN.md:65) is *half* resolved: the glob means
the build no longer fails, but the **runtime entrypoint still points at the wrong code**.
**Fix:** make `bot.py` the RedDial entrypoint — e.g. `bot.py` becomes a thin shim
`from target_bot import bot` (or `from attacker_bot import bot`), or set the PCC entrypoint
explicitly. Pick which agent each deploy is (`target` vs `attacker`) — one image cannot be both.

### 🔴 OPS-2 — `twilio` is not a declared dependency; outbound dialing ImportErrors
`attacker_bot.py:127` does `from twilio.rest import Client` and `place_outbound_call`
is the entire PSTN-outbound story, but `twilio` appears **nowhere** in
`pyproject.toml:6-9` or `uv.lock` (`grep -c twilio uv.lock` → 0). The Dockerfile installs
deps with `uv sync --locked --no-dev` (Dockerfile:16), so the image will not contain
twilio. The lazy import is caught and re-raised as a clear RuntimeError
(attacker_bot.py:128-131), so it degrades to a crash-with-message rather than a silent
hang — but the headline "Twilio OUTBOUND" capability cannot run as packaged.
(Note: the Twilio *serializer* `pipecat.serializers.twilio` ships inside pipecat-ai and is
fine; only the REST SDK used to *initiate* the call is missing.)
**Fix:** add `twilio` to `pyproject.toml` dependencies and re-lock (`uv lock`).

### 🟢 OPS-3 — Dependency closure for the cekura HTTP client is OK
`cekura_integration._post` (cekura_integration.py:51-59) prefers `requests`, falls back to
`httpx`. `requests` is NOT in the lock, but `httpx` IS (`grep '^name = "httpx"' uv.lock`),
and it degrades to a labeled stub if neither is present (cekura_integration.py:59). No crash.

### 🟢 OPS-4 — Core engine builds/tests cleanly with zero keys
`python3 -m pytest tests/ -q` → **45 passed in 0.02s**; the core modules
(campaign_runner, loopback, scorecard, cekura_integration, leak_classifier, attack_library,
attacker_policy, mock_llm, fake_accounts) all import with no keys and no heavy deps.
The glob `COPY ./*.py` (Dockerfile:23) does include every new module in the image.

---

## 2. Configuration

### 🔴 OPS-5 — Hardcoded LAN IP `192.168.7.228` as the default NIM/ASR endpoint
`attacker_bot.py:212,219`, `target_bot.py:400,409` (and inherited starter `bot.py:355,383`)
default `NVIDIA_ASR_URL` to `ws://192.168.7.228:8081` and `NEMOTRON_LLM_URL` to
`http://192.168.7.228:8000/v1` — a private LAN address from the original hackathon network.
In any prod/cloud deploy these resolve to nothing; if `.env` is incomplete the bot silently
points at a dead 192.168 host and every STT/LLM call times out. `nvidia_stt.py:93` similarly
defaults to `ws://localhost:8080`.
**Fix:** drop the 192.168 fallbacks — require `NVIDIA_ASR_URL`/`NEMOTRON_LLM_URL` (fail
fast with a clear error) or default to NVIDIA's hosted `https://integrate.api.nvidia.com/v1`.

### 🟡 OPS-6 — `.env.example` is missing required keys the voice path actually reads
Cross-checking every `os.getenv/environ` against `.env.example`:
- `GRADIUM_API_KEY` is read **unguarded** as `os.environ["GRADIUM_API_KEY"]`
  (target_bot.py:419, attacker_bot.py:228, bot.py:393) → a hard `KeyError` at pipeline build
  if unset. It IS in `.env.example:29`, so documented — but it is effectively **required** for
  any voice run while `.env.example` files it under an "optional"-looking section.
- `ENV` (target_bot.py:492 / attacker uses none) gates the Krisp filter — if unset (not
  `"local"`), it tries to import `KrispVivaFilter`, which only exists on Pipecat Cloud. Not
  in `.env.example`. Locally you MUST set `ENV=local` or the bot crashes on import.
- `OPENAI_MODEL` (bot-gpt.py:362) is read but absent from `.env.example`.
**Fix:** add `ENV=local` and `OPENAI_MODEL` to `.env.example`; mark `GRADIUM_API_KEY` (and
the NVIDIA URLs) as REQUIRED-for-voice in a clearly delineated block vs the optional
Twilio/Cekura keys. The required-vs-optional split is currently only implied by comments.

### 🟢 OPS-7 — Required-vs-optional is partially delineated and the no-key path is honest
`.env.example` correctly states the loopback/campaign path needs zero keys
(.env.example:5-7) and that Cekura no-ops without a key (.env.example:33). `NEMOTRON_LLM_API_KEY`
sensibly defaults to `EMPTY` (vLLM convention). Secrets are gitignored (`.gitignore` `.env`),
only `.env.example` with empty placeholders is tracked (confirmed by the devil's-advocate
PII/secret grep, DEVILS_ADVOCATE_REVIEW.md 🟢-3).

---

## 3. Integrations robustness

### 🟢 OPS-8 — Cekura integration degrades gracefully (no crash on any failure)
`cekura_integration.py` is the best-engineered integration: no key → labeled stub
(`_stub`, lines 32-37, 44-45); missing HTTP client → stub (line 59); network/DNS/timeout
caught → stub (lines 74-75); **HTTP 402 explicitly handled** as a no-op with a warning
(lines 77-79, the exact billing failure PLAN.md:82 warns about); any non-2xx → stub.
15s timeout on both clients. Auth header is the correct `X-CEKURA-API-KEY`
(line 48) matching REFERENCES.md:36. `post_observability` returns `False` on any stub so the
demo never blocks (lines 156-157).

### 🟡 OPS-9 — Cekura endpoint paths are unverified / likely wrong against the public API
`_SCENARIOS_PATH = "/test_framework/v1/scenarios/run"` (cekura_integration.py:24) and
`_OBSERVABILITY_PATH = "/test_framework/v1/observability"` (line 25). REFERENCES.md:39,78
documents that `scenarios/run` is **NOT in Cekura's public endpoint listing** and the real
observability path is `observability/send-calls`, not `test_framework/v1/observability`
(REFERENCES.md:38). So with a *real* key both POSTs will likely 404 → silently stub out →
nothing actually reaches Cekura, while the demo *looks* fine. The graceful-degrade masks a
non-functional integration.
**Fix:** confirm both paths against `docs.cekura.ai/openapi.json`; change observability to
`/observability/send-calls`; verify the scenario-registration path or use the MCP.

### 🟡 OPS-10 — `/attacker-ws` route is referenced but never registered (live-call 404)
`build_attacker_twiml` points Twilio's `<Stream>` at `wss://{host}/attacker-ws`
(attacker_bot.py:89), but no code registers that path — the Pipecat runner serves its
default WS route. On the first live outbound attempt Twilio connects back to `/attacker-ws`
and 404s. A `TODO` already flags this (attacker_bot.py:80-84) but it is unfixed.
**Fix:** register a `/attacker-ws` handler mapping to `attacker_bot.bot`, or change the
TwiML to the runner's actual default WS path.

### 🟢 OPS-11 — Twilio inbound caller-info fetch handles errors well
`target_bot.get_call_info` (target_bot.py:76-116) checks for missing creds (returns `{}`,
line 88-90), checks non-200 (logs + returns `{}`, line 100-103), and wraps everything in
try/except (line 114-116). It uses `aiohttp` (in the lock) rather than the missing twilio SDK,
so the inbound personalization path is robust. No caller-ID *verification* logic exists for
outbound, but `place_outbound_call` documents that `from_number` MUST be a verified caller ID
(attacker_bot.py:103-104) and fails fast if `VERIFIED_CALLER_ID` is unset (lines 112-124).

### 🟡 OPS-12 — NVIDIA NIM endpoints have no app-level retry/timeout/health probe
STT (`nvidia_stt.py`) reports errors via `ErrorFrame` (lines 230, 410, 443) but there is no
reconnect/retry on the NIM LLM or ASR websocket at the RedDial layer; a NIM blip during a
live call drops the turn. Combined with OPS-5 (dead default host) a misconfig is a silent
hang rather than a fast, debuggable failure. SHOULD-FIX for live ops, not a loopback blocker.

### 🟡 OPS-13 — Twilio media sample-rate ships the self-flagged 8k/8k config
`target_bot.py:518-519` (and starter `bot.py:488-489`) set BOTH
`audio_in_sample_rate=8000` and `audio_out_sample_rate=8000`. REFERENCES.md:29 + the inline
note (target_bot.py:514-517) document that Smart Turn v3 silently breaks at
`audio_in=8000` (Pipecat #3844). The code uses Silero VAD (so 8k/8k is currently OK) but the
landmine is armed if the turn strategy is ever swapped.
**Fix:** set only `audio_out_sample_rate=8000` if/when Smart Turn is adopted.

---

## 4. Observability

### 🟡 OPS-14 — Two logging stacks, no structured logging, no correlation IDs
Voice modules use `loguru` (attacker_bot.py:31, target_bot.py:41, nvidia_stt.py:15);
cekura uses stdlib `logging.getLogger("reddial.cekura")` (cekura_integration.py:21). No
single configuration, no JSON/structured output, no per-call correlation/trace ID, no log
level policy. Debugging a failed *live* call means grepping free-text loguru lines with no
call SID tying STT→policy→TTS→breach together.
**Fix:** standardize on one logger, attach the Twilio call SID / a campaign run ID to every
line, and emit JSON in cloud (`pc cloud logs` is line-based text today).

### 🟡 OPS-15 — `campaign_runner` emits no progress and no per-call persistence
`run_campaign` (campaign_runner.py:51-64) is a tight `for i in range(n)` loop that prints
**only one summary line at the very end** (lines 83-89). For the advertised 200-call batch
there is no progress output, no incremental checkpoint, and — despite PLAN.md:220 saying it
"persists transcripts + clips" and a `transcripts/` dir existing — **no transcript/clip is
written per call**; only the final `scorecard.{json,html}`. A crash at call 199 loses
everything.
**Fix:** log every Nth call, write each `CallResult` to `transcripts/` incrementally, and
checkpoint the scorecard periodically.

### 🟢 OPS-16 — Pipeline metrics are enabled
`PipelineParams(enable_metrics=True, enable_usage_metrics=True)` on both attacker
(attacker_bot.py:257) and target, so Pipecat's latency/usage metrics flow when running live.
Breach events log at WARNING (attacker_bot.py:200). No app-level health-check endpoint exists,
but PCC supplies the agent liveness layer.

---

## 5. Scalability reality-check

### 🔴 OPS-17 — The "200-call / scan-many-agents-concurrently" story does not hold
`run_campaign` is a **single-process, single-threaded, synchronous `for` loop**
(campaign_runner.py:58-60) calling `loopback.run_loopback` inline — zero concurrency, no
async, no worker pool, no queue. For the *text loopback* this is fine (45 calls run in
0.02s), but:
- The PLAN/README pitch (PLAN.md:13,43,321; README "Deploy at scale") sells "200 calls" and
  AWS-judge "concurrency story for scanning many agents." There is **no concurrency primitive
  anywhere** — no asyncio.gather, no multiprocessing, no job queue, no fan-out.
- `mode="pstn"` is `raise NotImplementedError` (campaign_runner.py:43-47), so the campaign
  cannot place real calls at all; the only working mode is in-process text loopback against a
  single mock. "200 real overnight calls" reduces to "200 deterministic text simulations of
  one mock target," which is what DEVILS_ADVOCATE 🔴-2 / the loopback timing label already
  concede.
**Reality:** to actually scan many live agents concurrently you would need: real PSTN/loopback
voice execution wired in, an async worker pool or job queue (e.g. a task runner + N PCC
agents), per-target config/fan-out, and rate limiting. None exists. The scalability claim is
aspirational; the honest framing (loopback simulation, one mock target) is what's built.
**Fix (framing):** present the campaign as a deterministic simulation harness, not a live
concurrent fleet; or build the async/queue layer before claiming concurrency to the AWS judge.

### 🟡 OPS-18 — No cost controls / spend guardrails for the live path
The only cost-related handling is the Cekura 402 no-op (cekura_integration.py:77-79). There is
**no budget cap, no max-calls limit beyond the `--n` arg, no rate limiter, no per-run spend
accounting** for NIM/Twilio/Gradium. PLAN.md:334 flags "cost explodes" as a top risk; the
mitigation ("cap at what finishes") is not implemented in code. A misconfigured live campaign
could rack up Twilio/NIM spend unbounded.
**Fix:** add a `--max-cost` / `--max-calls` guard and a rate limiter to the (future) live path.

---

## 6. Deploy story

### 🔴 OPS-19 — Laptop-only; no CI/CD, no IaC, no rollback/versioning
- **No CI/CD:** no `.github/workflows`, no Makefile, no pipeline (verified: directory absent,
  no `*.yml`/`*.yaml`/`*.tf`). The 45 tests run only when someone types `pytest` locally.
- **No infra-as-code:** the only deploy artifact is `pcc-deploy.toml` (8 lines) + a manual
  `pc cloud deploy`. NIM/AWS GPU hosts are manual `docker run` per PLAN.md:54-59.
- **Secrets management:** single shared secret set `flower-bot-secrets` (pcc-deploy.toml:2)
  via `pc cloud secrets set --file .env` (STARTER_README.md:158) — the whole `.env` uploaded
  as one blob; no rotation, no per-environment separation, no secrets-manager integration.
- **No rollback/versioning:** image tag is `latest` (Dockerfile:1 base; no app version tag);
  `pyproject.toml:3 version = "0.1.0"` is never bumped or surfaced; no release process, no way
  to roll back to a known-good agent revision beyond whatever PCC retains.
**Fix:** add a minimal CI workflow (lint + pytest on PR), pin/tag the image, and document a
two-secret-set split (target vs attacker) + a rollback procedure.

### 🟢 OPS-20 — The "behind at 3pm" MVP deploy is genuinely zero-dependency
The loopback core (loopback.py, campaign_runner.py, scorecard.py) runs offline with no keys,
no network, no Docker — `python3 campaign_runner.py --n 36` produces the scorecard. As a
hackathon-demo artifact this is deployable today; the gaps above are about *production* live
operation, not the offline demo.

---

## Ratings summary

| ID | Sev | Area | One-line fix |
|---|---|---|---|
| OPS-1 | 🔴 | entrypoint | `bot.py` must shim to `target_bot`/`attacker_bot`; today it runs the plain starter |
| OPS-2 | 🔴 | deps | add `twilio` to pyproject + `uv lock` (outbound dialing ImportErrors as packaged) |
| OPS-5 | 🔴 | config | remove `192.168.7.228` NIM/ASR defaults; require the URL or use the hosted endpoint |
| OPS-17 | 🔴 | scalability | campaign is a sync for-loop, PSTN is NotImplemented — drop the "concurrent fleet" claim |
| OPS-19 | 🔴 | deploy | no CI/CD/IaC/rollback; add lint+test CI, tag images, split secret sets |
| OPS-6 | 🟡 | config | add `ENV=local`/`OPENAI_MODEL`; mark `GRADIUM_API_KEY`+NIM URLs REQUIRED-for-voice |
| OPS-9 | 🟡 | cekura | fix endpoint paths (`/observability/send-calls`); current ones likely 404 |
| OPS-10 | 🟡 | twilio | register `/attacker-ws` route or fix TwiML path (live-call 404) |
| OPS-12 | 🟡 | nim | add reconnect/retry + fast-fail on NIM ASR/LLM |
| OPS-13 | 🟡 | twilio | set only `audio_out=8000` if Smart Turn is adopted |
| OPS-14 | 🟡 | logging | one logger, structured, attach call/run ID |
| OPS-15 | 🟡 | campaign | emit progress + persist per-call transcripts incrementally |
| OPS-18 | 🟡 | cost | add `--max-calls`/`--max-cost` guard + rate limit |
| OPS-3 | 🟢 | deps | httpx fallback present; OK |
| OPS-4 | 🟢 | build | 45 tests pass; all modules in image |
| OPS-7 | 🟢 | config | no-key path honest; secrets gitignored |
| OPS-8 | 🟢 | cekura | graceful no-op incl. explicit 402 handling |
| OPS-11 | 🟢 | twilio | inbound caller-info fetch handles errors |
| OPS-16 | 🟢 | metrics | Pipecat metrics enabled |
| OPS-20 | 🟢 | deploy | offline loopback MVP is zero-dependency |

---

## Verdict

**Deployable/operable in production? PARTIALLY — only the offline loopback core.**

The deterministic text-loopback engine (loopback / campaign_runner / scorecard / classifier)
is genuinely shippable today: zero keys, 45 passing tests, clean imports, honest no-key
framing. As a hackathon demo artifact and a self-contained simulation harness it is operable.

The **live voice product is NOT production-ready**. As packaged, a `pc cloud deploy` runs the
unmodified flower-shop starter (not RedDial), outbound dialing crashes for lack of the
`twilio` dependency, the NIM endpoints default to a dead LAN IP, and the `/attacker-ws` route
404s on first call. The "scan many agents concurrently / 200 live calls" story is not built —
the runner is a synchronous in-process loop and the PSTN mode is `NotImplementedError`.

### Top 3 ops gaps
1. **Wrong entrypoint + missing twilio dep (OPS-1, OPS-2):** the thing you deploy is not
   RedDial, and the thing that places calls can't import its SDK. The two highest-impact,
   lowest-effort blockers — fix before any live attempt.
2. **No concurrency / live execution behind the scalability pitch (OPS-17):** "scan many
   agents concurrently" is a sync for-loop with PSTN stubbed out. Either build the async/queue
   fleet or reframe the campaign as a deterministic simulation.
3. **No deploy hardening (OPS-5, OPS-19):** hardcoded LAN IP defaults, no CI/CD, one shared
   secret blob, `latest`-tagged images, and no rollback path. Fine for a laptop demo, not for
   an operable production service.
