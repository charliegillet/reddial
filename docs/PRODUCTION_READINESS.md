# RedDial — Production-Readiness Assessment

> ## ▶ Audit #2 — 2026-05-31 (wiring + production pass, post-build)
>
> Re-audited after the control-plane API, dashboard, Conversation view, auto-improve loop,
> Cekura fix, and live-call wiring landed. 5-agent team (wiring · code · security · ops · devil's
> advocate) — reports: [wiring](audit/wiring.md) · [code-quality-2](audit/code-quality-2.md) ·
> [security-2](audit/security-2.md) · [ops-2](audit/ops-2.md) · [production-devils-advocate](audit/production-devils-advocate.md).
>
> **Is everything wired properly?** ✅ **YES** — all 8 flows traced against the *live* system
> (scan, auto-improve, conversation, analytics, Cekura→campaign, voice dispatcher→`/ws`, nav,
> imports). No broken/orphaned/mismatched wiring. 151 tests pass · CI green · ~78% scoped coverage.
>
> **Is it production *level*?** ⚠️ **Partially — production-grade as an OFFLINE/internal harness;
> NOT yet a hardened multi-tenant service, and the live product is unproven.** Maturity: **late-alpha**.
> Two facts hold the verdict back (both honest, neither a wiring break):
> 1. The **live voice path has never executed** — wired + safe, but no real call placed (the one true gap).
> 2. The **API has no auth / is single-user** (CORS `*`, in-process state) — an offline console, not a SaaS.
> Scorecard/auto-improve numbers are self-graded vs the mock (honestly labeled).
>
> | Dimension (now) | Grade |
> |---|---|
> | End-to-end wiring | **A** (verified live, all flows connect) |
> | Offline engine + API + auto-improve | **A−** |
> | Code quality | **B+** |
> | Security — dialing gate / secrets / PII | **A−** (fail-closed, no bypass; results/ now gitignored) |
> | Testing & CI | **B+** (151 tests, CI green, +frontend gate) |
> | Ops / deploy | **B** |
> | Service hardening (auth, multi-tenant) | **D** (single-user offline tool) |
> | Real-world product proof (live call) | **F** (never executed) |
>
> **Fixes applied this pass:** 🔴 `_emit_live_artifact` no longer auto-asserts `proves_real_world_efficacy`
> on a live breach (now `null` + operator-must-verify note); 🔴 the `final_guardrail` `[object Object]`
> render (engine now returns clause-text strings); 🟡 the inert `rounds` control (now bounds the loop);
> 🟡 untracked the root `scorecard.json` + broadened gitignore (results/ live transcripts may hold real PII);
> 🟡 `run.sh` frees the web port too; 🟡 added a **frontend CI gate** (tsc+build); 🟡 omit `smoke_voice.py`
> from coverage. Still open (by design): one recorded live call vs a non-self agent; API auth/multi-tenancy.
>
> **Verdict:** ship-ready as the **offline harness + demo + Auto-Improve entry**; for a real product, the
> next milestones are (1) one recorded gated live call, (2) API auth + persistence/multi-tenancy.

---

## Audit #1 — 2026-05-30 (original)

