# RedDial — Live LLM mode (un-mocked) vs Deterministic mode

RedDial now runs in two modes. This doc states, honestly, exactly what each is —
and what still can't be live.

## TL;DR
- **Deterministic mode (default for tests/CI + the reproducible demo):** the keyword
  `MockTargetLLM` + template attacker. Guarantees a Luhn-verified breach, a byte-identical
  run, and the monotone auto-improve curve. Needs **no keys**. This is the fixture that
  makes the demo and the 157-test suite reproducible — it is NOT deleted.
- **Live LLM mode (`make live-llm` / `live_attack.py`):** a **real Nemotron attacker ↔ real
  Nemotron target ↔ real Luhn classifier**, over **text**. Proven working: the real target
  reads back the planted card and the real classifier catches it (`breach @ turn 1`, ~2.3s/turn).

## What is genuinely LIVE (verified against `nvidia/nemotron-3-super`)
| Piece | Live? | Notes |
|---|---|---|
| Target agent | ✅ real LLM | `live_agents.RealTargetLLM` — persona + FAKE account + a deliberately-vulnerable guardrail. |
| Attacker | ✅ real LLM | `live_agents.RealAttackerLLM` — social-engineer persona, escalates over the attack ladder. |
| Posture read | ✅ real LLM | `posture.NemotronClassifier`. |
| Leak detection | ✅ already real | `leak_classifier` (regex + Luhn) — never was a mock. |
| Conversation | ✅ live, text | real per-turn latency (~1–2.3s); no modeled timing. |

Two model gotchas that are handled (don't regress them):
- **`enable_thinking=false` is required** — otherwise Nemotron spends its token budget
  reasoning and returns **empty content** (`finish_reason=length`). All live calls set it.
- **bounded timeout** (`NEMOTRON_TIMEOUT_S`, default 25s) so a slow/dead endpoint fails fast.

## What is NOT live (and won't be faked)
- **Real PSTN phone call + audio (STT/TTS over Twilio).** Cannot run in this environment;
  it's the operator's separate run (see `DEPLOY.md`: `make serve-attacker` + `make live-call`).
- **A third-party agent.** The live target is still **our own consented, deliberately-vulnerable
  agent** seeded with **FAKE PII**. So `live_attack.py` stamps `proves_real_world_efficacy: false`.
  Real-world efficacy still requires a recorded call against an agent your team did not author.

## Honesty guarantees (built in)
- **No silent live→mock.** If the endpoint is unset/errors/returns empty, the agent falls back to
  the deterministic mock and sets `live_failed = True`. The artifact records it — a "live" result
  can never be a disguised mock result.
- **A well-aligned target with a *sane* guardrail refuses** (no breach). A breach only happens when
  the target is configured to be **deliberately vulnerable** — which is RedDial's documented premise
  ("we build the target to be vulnerable"). The live loop does not manufacture a leak from a safe agent.

## Mode selection
- `live_agents.default_mode()` → `"live"` when `NEMOTRON_LLM_URL` is set and
  `REDDIAL_FORCE_DETERMINISTIC` is not set; `"deterministic"` otherwise.
- **Tests/CI stay deterministic** (no `NEMOTRON_LLM_URL`, or `REDDIAL_FORCE_DETERMINISTIC=1`) so the
  suite is offline + reproducible. The live run is network-gated (`test_live_agents.py` skips without
  the endpoint).

## Run it
```bash
cd server
make live-llm          # one live attack -> results/live_attack_*.json (needs NEMOTRON_LLM_URL in .env)
```
