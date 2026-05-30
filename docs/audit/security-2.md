# RedDial — Security & Safety Audit #2 (Live-Call Wiring)

Auditor role: Security & Safety. Branch: `audit/production-wiring`. Date: 2026-05-31.
Scope: the now-WIRED live PSTN path (`make serve-attacker` + `make live-call` →
`place_outbound_call`). Builds on `docs/audit/security.md` (which flagged the dialing
gate as the BLOCKER). This pass re-verifies whether the gate is fail-closed end-to-end
now that live is real, and looks for a bypass. Citations are `file:line`.

Legend: 🔴 BLOCKER · 🟡 SHOULD-FIX · 🟢 OK

---

## Executive verdict

**Is RedDial SAFE to run the live call as wired? YES — only under conditions (operator
must own/consent the target; one-call discipline).**

The two prior BLOCKERS (🔴-1 no allowlist/consent, 🔴-2 no cap/kill-switch) are **CLOSED**.
`server/safety_controls.py` now implements a real fail-closed gate and `place_outbound_call`
calls it **first, before any Twilio work** (attacker_bot.py:170-177). I attempted to find a
dial path that skips the gate (efficacy_run live, the API, the make targets, the
serve-attacker media leg) and **found none** — every route to `client.calls.create`
passes through `check_destination` + `CallGuard.acquire`. 50/50 safety + API tests pass.
Secrets are clean in tree and history. The control-plane API exposes **no** live dialing.

Remaining items are SHOULD-FIX, all on the *new* live capture path: the live artifact
writes a connected real agent's transcript (potential real PII) to `results/` in
plaintext with no redaction, and `make live-call` auto-affirms `--consent` (operator
self-attestation, not a logged per-target consent record).

Top 3 safety items (all SHOULD-FIX, none blocking the gate):
1. The live efficacy artifact persists the **real connected agent's full transcript** to
   `results/efficacy_live_*.json` unredacted — real PII at rest (🟡-1).
2. `make live-call` hardcodes `--consent`, so consent is operator self-attestation with
   no per-target `consent_ref` logged (🟡-2).
3. `CallGuard.acquire()` increments the cap *before* the Twilio-config check, so a
   misconfigured (keyless) live attempt still burns a cap slot (🟡-3, minor).

---

## 1. Dialing safety gate — end-to-end trace (fail-closed?) 🟢

**The gate is fail-closed and there is no bypass.** Trace:

`place_outbound_call(to_number, ..., consent=False)` (attacker_bot.py:152) runs, **as its
first statements before reading any credential**:

1. `safety_controls.check_destination(to_number, consent=consent)` (attacker_bot.py:172)
   — raises `DialingNotAllowed` unless ALL hold (safety_controls.py:76-97):
   kill-switch `REDDIAL_DIALING_ENABLED` ∈ {1,true,yes} (safety_controls.py:88, default
   FALSE at :58), `to_number` strict E.164 `^\+[1-9]\d{7,14}$` (safety_controls.py:92,:37),
   `to_number ∈ REDDIAL_DIAL_ALLOWLIST` (safety_controls.py:94), `consent=True`
   (safety_controls.py:96). Default-deny is unit-proven: `test_default_is_fail_closed`
   refuses even a valid consented number with no env (tests/test_safety_controls.py:29-32).
2. `_dial_guard().acquire()` (attacker_bot.py:176) — per-process cap (default 50,
   never unlimited; safety_controls.py:46,:140-142) + optional min-interval rate limit
   (safety_controls.py:154-171). Reserved **before** dialing so back-to-back allowlisted
   calls can't become an unthrottled autodialer.
3. `validate_public_host(...)` (attacker_bot.py:177) before TwiML build.

Only after all three does it read Twilio creds and call `client.calls.create`
(attacker_bot.py:209).

**Bypass attempts — all negative:**
- **`efficacy_run.py --mode live`**: `run_live_efficacy` (efficacy_run.py:68-91) calls
  `attacker_bot.place_outbound_call(to_number, consent=consent)` (efficacy_run.py:80) —
  no separate dial path, gate applies. `--to` required (efficacy_run.py:115).
