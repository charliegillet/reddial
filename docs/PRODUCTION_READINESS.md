# RedDial — Production-Readiness Assessment

**Date:** 2026-05-30 · **Method:** 5-agent parallel audit (code quality, security/safety,
testing/reliability, ops/deploy, + an adversarial devil's advocate). Per-dimension detail in
[`docs/audit/`](audit/). Findings cross-checked: items found independently by ≥2 auditors are
marked **[converged]** (high confidence).

---

## Verdict

> **NOT production-ready.** RedDial today is a **strong hackathon demo / prototype of the *offline*
> harness**, not a shippable product. The part that is real, tested, and safe — the deterministic
> text loopback (attacker FSM ↔ self-authored vulnerable mock ↔ Luhn classifier → scorecard) — is
> **not the product**. The actual product (autonomously *calling real third-party voice agents*
> over PSTN and producing a trustworthy vulnerability report) is **unbuilt where it counts,
> untested, and legally hazardous to ship as-is.**
>
> **Safe/ready for:** running the offline loopback as an internal demo or research harness (after
> the two latent-crash fixes + CI).
> **NOT ready for:** any live outbound dialing, customer-facing scans, or presenting the scorecard
> numbers as evidence about real agents.
>
> **Distance to production (devil's advocate estimate): ~2–4 months** of focused work.

## Scorecard

| Dimension | Grade | One-line |
|---|---|---|
| Offline core (engine + classifier) | **B+** | Solid, deterministic, 83% line coverage, prior false-positive bug fixed |
| Code quality & architecture | **C** | Core clean; voice layer doesn't import clean & isn't what deploys |
| Security & safety (as a live dialer) | **F** | Zero enforced consent/allowlist/rate-limit on a PII-extracting autodialer |
| Security & safety (secrets/PII hygiene) | **A−** | Clean git history, fake-PII verified, no PII logging, no XSS |
| Testing & reliability | **D** | 33% overall coverage; voice/integration layer 0%; no CI; latent crashes |
| Ops / deploy / integrations | **D** | Wrong deploy entrypoint, undeclared deps, LAN-IP defaults, no CI/CD |
| Product proof (real-world efficacy) | **F** | Every number comes from grading its own mock; never called a real agent |

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
**Still open:** `/attacker-ws` route registration — code TODO, can't be verified without a live call.

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
