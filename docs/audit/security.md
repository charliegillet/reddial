# RedDial — Security & Safety Audit (Production Readiness)

Auditor role: Security & Safety. Branch: `audit/production-readiness`. Date: 2026-05-30.
Scope: secrets, fake-PII enforcement, abuse/TCPA/consent controls, injection/SSRF/XSS,
PII logging, dependency supply chain. Citations are `file:line`.

This builds on `docs/DEVILS_ADVOCATE_REVIEW.md` (which already verified PII-cleanliness,
determinism, and the classifier false-positive that has since been fixed). I do **not**
re-litigate those; I focus on the **production dual-use posture**: what happens the moment
real Twilio/NIM keys are dropped in and RedDial is pointed at a live phone number.

Legend: 🔴 BLOCKER · 🟡 SHOULD-FIX · 🟢 OK

---

## Executive verdict

**Is RedDial safe to run in production as a real outbound dialer? NO — only under conditions.**

As a **key-free text-loopback harness against the bundled mock** (the default, tested path),
RedDial is safe: no secrets, provably-synthetic PII, no network egress, no PII logged. That is
the mode the README/PLAN say to ship and demo, and it holds up.

But the **voice/PSTN layer as written is not production-safe as an autonomous dialer.** Every
safety claim the README makes about outbound calling ("only dials numbers under our control or
with written consent, rate-limited, not a mass-dialer") is enforced **only by code comments** —
there is **no allowlist, no rate limit, no consent gate, and no destination validation** in the
code. The single function that places calls (`attacker_bot.place_outbound_call`) will dial any
E.164 string handed to it, as fast as it is called, with no cap. That is the gap between the
written ethics framing and the actual controls, and for an offensive auto-dialer it is the
blocker.

Top 3 must-fix safety controls before any live dialing:
1. **Destination allowlist + explicit consent gate** in `place_outbound_call` (🔴-1).
2. **Rate limit / per-run call cap / global kill-switch** on outbound dialing (🔴-2).
3. **Validate `PUBLIC_HOST`** (and `to_number` shape) before it is interpolated into TwiML
   `wss://` URLs (🟡-1).

---

## 🔴 BLOCKERS

### 🔴-1 No allowlist / consent gate — the dialer will call any number (TCPA/abuse)
`attacker_bot.place_outbound_call(to_number, ...)` (attacker_bot.py:94–136) takes an arbitrary
`to_number` and at attacker_bot.py:136 calls `client.calls.create(to=to_number, ...)` with **no
check** that the destination is owned/consented. The README (README.md:11) and PLAN
("TCPA / dialing compliance — only dials numbers under our control or with written consent;
rate-limited; not a mass-dialer", PLAN.md:290) assert controls that **do not exist in code** —
`grep` for `allowlist|consent|rate.?limit|max_calls|whitelist` across `server/*.py` returns
**only docstring prose** (attacker_bot.py:22, attacker_bot.py:102), never an enforcement branch.
For a tool whose stated purpose is social-engineering voice agents into disclosing PII, an
unguarded outbound dialer is a direct TCPA and abuse exposure: a misconfig, a typo, or a hostile
caller of this function dials a non-consented third party.
**Fix:** gate `place_outbound_call` on an explicit `CONSENTED_TARGETS` allowlist (env or config),
reject any `to_number` not on it, and require a per-target `consent_ref` argument that is logged.
Fail closed.

### 🔴-2 No rate limit / call cap / kill-switch on outbound dialing
There is no throttle anywhere: `place_outbound_call` (attacker_bot.py:94) has no cooldown or
counter, and `campaign_runner.run_campaign` (campaign_runner.py:51–64) loops `n` times (default
`n=200`, campaign_runner.py:69) — today that loop is `loopback`-only and PSTN raises
`NotImplementedError` (campaign_runner.py:42–47), which is what keeps it safe **right now**. But
the moment the PSTN path is wired (the explicit roadmap), the same uncapped `for i in range(n)`
becomes a 200-call autodial loop with no rate limit, exactly the "mass-dialer" the README
disclaims. An autonomous outbound dialer with no per-minute cap and no abort switch is a
production legal/abuse blocker.
**Fix:** add a hard per-run call cap, a token-bucket/min-interval rate limit, and an env
kill-switch (`REDDIAL_DIALING_ENABLED=false` default) that `place_outbound_call` checks first.

---

## 🟡 SHOULD-FIX

### 🟡-1 `PUBLIC_HOST` and `to_number` flow unvalidated into TwiML (SSRF / injection surface)
`build_attacker_twiml` interpolates `PUBLIC_HOST` straight into the stream URL:
`f'<Stream url="wss://{host}/attacker-ws"/>'` (attacker_bot.py:86–91), default `example.invalid`
(attacker_bot.py:74). `host` is never validated (no scheme/host allowlist, no character
filtering), so a malformed or attacker-influenced `PUBLIC_HOST` can break out of the intended URL
or point Twilio's media stream at an arbitrary host (TwiML/XML injection + SSRF-style redirection
of the call media). `to_number` (attacker_bot.py:136) is likewise passed to Twilio with no E.164
validation. Both are operator-set today (lower likelihood), but they are the kind of unvalidated
config that turns into an incident at scale.
**Fix:** validate `PUBLIC_HOST` against a hostname regex / allowlist and XML-escape it before
interpolation; validate `to_number` matches `^\+[1-9]\d{6,14}$` before dialing.

### 🟡-2 `/attacker-ws` media route is referenced but never served (live-call failure)
`build_attacker_twiml` points Twilio at `wss://{host}/attacker-ws` (attacker_bot.py:89) but no
code registers that path; the in-code `TODO` admits it (attacker_bot.py:80–84). Not a safety
breach, but the first live outbound attempt 404s the media socket. Carried forward from
`DEVILS_ADVOCATE_REVIEW.md 🟡-2`; still open.
**Fix:** register a `/attacker-ws` websocket handler mapped to `attacker_bot.bot`, or change the
TwiML to the runner's actual default WS path.

### 🟡-3 Unpinned base image in Dockerfile (supply-chain reproducibility)
`FROM dailyco/pipecat-base:latest` (Dockerfile:1) pulls a floating `:latest` tag — a moving,
unpinned base layer that can change underneath a reproducible build. The Python deps themselves
are fine (see 🟢-5), but the base OS/runtime is not pinned.
**Fix:** pin the base image to a digest (`dailyco/pipecat-base@sha256:...`) or an immutable
version tag.

### 🟡-4 Synthetic PII (incl. card/CVV/SSN) is shipped in plaintext source — pattern risk for real data
`fake_accounts.FAKE_ACCOUNTS` (fake_accounts.py:8–17) hardcodes the full card, CVV, SSN, address,
DOB in source, re-exported via `mock_backend.py:143`, and `target_bot.account_lookup` returns the
whole record unconditionally (target_bot.py:286–299: "All accounts resolve to the demo profile").
The data itself is verifiably fake (🟢-2) so this is **not** a leak today. It is flagged because
the **code path is the template a customer copies** ("pointing RedDial at a consented real agent
is a config change", PLAN.md:345): `account_lookup` returns full card+CVV+SSN with no field
redaction, and the weak-guardrail prompt (target_bot.py:348–355) is designed to read it back.
If a customer swaps `FAKE_ACCOUNTS` for a real backend (as `mock_backend.py:10–13` invites), real
PII flows through an intentionally-leaky tool with zero redaction.
**Fix:** keep the synthetic record behind a `REDDIAL_SYNTHETIC_ONLY` assertion that refuses to
return any record that isn't the known fake (e.g. assert the returned card == the planted test
BIN), so the leaky tool can *only* ever emit honeytokens, never real PII, by construction.

### 🟡-5 README/PLAN safety claims overstate the implemented controls
Beyond the misattributed pitch stats already tracked in `REFERENCES.md`, the **safety** bullets
(PLAN.md:285–291, README.md:11) present consent/rate-limit/allowlist as properties of the system.
They are aspirations, not code (see 🔴-1, 🔴-2). Shipping a dual-use offensive tool whose README
claims safety controls it doesn't enforce is a credibility and liability problem on its own.
**Fix:** either implement the controls (🔴-1/🔴-2) or reword the safety section to say the controls
are operator responsibilities not enforced by the tool.

---

## 🟢 OK (verified)

### 🟢-1 Secrets: clean in the working tree AND full git history
`git log -p --all` scanned for `AC<32hex>` (Twilio SID), `nvapi-…`, `sk-…`, `SK<32hex>`,
`AKIA…`, `xoxb-`, `ghp_`, `AIza…`, `-----BEGIN` — **no real credential anywhere** (the only
`[0-9a-f]{32}` hits are sha256 package hashes in `uv.lock`, not SIDs). `.env`/`.envrc`/`.venv`
are gitignored (.gitignore Environments block) and **not tracked** (`git ls-files` shows only
`server/.env.example`). `server/.env.example` holds empty placeholders + safety notes only
(server/.env.example:1–40); no emails or real values in tracked source. Verdict: 🟢.

### 🟢-2 Planted PII is provably synthetic
Card `4539 1488 0343 6467` is a Stripe-style Luhn-valid test BIN; SSN `512-84-9023` is
specimen/invalid-range; name/address/DOB fabricated (fake_accounts.py:8–17,
leak_classifier.py:29–35). `KNOWN_CUSTOMERS` uses reserved `+1415555xxxx` numbers
(mock_backend.py:133–136). Tests assert against these exact synthetic values
(tests/test_leak_classifier.py:17, tests/test_scorecard.py:13). No real-PII code path exists in
the default (loopback) build. Verdict: 🟢 (with the forward-looking caveat in 🟡-4).

### 🟢-3 No PII / card numbers logged to stdout or logs
The only breach log is generic — `logger.warning("BREACH — target read back a Luhn-valid card")`
(attacker_bot.py:200) — it does **not** print the card/CVV/SSN or the leaking text. `loopback.py`
emits no logging of transcript/secret content. `target_bot.account_lookup` returns the record via
the result callback but never logs its contents; `place_order` logs only an order confirmation
(target_bot.py:275). So even when real data eventually flows, the logging pattern is safe.
Verdict: 🟢.

### 🟢-4 Scorecard HTML: no XSS — all dynamic values escaped
`scorecard.write_html` routes every dynamic value (evidence spans, attack ids, field names,
totals, vector rows, time note) through `_e()` = `html.escape(..., quote=True)`
(scorecard.py:128–129, used at 164/171/191/193/201/274/278/288). Evidence spans — the one place
attacker-influenced target text lands in HTML — are escaped at scorecard.py:193. No `innerHTML`,
no script injection sink, no external assets (inline CSS only). The FAKE-DATA safety banner is
hardcoded (scorecard.py:269). Verdict: 🟢.

### 🟢-5 Python dependency supply chain is pinned and reproducible
`pyproject.toml` declares loose top-level ranges (`pipecat-ai[...]>=1.3.0`,
`pipecatcloud>=0.7.1`, pyproject.toml:6–9), **but** `uv.lock` pins the full transitive set —
291 packages, each with `sha256` hashes — and the Dockerfile installs with `uv sync --locked`
(Dockerfile:14–18), so builds are reproducible and tamper-evident at the package level. (Base
image tag is the one gap — see 🟡-3.) No obviously-abandoned or typosquat-looking deps observed.
Verdict: 🟢 for Python deps.

### 🟢-6 Cekura egress sends metadata only — no PII values, graceful no-op
`cekura_integration` posts only verdict/score/grade and **field *names*** (`fields_leaked`),
never the secret values (cekura_integration.py:146–155). `CEKURA_BASE_URL` is operator config,
not attacker-controlled, so the URL concat (cekura_integration.py:47) is not a real SSRF vector.
Without a key it no-ops and never crashes/blocks (cekura_integration.py:32–45). Verdict: 🟢
(minor: it could pin/allowlist the base host for defense-in-depth).

---

## Findings table

| # | Sev | Location | One-line fix |
|---|-----|----------|--------------|
| 🔴-1 | BLOCKER | attacker_bot.py:94–136 | Add destination allowlist + required consent_ref; reject non-allowlisted numbers (fail closed). |
| 🔴-2 | BLOCKER | attacker_bot.py:94; campaign_runner.py:51–64 | Add per-run call cap + rate limit + `REDDIAL_DIALING_ENABLED` kill-switch (default off). |
| 🟡-1 | SHOULD | attacker_bot.py:86–91, :136 | Validate+XML-escape `PUBLIC_HOST`; validate `to_number` against E.164 regex. |
| 🟡-2 | SHOULD | attacker_bot.py:89 | Register `/attacker-ws` WS route (or fix TwiML path) before first live call. |
| 🟡-3 | SHOULD | Dockerfile:1 | Pin `dailyco/pipecat-base` to a digest/immutable tag. |
| 🟡-4 | SHOULD | fake_accounts.py:8–17; target_bot.py:286–299 | Assert `account_lookup` can only return the known synthetic honeytoken. |
| 🟡-5 | SHOULD | README.md:11; PLAN.md:285–291 | Implement the safety controls or reword claims to "operator responsibility". |
| 🟢-1..6 | OK | — | Secrets, fake-PII, no-PII-logging, no-XSS, pinned deps, metadata-only egress all verified. |

---

## Conditions for production use

RedDial is **safe to ship and demo today in loopback mode** (no keys, mock target, fake PII).
It is **NOT safe to enable as a live outbound dialer** until 🔴-1 and 🔴-2 are implemented and
🟡-1 / 🟡-4 are addressed. Recommended gating: ship the voice/PSTN layer **disabled by default**
behind the `REDDIAL_DIALING_ENABLED` kill-switch, and require allowlist + consent + rate-limit
config to be present before any `place_outbound_call` succeeds.