- **The API**: grepped api.py for `twilio|pstn|place_outbound|attacker_bot|dial` — only
  docstrings asserting OFFLINE-only (api.py:8-9,:352,:481). `/scans` forces
  `mode="loopback"` (api.py:359); `/auto-improve` uses the mock engine (api.py:487).
  Live probe confirmed: `POST /scans` returns a loopback summary, and
  `/dial /call /live /pstn /outbound /place_outbound_call` all 404. **No live path.**
- **`make serve-attacker`** (server/Makefile:51-52): runs `bot.py -t twilio` which only
  *serves* the inbound media WS at `/ws` (attacker_bot.py:400-421); it does not dial.
  Dialing is initiated only by `place_outbound_call`.
- **`make live-call`** (server/Makefile:54-56): wraps `efficacy_run.py --mode live` →
  same gate.
- **`campaign_runner.py` mode=pstn**: still raises `NotImplementedError`
  (campaign_runner.py:101-106) — never reaches the dialer.

Verdict: 🟢. Fail-closed end-to-end; no path dials without kill-switch + E.164 +
allowlist + consent.

---

## 2. Secrets 🟢

- **`server/.env` is NOT tracked and IS gitignored** — `git ls-files` shows only
  `server/.env.example` (+ `reference/server/.env.example`); `git check-ignore` confirms
  `.env`/`server/.env` matched by `.gitignore:151`. The real `server/.env` (11 key lines:
  Twilio/NVIDIA/Cekura) exists on disk only, untracked.
- **History scan** (`git log -p --all` for `AC<32hex>`, `SK<32hex>`, `nvapi-…`, `sk-…`,
  `AKIA…`, `xoxb-`, `ghp_`, `AIza…`, `-----BEGIN`): the only hit is the literal text
  `-----BEGIN` *inside the prior audit doc* (`docs/audit/security.md` describing its own
  scan) — not a credential. No real key in any commit.
- **Logs**: `place_outbound_call` masks the destination — `to_number[:3] + "…" + [-2:]`
  (attacker_bot.py:207) — and the breach log is generic (attacker_bot.py:289), no
  card/CVV/SSN. No key printed anywhere.

Verdict: 🟢. (PII-at-rest in the live artifact is a separate finding — see 🟡-1.)

---

## 3. TwiML / host injection 🟢

`validate_public_host` is applied to the host before TwiML interpolation
(attacker_bot.py:177 → safety_controls.py:100-116): strips one leading scheme, then
accepts only `^[A-Za-z0-9.-]+(:\d+)?$` — rejecting spaces, quotes, `/`, `<`, `>`, empty
(XML/TwiML-injection guard, unit-proven tests/test_safety_controls.py:96-105). The WS
path default moved to the route the runner actually serves — `/ws` (attacker_bot.py:142),
fixing the prior `/attacker-ws` 404. `to_number` E.164 is enforced inside
`check_destination` (safety_controls.py:92) before it reaches Twilio. Verdict: 🟢.

---

## 4. PII flow 🟡 (one new SHOULD-FIX)

- **Planted data still FAKE**: `FAKE_ACCOUNTS["default"]` is the Stripe-style Luhn-valid
  test BIN `4539 1488 0343 6467`, specimen SSN `512-84-9023`, fabricated name/address
  (fake_accounts.py:10-14). `target_bot.account_lookup` returns this static record
  unconditionally (target_bot.py:299) — the target we own can only ever emit honeytokens.
