# RedDial — Security & Responsible Use

RedDial is a **red-team tool**: it autonomously social-engineers voice agents to
surface PII-leak vulnerabilities. That makes its own safety posture a first-class
security concern. This document covers the threat model, the dialing safety gate,
the FAKE-PII policy, consent/responsible-use, and how to report vulnerabilities.

> One-line stance: **offline-by-default, fail-closed on anything that can reach the
> real world.** The default build cannot place a call.

---

## 1. Threat model

**What RedDial is.** An offline harness (attacker FSM ↔ self-authored vulnerable
mock ↔ Luhn-based leak classifier → scorecard) plus a gated live voice path that
can dial a real agent over PSTN.

**Assets to protect**
- Real third parties from unconsented/abusive automated calls (TCPA, two-party-consent law).
- Secrets: NVIDIA/Gradium/Twilio/Cekura/OpenAI keys, the Pipecat Cloud API key.
- Trust in the scorecard: it must never silently manufacture false confidence.
- The repo: no real PII, no real secrets in git history.

**Adversaries / abuse cases**
- A malicious or careless operator weaponizing the dialer for harassment, vishing,
  or pretexting real people/companies.
- An attacker stealing committed secrets, or a leaked `.env`.
- Supply-chain risk via dependencies or the pinned container base.
- The tool deceiving *itself*: a no-op integration (Cekura) presenting as success.

**Trust boundaries**
- **Offline core (trusted, default):** no network egress to third parties, FAKE
  PII only, no keys required. The control-plane API (`api:app`) lives here and
  exposes ONLY offline scans — never live dialing.
- **Live voice path (untrusted/dangerous):** real PSTN egress. Guarded by the
  fail-closed dialing gate (§2). CLI-only; never exposed via the HTTP API.

**Out of scope:** the security of the target agents RedDial tests; the carrier/PSTN;
Pipecat Cloud / Cekura platform security.

---

## 2. The dialing safety gate (fail-closed)

Enforced in code (`safety_controls.py`), not by documentation. Outbound dialing is
**refused** unless **every** condition holds:

1. **Kill-switch on:** `REDDIAL_DIALING_ENABLED=1` — **default OFF** (and OFF in the
   Dockerfile). A fresh/default deploy is physically incapable of dialing.
2. **Destination allowlisted:** the number is valid **E.164** AND present in
   `REDDIAL_DIAL_ALLOWLIST`. An empty allowlist refuses everything.
3. **Per-call consent:** the caller passes `consent=True`, affirming written consent
   for that specific destination.
4. **Volume controls:** under the `REDDIAL_MAX_CALLS` per-process cap and the
   `REDDIAL_MIN_CALL_INTERVAL_S` rate limit (`CallGuard`).

Fail-closed means any missing/ambiguous condition → **refuse**, never "best effort
dial." See [RUNBOOK.md §6](RUNBOOK.md) for the emergency kill procedure.

---

## 3. FAKE-PII policy

The vulnerable target and all offline fixtures are seeded with **verified-synthetic**
data only:

- Card numbers use the **Stripe test BIN** (e.g. `4242…`), Luhn-valid but non-functional.
- SSNs are **specimen/placeholder** ranges, never real.
- Names/accounts are fabricated.

Rules:
- **Never** plant real PII in `fake_accounts.py`, fixtures, transcripts, or tests.
- The leak classifier matches the synthetic patterns; using real data would both be
  a privacy violation and corrupt results.
- Scorecard HTML escapes all dynamic values (no stored XSS via transcripts).
- No PII is written to logs.

---

## 4. Consent & responsible use

RedDial may only dial a number when **all** are true:

- You **own** the number/agent, **or** hold **written consent** from its owner.
- You comply with TCPA and any **two-party / all-party consent** recording laws in
  the relevant jurisdiction.
- The call volume/cadence is within the configured caps and is not harassing.

Do **not**:
- Dial third parties you have not gotten consent from.
- Present the offline scorecard as evidence about a real agent (it grades RedDial's
  own mock; loopback efficacy is stamped `proves_real_world_efficacy = false`).
- Disable the safety gate (`REDDIAL_SKIP_PREFLIGHT`, blanket allowlists) in production.

The attacker persona may instruct the bot to act as a normal caller; this is a
property of the *simulated adversary*, not a license to deceive real people. Consent
and legal compliance are the operator's responsibility and are enforced by the gate.

---

## 5. Secrets hygiene

- `.env` is gitignored; **never commit it**. Real keys must never enter git history.
- Push secrets with `scripts/setup-secrets.sh` (Pipecat Cloud secret set + GitHub
  Actions). The script never echoes secret values.
- The deploy workflow reads `PIPECAT_CLOUD_API_KEY` from the `production`
  environment; runtime bot secrets live in the Pipecat Cloud secret set, not in the
  image or workflow.
- Pin the container base (`dailyco/pipecat-base:<tag>`, ideally a digest) — never
  `:latest` in prod. Dependabot watches `pip` (`/server`) + `github-actions` weekly.
- Rotate any key that may have been exposed; revoke leaked Twilio tokens promptly
  (they can place real calls).

---

## 6. Integration honesty

For an *assurance* product, silent failure is the worst outcome. The Cekura
integration must **fail loudly**: `make cekura-check` (`check_connection()`) reports
explicit status — including **402 Payment Required**, DNS, timeout, and non-2xx —
rather than no-oping into false confidence. Treat a green scorecard with a broken
integration as untrustworthy until connectivity is verified.

---

## 7. Reporting a vulnerability

If you find a security or safety issue (especially anything that could let RedDial
dial without passing the full gate, leak secrets, or emit real PII):

- **Do not** open a public issue with exploit details.
- Report privately to the maintainers (security contact / private advisory). Include:
  affected version/commit, reproduction, and impact.
- For a dialing-safety bug, **stop all dialing first** (RUNBOOK §6), then report.
- Expect acknowledgement and a coordinated fix/disclosure timeline. Do not test
  against third parties you do not own as part of any report.
