# RedDial — Deploy & Operate

Covers the offline harness, the gated live voice path, and how to run a real
efficacy test (the only thing that closes audit BLOCKER 4).

## Roles

`bot.py` dispatches by `REDDIAL_ROLE` (default `target`):

| Role | Runs | Use |
|---|---|---|
| `target` | the deliberately-vulnerable agent (FAKE PII) | the bot RedDial dials into |
| `attacker` | the autonomous social-engineer pipeline | places the gated outbound call |
| `flower` | the original Field & Flower starter | reference / "break a real agent" demo |

## Offline harness (no keys)

```bash
cd server
make install         # uv sync --locked
make test            # 100+ tests
make loopback        # one deterministic Luhn-verified breach
make campaign N=200  # overnight batch -> scorecard.{json,html} (+ transcripts/ with --persist)
```

## Build & deploy the voice image

The Pipecat base image (`dailyco/pipecat-base`) is published for **linux/arm64
only** — Pipecat Cloud runs arm64. Build for arm64 with buildx; on an amd64 host
this uses QEMU emulation (CI does this automatically). Pin a **real** tag — the
lowest published tag is `0.1.2`; `0.0.8` never existed. Use the digest in prod.

```bash
# `make build` now always builds linux/arm64 via buildx (QEMU on amd64, native on
# Apple Silicon) and defaults BASE to the real, published 0.1.20-py3.12 tag:
make build TAG=v0.1.0                                   # never :latest in prod

# Equivalent explicit invocation (what `make build` runs under the hood):
docker buildx build --platform linux/arm64 \
  --build-arg PIPECAT_BASE=dailyco/pipecat-base:0.1.20-py3.12 \
  -t reddial:v0.1.0 server

pcc deploy                                              # Pipecat Cloud (pcc-deploy.toml)
```

> **Pin the digest in prod.** `0.1.20-py3.12` is a moving tag; for reproducible
> deploys resolve and pin the immutable digest in `server/Dockerfile`
> (`dailyco/pipecat-base@sha256:...`). The tag is fine for CI/dev.

### Selecting the bot role at deploy time (audit C3)

Pipecat Cloud injects runtime env **only** from the deploy **secret set**
(`reddial-secrets`, named in `server/pcc-deploy.toml`) — **not** from the shell
that runs `pcc deploy`, and `pcc-deploy.toml` accepts no inline `env`/`role` key
(adding one is rejected as an unexpected key). So `REDDIAL_ROLE` must live in the
secret set. Set it before deploying:

```bash
pcc secrets set reddial-secrets REDDIAL_ROLE=attacker --skip   # target | attacker | flower
pcc deploy
```

The `Deploy (Pipecat Cloud)` workflow does this automatically: its role dropdown
upserts `REDDIAL_ROLE` into `reddial-secrets` (an upsert that leaves other
secrets intact) right before `pcc deploy`, so the dropdown is no longer inert.

Required env (see `.env.example`): `NVIDIA_ASR_URL`, `NEMOTRON_LLM_URL` (no defaults —
a missing value fails loudly rather than dialing a dead dev IP), `GRADIUM_API_KEY`,
and for outbound: `TWILIO_ACCOUNT_SID/AUTH_TOKEN`, `VERIFIED_CALLER_ID`, `PUBLIC_HOST`.

## Outbound dialing safety gate (fail-closed)

Dialing is **refused** unless **all** hold (enforced in `safety_controls.py`):

- `REDDIAL_DIALING_ENABLED=1` (kill-switch, default OFF)
- destination is E.164 **and** in `REDDIAL_DIAL_ALLOWLIST`
- per-call `consent=True` (you affirm written consent)
- under the `REDDIAL_MAX_CALLS` cap + `REDDIAL_MIN_CALL_INTERVAL_S` rate limit

```bash
make cekura-check    # verify Cekura connectivity (explicit status, never a silent no-op)
```

## Running a REAL efficacy test (closes BLOCKER 4) — click-to-run

The offline scorecard attacks RedDial's **own mock** — it is **not** evidence about a
real agent. To produce real evidence, an operator with keys + consent runs two commands:

```bash
# (1) Serve the attacker bot. The Pipecat runner exposes the telephony media socket
#     at /ws and dispatches it to attacker_bot.bot(); our TwiML streams back to /ws.
make serve-attacker PUBLIC_HOST=your-app.ngrok.io     # needs NVIDIA + Gradium keys

# (2) In another shell: place ONE gated, consented call (fail-closed safety gate).
export REDDIAL_DIALING_ENABLED=1
export REDDIAL_DIAL_ALLOWLIST=+1XXXXXXXXXX             # a number you own / have written consent for
make live-call TO=+1XXXXXXXXXX                         # = efficacy_run.py --mode live --to ... --consent
```

Flow: `live-call` → gated `place_outbound_call` → Twilio dials the target → Twilio
opens the media stream back to `wss://$PUBLIC_HOST/ws` → the runner runs the attacker
pipeline → on completion it writes `results/efficacy_live_<id>.json` (transcript +
`leak_classifier` verdict, `target_kind="real-agent"`). `--mode loopback` always
stamps `proves_real_world_efficacy = false`. The media path is `/ws` (the runner's
route); override with `REDDIAL_WS_PATH` only if you front the bot with a custom server.

## Operability

- **Correlation:** every campaign has a `run_id`; every call a `call_id` (`run_context.py`).
- **Persistence:** `--persist` writes each call's transcript to `transcripts/<run_id>/`.
- **Concurrency:** `--concurrency N` (thread pool) for the live/campaign path.
- **Retries:** `--retries N` (exponential backoff) for transient live failures.
- **Cost control:** `--budget N` caps calls; the safety `CallGuard` caps per-process volume.
- **Logging:** `REDDIAL_LOG_LEVEL`; structured format via `run_context.setup_logging()`.

## Known follow-ups (tracked in docs/PRODUCTION_READINESS.md)

- ~~Register the `/attacker-ws` websocket route~~ — RESOLVED: the runner serves `/ws` and the
  outbound TwiML now targets it (`REDDIAL_WS_PATH=/ws`). Verify on the first live call.
- Real-world efficacy remains **unproven** until a live run against a non-self agent is recorded.