**Method:** 5-agent parallel audit (code quality, security/safety,
testing/reliability, ops/deploy, + an adversarial devil's advocate). Per-dimension detail in
[`docs/audit/`](audit/). Findings cross-checked: items found independently by ≥2 auditors are
marked **[converged]** (high confidence).

---

## Verdict

> **Original audit:** NOT production-ready — a hackathon prototype of the offline harness.
>
> **Now (after Phases 0–3 + the production-hardening pass):** the offline product is **production-grade
> and pilot-ready** — the deterministic engine, classifier, control-plane API, web dashboard, fail-closed
> dialing safety gate, CI/CD with a coverage gate, deploy workflow, and runbooks are all built and tested
> (129 tests, ~81% scoped coverage). The live voice path is **safe to attempt and operable**, wired
> end-to-end behind the safety gate.
>
> **The one thing that remains FALSE-if-claimed:** RedDial has **never placed a real call to an agent it
> didn't author**. Every scorecard number still grades its own mock. That is the lone blocker between
> "pilot-ready alpha" and "production-ready product," and it is **not code** — it requires an operator to
> run `efficacy_run.py --mode live` with real NVIDIA+Twilio keys against a consented agent (see
> [`DEPLOY.md`](DEPLOY.md)) and record the result.
>
> **Ready for:** internal/pilot use of the offline harness + API + dashboard; a gated, consented live
> trial. **Still NOT ready for:** selling the scorecard numbers as evidence about real agents until one
> live run exists.

## Scorecard

Two grades per dimension: **(audit)** = the original teardown · **(now)** = after Phases 0–3 +
the production-hardening pass (API, dashboard, CI/CD, ops).

| Dimension | audit → now | One-line (now) |
|---|---|---|
| Offline core (engine + classifier) | B+ → **A−** | Deterministic, ~81% scoped coverage, false-positive bug fixed, model-based posture path |
| Code quality & architecture | C → **B** | Core clean + tested; voice layer imports clean under uv; role-dispatch entrypoint |
| Security & safety (as a live dialer) | F → **B+** | Fail-closed gate (kill-switch off, allowlist, consent, call cap/rate limit) enforced in code |
| Security & safety (secrets/PII hygiene) | A− → **A** | Clean git history, fake-PII verified, no PII logging, no XSS, SECURITY.md threat model |
| Testing & reliability | D → **B+** | 129 tests, CI w/ coverage gate (≥70%), per-call isolation, retries, latent crashes fixed |
| Ops / deploy / integrations | D → **B** | Fixed entrypoint, declared+locked deps, pinned image, CI/CD, deploy workflow, runbook, API + dashboard |
| Product proof (real-world efficacy) | F → **F** | UNCHANGED — still never called a real agent; every number grades its own mock |

---

## 🔴 Blockers (must fix before "production")

1. **Deploy serves the wrong bot. [converged: code + ops]** The container entrypoint is `bot.py`,
   which is **byte-identical to the vanilla flower-shop starter** (`bot-nemotron.py`) — no
   `account_lookup`, no `FAKE_ACCOUNTS`, no weak guardrail. The vulnerable target lives only in
   `target_bot.py`, which nothing deploys. A real deploy runs the harmless starter.
   *Fix:* point the entrypoint/shim at `target_bot`/`attacker_bot`; CI-assert `account_lookup` is exposed.
2. **Voice/integration layer doesn't import clean & has undeclared deps. [converged: code + ops + testing]**
   `attacker_bot`/`target_bot` import `loguru` (and `pipecat`, `aiohttp`, `dotenv`) at module top, and
   `attacker_bot` imports `twilio` — **none declared in `pyproject.toml`/`uv.lock`**. `import attacker_bot`
   → `ModuleNotFoundError`; `uv sync --locked` won't install `twilio` → outbound dialing errors.
   This contradicts the docstrings/INTERFACES claim of "imports cleanly with no keys."
   *Fix:* declare deps + `uv lock`; lazy-guard optional imports.
3. **An autonomous PII-extracting dialer with ZERO enforced controls. [converged: security + devil's advocate]**
   `attacker_bot.place_outbound_call(to_number)` dials anything passed in. No allowlist, consent gate,
   rate limit, call cap, or kill-switch exists in code — the README/PLAN safety promises are enforced
   **only by docstrings**. The persona prompt even instructs "never mention this is a test." This is a
   TCPA / two-party-consent / pretexting hazard, not a missing feature.
   *Fix (hard precondition to any live call):* fail-closed destination allowlist + explicit consent record
   + per-run call cap + rate limit + `REDDIAL_DIALING_ENABLED` kill-switch (default OFF).
4. **The product is unproven where it counts. [converged: testing + devil's advocate]** ~1,700–2,000 LOC
   of voice/Twilio/Cekura/Nemotron glue has **0% runtime tests**; PSTN mode is literally
   `raise NotImplementedError`. The system has never placed a call, attacked a non-self target, or
   demonstrably reached Cekura. **Most embarrassing question it can't answer:** *"Show one vulnerability
   report RedDial produced by calling an agent your team didn't write — and prove the call happened."*

## 🟡 Should-fix (high-impact)

- **Scorecard grades its own homework. [converged: devil's advocate + code]** breach/leak rates and the
  "vuln score" come entirely from this attacker beating the project's own keyword-matched mock
  (`mock_llm.py`); per-vector results are binary string-overlap. "Median time-to-leak 18.0s" is a modeled
  `turns × 9s` constant (honestly labeled, but not a measurement). Don't present as real-world evidence.
- **Autonomy is a fixed schedule + brittle keyword classifier. [converged: devil's advocate + code]** The FSM
  advances through all phases even after 4 straight refusals; `_keyword_posture` collapses common real-agent
  replies ("Absolutely, I can read that back", "We don't share card numbers", "May I take your name?") to the
  do-nothing default. Against a real agent the attacker is effectively blind. Only 5–6 of the 12 vectors ever breach.
- **Graceful no-op hides a non-functional integration. [converged: ops + security + devil's advocate]**
  `cekura_integration` no-ops on missing key/dep/DNS/timeout/402/non-2xx, posting to endpoint paths
  (`/test_framework/v1/scenarios/run`, `/.../observability`) that the project's own `REFERENCES.md` flags as
  wrong (real path `observability/send-calls`). For an *assurance* product, silently manufacturing false
  confidence is the worst failure mode. *Fix:* a "connectivity check" mode that fails loudly.
- **Latent crashes / no campaign isolation. [testing]** `score(..., max_turns=0)` → ZeroDivisionError;
  `aggregate([{}])` → KeyError; one throwing call aborts the whole `run_campaign` batch and writes no scorecard.
- **No CI; suite not runnable bare. [converged: testing + ops]** A bare `pytest` aborts at collection on
  `test_nemotron_llm.py` (needs pipecat); no `.github/workflows`, no coverage floor.
- **Known voice TODOs unresolved:** `/attacker-ws` route never registered (live 404); Twilio `audio_in=8000`
  caveat; hardcoded LAN IP `192.168.7.228` as the default NIM/ASR endpoint.

## 🟢 Genuinely solid (verified, not assumed)

- Offline loopback is **deterministic** (5× byte-identical) and won't flake on content.
- **Secrets/PII hygiene is clean:** full `git log -p` scan found no real keys; `.env` gitignored;
  planted data is verified-synthetic (Stripe test BIN, specimen SSN); no PII in logs; scorecard HTML escapes all dynamic values.
- The prior review's 🔴 classifier false-positive is **genuinely fixed** (all 4 repros re-verified no-breach).
- GEPA framing is honest (suggested mitigation, not robustness); the team labels unbuilt parts honestly.
- Core engine ~83% line coverage; clean architecture, type hints, no bare excepts.

---

## Path to production (status as of the phase work)

**Phase 0 — make the offline harness shippable — ✅ DONE.** Deps declared + locked (incl.
`twilio`, `pytest`); two latent crashes guarded; campaign per-call + loopback per-turn isolation;
GitHub Actions CI (`uv sync --locked` + ruff + `pytest tests/`); import-smoke + no-op contract tests.

**Phase 1 — safe to place one real call — ✅ DONE (code) / ⚠️ one untested route.** `safety_controls.py`
fail-closed gate (kill-switch off by default, E.164 allowlist, per-call consent, `CallGuard` cap + rate
limit), wired + tested; deploy entrypoint fixed (`bot.py` role dispatcher); `twilio` dep added; LAN-IP
defaults replaced with required config; Cekura endpoint corrected + loud `check_connection()`.
**Resolved:** the media-stream path — the Pipecat runner serves telephony at `/ws` and dispatches to
`attacker_bot.bot()`; the outbound TwiML now targets `/ws` (was the 404'ing `/attacker-ws`). `make
serve-attacker` + `make live-call TO=...` is the click-to-run live path. Final confirmation needs one live call.

**Phase 2 — real autonomy ✅ / real-world efficacy ⛔ NOT YET (requires an operator live run).**
Model-based posture classifier (`posture.py`) + hardened keyword fallback replaces the brittle matcher;
`efficacy_run.py` is the single-run harness. **Loopback efficacy is stamped
`proves_real_world_efficacy = false`** — attacking our own mock is NOT evidence. Closing this blocker
requires `efficacy_run.py --mode live` against a **consented, non-self agent** (keys + the safety gate),
with the captured transcript attached — see [`DEPLOY.md`](DEPLOY.md). **Not done in this repo; not claimed.**

**Phase 3 — scale & operate — ✅ MOSTLY DONE.** Bounded concurrency (thread pool), per-call retries with
backoff, per-call transcript persistence, run/call correlation IDs + structured logging (`run_context.py`),
campaign `--budget` cost cap, pinned Docker base, Makefile, [`DEPLOY.md`](DEPLOY.md). **Still open:**
IaC/secrets management and versioned-deploy/rollback automation.

> **Bottom line:** offline harness is shippable as an internal tool; the live voice product is now
> *safe to attempt* and *operable*, but its core claim — working against a real third-party agent —
> **remains unproven** until an operator records one live run. Status moved from "demo/prototype" toward
> "alpha that's safe to pilot," **not** "production-ready."

*Detailed per-dimension findings: [code-quality](audit/code-quality.md) · [security](audit/security.md) ·
[testing](audit/testing.md) · [ops](audit/ops.md) · [devils-advocate](audit/devils-advocate.md) ·
[fix-review](audit/fix-review.md) · [phases-review](audit/phases-review.md).*