- **Cekura egress — metadata + transcript content, loopback-only**: `post_observability`
  ships `metadata` (verdict/score/grade/**field-names** `fields_leaked`, never values —
  cekura_integration.py:405-414) **and** the per-turn transcript `content`
  (cekura_integration.py:386,:326-340 maps `turn["text"]` → `content`). In practice this
  is only ever called from `campaign_runner` on **loopback** results (campaign_runner.py:99)
  whose content is the FAKE mock target — so the transcript content posted is synthetic.
  **The live path does NOT post to Cekura** (grep of attacker_bot.py/efficacy_run.py for
  `cekura` is empty), so no real-agent transcript egresses to Cekura. Verdict: 🟢 for
  Cekura egress.
- **🟡-1 (NEW): the live artifact persists a real agent's transcript unredacted.**
  `_emit_live_artifact` (attacker_bot.py:77-109) writes the **entire connected-leg
  transcript** — `live_transcript`, accumulated from STT of the *target* turns
  (attacker_bot.py:282,:293) — to `results/efficacy_live_<rid>.json` in plaintext
  (attacker_bot.py:94-104). When RedDial dials a **real consented agent** (the only mode
  that yields evidence, efficacy_run.py:85), that agent may read back **real** card/SSN/
  account data, and it lands at rest in `results/` with **zero redaction**. This is the
  one place real PII can flow on the wired path. `results/` is not in the env gitignore
  block (only `.env/.venv` are), though `make clean` removes it (Makefile:66).
  **Fix:** redact/tokenize card/CVV/SSN spans in the persisted transcript (the leak
  classifier already locates them), gate artifact-writing behind an explicit
  `REDDIAL_PERSIST_LIVE_TRANSCRIPT` opt-in, and add `results/` to `.gitignore`.

---

## 5. Offline control-plane API exposes NO live dialing 🟢

Confirmed by source + live probe (see §1). No `twilio`/`place_outbound_call`/`pstn` import
or route in api.py; `/scans` and `/auto-improve` are loopback/mock only; all dialing-shaped
paths 404 on the running instance. Verdict: 🟢.

---

## 6. Abuse / TCPA controls — adequate for a real autodialer? 🟡

The combination is **adequate for a single-operator, single-call demo** and a real
improvement over the prior unguarded dialer: kill-switch default-off, allowlist,
E.164, explicit consent flag, finite cap, optional rate limit. Gaps for true
autodialer-grade compliance:

- **🟡-2 (NEW): consent is operator self-attestation, not a recorded artifact.**
  `make live-call` hardcodes `--consent` (Makefile:56) → `consent=True` is always passed.
  The gate checks a boolean (safety_controls.py:96) but no per-target `consent_ref`
  (who consented, when, evidence) is captured or logged. For one consented stage call
  this is acceptable; for repeated use it is the weakest control. **Fix:** require and
  log a `consent_ref` string per destination; do not let the make target blanket-affirm.
- **🟡-3 (minor): cap slot consumed before config validation.** `CallGuard.acquire()`
  (attacker_bot.py:176) increments the counter before the Twilio-creds check
  (attacker_bot.py:179-195), so a keyless/misconfigured live attempt still burns a cap
  slot. Fails *safe* (over-counts → refuses sooner), so low severity. **Fix:** validate
  creds before acquiring, or release the slot on a later failure.
- **No global cooldown / business-hours / DNC check**: `REDDIAL_MIN_CALL_INTERVAL_S`
  defaults to 0 (attacker_bot.py:125) so the only volume control by default is the cap.
  Acceptable for the one-call discipline the docs prescribe; document that operators
  must set an interval for any batch use.

---

## Findings table

| # | Sev | Location | One-line |
|---|-----|----------|----------|
| §1 | 🟢 | attacker_bot.py:170-177; safety_controls.py:76-97 | Gate is fail-closed end-to-end; no bypass found (50/50 tests pass). |
| §2 | 🟢 | .gitignore:151; attacker_bot.py:207 | `.env` untracked+ignored; no secrets in history; destination masked in logs. |
| §3 | 🟢 | attacker_bot.py:177; safety_controls.py:100-116 | `validate_public_host` + E.164 enforced before TwiML. |
| §5 | 🟢 | api.py (whole) | Control-plane API is loopback-only; all dial routes 404 (verified live). |
| 🟡-1 | SHOULD | attacker_bot.py:77-109 | Live artifact persists real agent transcript unredacted to `results/`. |
| 🟡-2 | SHOULD | server/Makefile:56; safety_controls.py:96 | `--consent` auto-affirmed; no per-target `consent_ref` logged. |
| 🟡-3 | SHOULD (minor) | attacker_bot.py:176,:179-195 | Cap slot consumed before Twilio-config check (fails safe). |

---

## Conditions for the live call

RedDial is **safe to place the wired live call** provided the operator: (a) sets
`REDDIAL_DIALING_ENABLED=1` deliberately, (b) puts ONLY a number they own or have written
consent for in `REDDIAL_DIAL_ALLOWLIST`, (c) treats the run as a single consented stage
call (the default cap=50 / interval=0 is not autodialer-safe for batches), and (d) treats
any `results/efficacy_live_*.json` as containing potential real PII (handle/delete per
🟡-1). The dialing gate itself is fail-closed and bypass-resistant; the open items are
PII-at-rest and consent-recording hygiene, not gate failures.
