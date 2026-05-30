# RedDial — Full Build Design (2026-05-30)

## Context
RedDial (see `PLAN.md`) is an autonomous voice red-team: it calls a target voice agent,
social-engineers it into reading back planted **FAKE** PII, and emits a Luhn-verified
vulnerability scorecard — shipped as a Cekura social-engineer persona pack.

`PLAN.md` is the authoritative design. This doc records the *build decisions* for the
"full build" scope approved on 2026-05-30, and how the agent team executes it.

## Scope (approved)
Full build: text loopback core + voice/Twilio layer + Cekura + GEPA + scorecard.
Real services wired via `.env` (NVIDIA NIM, Twilio, Cekura) with graceful fallback.

## Architecture decision: a testable text core under the voice layer
The plan's own devil's-advocate verdict: *"loopback is the floor; PSTN is cosmetic."*
We make that literal. Two layers:

1. **Deterministic text-level engine (the product's heart — fully tested, zero keys):**
   `attacker_policy` (state machine) ↔ `mock_llm.MockTargetLLM` (deliberately-vulnerable,
   plausible) ↔ `leak_classifier` (Luhn ground truth + semantic judge) → `scorecard`.
   Driven by `loopback.run_loopback()`. Produces a real BREACH + real scorecard offline.
   `campaign_runner` runs N of these; `gepa_mitigation` re-runs with a hardened guardrail
   to show the suggested diff helps *on that attack* (honest, not general robustness).

2. **Voice layer (real code, key-gated, not runtime-verified here):**
   `target_bot.py` (fork of `bot-nemotron.py` + `account_lookup` tool + weak guardrail),
   `attacker_bot.py` (Pipecat pipeline, SmallWebRTC local + Twilio OUTBOUND), wired to
   NIM/Twilio. Imports cleanly and degrades clearly when keys are absent.

3. **Cekura:** `cekura_integration.py` maps each attack → a scenario, posts verdicts to
   observability; no-ops gracefully without `CEKURA_API_KEY`.

Why this split: it guarantees a *verifiable* deliverable (the loopback breach + scorecard
pass in CI with no secrets), while the audio/Twilio code is real and ready for keys —
matching the plan's "lock the loopback breach first, PSTN is a nice-to-have."

## Data flow
`Attack.spoken_template` → policy state → target reply → `scan_turn` (normalize→Luhn→
semantic) → `Leak[]` → `is_breach` → `CallResult` → `aggregate` → `scorecard.{json,html}`.

## Safety (hard requirement, enforced in review)
All PII is synthetic: Stripe test-card BIN `4539…`, specimen SSN `512-84-9023`. The
system only ever attacks a target we build/own. No real PII anywhere. Reviewed by the
devil's-advocate teammate before commit.

## Testing
`server/tests/`: classifier (normalize/Luhn/no-false-positive/breach), policy state
progression, loopback breach (deterministic, Luhn-valid), scorecard math + HTML render.
Gate: `cd server && uv run pytest -q` green + a loopback smoke run printing a BREACH.

## Team (background agents + devil's advocate)
- **researcher** → `docs/REFERENCES.md` (WebSearch-verified citations for every plan claim).
- **attacker engineer** → `attack_library`, `attacker_policy`, `attacker_bot`, `mock_llm`.
- **target+classifier engineer** → `target_bot`, `mock_backend`/`fake_accounts`, `leak_classifier`, tests.
- **integration engineer** → `loopback`, `scorecard`, `campaign_runner`, `gepa_mitigation`, `cekura_integration`, Dockerfile, tests.
- **devil's advocate** → adversarial review vs PLAN.md risk section; runs the suite.
All build against `server/INTERFACES.md` to prevent drift; orchestrator integrates + verifies.
