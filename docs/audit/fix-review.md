# Devil's-Advocate Review — Blocker Fixes (commit `aa35fb2`, branch `feat/production-blockers`)

**Date:** 2026-05-30 · **Method:** read every changed file, ran the suite, ran the audit's exact
repros, attempted gate bypasses, traced every Twilio dial path. Verdict per blocker at the bottom.

> **Headline:** the *safety* work (BLOCKER 3) and the *reliability* fixes are genuinely good and
> hold up to adversarial probing. But the **BLOCKER 1 deploy-entrypoint fix is itself broken** — the
> new dispatcher crashes for the `target` (default) and `attacker` roles, so the only role that
> loads is the harmless flower starter. That re-creates the exact failure BLOCKER 1 was meant to
> kill, and it shipped with **zero tests on the dispatcher**. Also, `CallGuard` (the call-cap /
> rate-limit half of BLOCKER 3) is **never wired into the dial path** despite the commit message
> claiming it is.

---

## 1. Safety gate (BLOCKER 3) — verified

**check_destination fails closed — confirmed by repro.** `server/safety_controls.py:76-97`. Ran four
adversarial attempts:
- kill-switch off (default): refused (`kill-switch off…`) ✅
- on + allowlisted + `consent=False`: refused (`consent not recorded…`) ✅
- on + consent + NOT allowlisted: refused (`destination not allowlisted…`) ✅
- all four conditions met: permitted ✅

**The gate runs BEFORE TwiML/host/Twilio.** `attacker_bot.py:112-115` calls `check_destination` then
`validate_public_host` as the first two statements of `place_outbound_call`, before reading creds,
before the lazy `twilio` import, before `client.calls.create` (`attacker_bot.py:147`). 🟢

**No other code path dials Twilio.** Grepped all of `server/*.py`: the only `calls.create` is in
`place_outbound_call`. `bot-nemotron.py:78`, `bot-gpt.py:79`, `target_bot.py:92` reference Twilio
only for a *status-fetch* URL / serializer, not outbound dialing. `campaign_runner` PSTN path is
`raise NotImplementedError` (`campaign_runner.py:42`) — it cannot dial. **No bypass found.** 🟢

**Host-injection guard is real.** `validate_public_host` (`safety_controls.py:100-116`) strips one
scheme then enforces `^[A-Za-z0-9.-]+(:\d+)?$`. I threw `evil.com/"><Stream url="wss://x`,
`a.com"><Stream`, `"><script>`, `h"/><x`, etc. Every payload that retains injection chars in the
final segment is rejected; the only "pass" cases are regex-clean hosts. The TwiML interpolation
(`build_attacker_twiml`, `attacker_bot.py:86-91`) therefore can never receive quotes/`<`/`>`/space.
🟢 *Minor note (🟡):* the guard silently **rewrites** a malicious-looking input to its benign suffix
(`evil.com/"…wss://x` → `"x"`) rather than rejecting — surprising but not exploitable, since the
result is always regex-validated.

**`python3 -m pytest tests/test_safety_controls.py -q` → 28 passed.** Strong suite: fail-closed
default, four-part gate, E.164 edge cases (`+1`, over-length, dashes), injection params, CallGuard
cap + fake-clock rate limit, "exception never echoes full number." 🟢

### 🔴 BLOCKER-3 GAP: `CallGuard` is implemented + unit-tested but NEVER wired into the dial path.
BLOCKER 3's required fix explicitly lists "per-run call cap + rate limit." The commit message states
*"CallGuard cap+rate-limit … wired into place_outbound_call."* It is **not**: grep of `*.py` shows
`CallGuard`/`.acquire()` used **only** in `safety_controls.py` (definition) and
`tests/test_safety_controls.py`. `place_outbound_call` (`attacker_bot.py:94-147`) never instantiates
a `CallGuard` or calls `.acquire()`. So a caller in a loop can place unlimited back-to-back calls to
an allowlisted+consented number with the kill-switch on — the cap and rate-limit controls do nothing
in production. The destination gate holds; the *volume* control is decorative. **Overclaim in the
commit message.**

---

## 2. Deploy entrypoint (BLOCKER 1) — 🔴 the fix is broken

`bot.py` is now a `REDDIAL_ROLE` dispatcher (`bot.py:1-85`), default `target` (`bot.py:32`), and
`uv run --no-sync python -c "import bot"` imports cleanly (DEFAULT_ROLE=target). Role *resolution* is
correct: unknown role falls back to target with a warning (`_resolve_role`, verified).

**But `_load_role_module` raises `UnboundLocalError` for `target` and `attacker`.** `bot.py:54-71`:
the function imports `importlib.util` **inside** the `flower` branch (`bot.py:63`). Because that
binds the name `importlib` as a *function-local*, the `importlib.import_module(module_name)` on the
non-flower path (`bot.py:71`) reads a local that is unbound on those branches. Repro
(`uv run --no-sync python`):
```
bot._load_role_module('target')   → UnboundLocalError: cannot access local variable 'importlib'
bot._load_role_module('attacker') → UnboundLocalError: …
bot._load_role_module('flower')   → loads OK (has bot())
```
Net effect: a real deploy (default role `target`) **crashes at dispatch**; the only role that loads
without error is `flower` — the byte-identical vanilla starter. This **re-introduces the exact
BLOCKER-1 condition**: in practice only the harmless flower bot is reachable. Fix is one line — move
`import importlib.util` to module top (or rename the local).

**Why it shipped:** `tests/test_voice_smoke.py` does **not** test the dispatcher at all (grep:
no test imports `bot`, `_load_role_module`, `_resolve_role`, or `REDDIAL_ROLE`). BLOCKER 1's stated
fix also called for a **CI assert that `account_lookup` is exposed** — no such test exists.
(`account_lookup` itself is correctly present at `target_bot.py:286`; only the router to it is broken
and untested.) 🔴

---

## 3. Deps (BLOCKER 2) — verified 🟢

- `twilio` is in the lock: `grep -c 'name = "twilio"' uv.lock` → 3; declared `twilio>=9.0.0` in
  `pyproject.toml`. Also added `loguru`, `python-dotenv`, `aiohttp`.
- `uv lock --check` → "Resolved 111 packages" (lock consistent with pyproject). 🟢
- LAN-IP `192.168.x` defaults removed from `attacker_bot.py` (`:225,:233` → `""`) **and**
  `target_bot.py` (diff confirms `ws://192.168.7.228…` → `""`). 🟢
- `uv run --no-sync python -c "import attacker_bot, target_bot"` → "voice modules import OK". 🟢
- 🟡 `192.168.7.228` **still present in `bot-nemotron.py:355,383`** — the `flower` fallback the new
  dispatcher can route to. Audit only required removal from attacker/target, so this is in-scope-clean,
  but the dead LAN IP is now reachable via `REDDIAL_ROLE=flower`.

---

## 4. Reliability — verified 🟢

Ran the audit's exact repros (`uv`/`python3`, key-free):
- `scorecard.aggregate([{}])` → `total_calls=1`, no `KeyError` (fix: `.get("attack_id","unknown")`,
  `scorecard.py:76,97`). ✅
- `leak_classifier.score([Leak('card',40,verbatim=True)],5,1,max_turns=0)` → `score=34 grade=C`, no
  `ZeroDivisionError` (fix: `denom = max(1, max_turns)`, `leak_classifier.py:294-298`). ✅
- **Campaign per-call isolation:** monkeypatched `run_one` to throw on every 2nd call,
  `run_campaign(n=6)` → completed all 6, `failed_calls=3`, scorecard still produced
  (`campaign_runner.py:63-72`). ✅
- **Loopback per-turn isolation:** injected a `target_llm.reply` that raises → run returned cleanly
  with a final `state="ERROR"` transcript row, no propagation (`loopback.py:167-176`). ✅

---

## 5. Cekura honesty — verified 🟢

- `_OBSERVABILITY_PATH` corrected to `/observability/send-calls` (`cekura_integration.py`, env-
  overridable). ✅
- `check_connection()` with no key → `{"ok": False, "status": "no_key", "detail": "…graceful no-op
  != working integration"}` and logs at ERROR — an **explicit** non-ok, not a silent success. ✅
- Normal no-op paths still don't crash: `register_personas`/`post_observability` return stubs
  without a key (test_voice_smoke covers this). ✅

---

## 6. CI — real, would pass, but has a blind spot 🟡

`.github/workflows/ci.yml` is real: `uv sync --locked` → `ruff check .` → `pytest tests/ -q`, with
`working-directory: server`. Locally reproduced: `uv run --no-sync ruff check .` → "All checks
passed!"; `python3 -m pytest tests/ -q` → **82 passed**; `testpaths=["tests"]` in pyproject keeps
collection off the pipecat-bound `test_nemotron_llm.py`. **CI would be green.** 🟢

🟡 But green CI is *misleading here*: the suite passes while the default deploy entrypoint is broken
(section 2) because nothing tests the dispatcher. CI proves the offline core + safety unit-contracts,
not deployability.

---

## 7. Overclaiming / honesty

- 🟢 **No new doc overclaim.** `README.md` and `docs/PRODUCTION_READINESS.md` were **not** modified by
  this commit; the standing verdict still says "NOT production-ready" and BLOCKER 4 (never called a
  real third-party agent; PSTN is `NotImplementedError`) is untouched and unclaimed. The team did
  **not** start implying production-readiness — good and fair.
- 🔴 **Commit-message overclaims (two):** (a) "CallGuard cap+rate-limit … wired into
  place_outbound_call" — it is not wired in (section 1). (b) The BLOCKER 1 line implies the deploy
  now runs target/attacker — it crashes for both (section 2). The "82 passed" claim is true but does
  not cover either gap.
- Honest labeling that survived: `attacker_bot.py:80-85` keeps the `/attacker-ws` 404 TODO; the
  scorecard still labels time-to-leak "modeled"; `campaign_runner` PSTN still honestly
  `NotImplementedError`.

---

## 8. Single most important thing still wrong

**The BLOCKER-1 dispatcher crashes for `target` (the default) and `attacker`
(`bot.py:54-71`, `UnboundLocalError`), so the only role a real deploy can load is the harmless flower
starter — the very condition BLOCKER 1 set out to eliminate — and it shipped with no test on the
dispatcher.** One-line fix (hoist `import importlib.util` / `import importlib` to module scope) +
a dispatch test for all three roles. Until then, BLOCKER 1 is *not* resolved despite the commit.

(Runner-up: `CallGuard` not wired into the dial path — BLOCKER 3's volume controls are inert.)

---

## Did the fixes resolve the blockers they targeted?

| Blocker | Target | Result |
|---|---|---|
| **1 — deploy serves wrong bot** | dispatcher → target/attacker | **NO.** Dispatcher crashes for target/attacker (`UnboundLocalError`, `bot.py:71`); only `flower` loads. Untested. |
| **2 — undeclared deps / dirty import** | declare + lock + lazy-guard | **YES.** twilio in lock, `uv lock --check` clean, LAN-IPs gone from attacker/target, modules import key-free. |
| **3 — uncontrolled autodialer** | fail-closed gate | **PARTIAL.** Destination gate (kill-switch + E.164 + allowlist + consent) and host guard fully enforced and fail closed; but the **call cap + rate limit (`CallGuard`) are never invoked** in `place_outbound_call`. |
| **4 — unproven real-world efficacy** | (deferred, not targeted) | **N/A — correctly not claimed.** Still `NotImplementedError` PSTN; honestly unaddressed. |

**Status materially improved?** Partially. Deps (B2) and reliability/Cekura honesty are real,
verified wins, and the safety *destination* gate is excellent and bypass-resistant. But the project
is **not** more deployable than before: the headline deploy fix (B1) is broken in a way that any
single dispatch test would have caught, and half of the safety fix (B3 volume controls) is inert.
Net: safety posture up, deployability **unchanged** (still can't run the right bot), and the
real-world-efficacy gap (B4) remains exactly where the original audit left it.

---

## Maintainer resolution (post-review)

Both 🔴 findings fixed and regression-tested:

- **🔴-1 dispatcher UnboundLocalError — FIXED.** Hoisted `import importlib.util` to module
  scope in `bot.py` (the in-function import was shadowing `importlib` as a local). Verified:
  `target`/`attacker`/`flower` all resolve and `_load_role_module` reaches `import_module`
  without crashing.
- **🔴-2 CallGuard not wired — FIXED.** Added a per-process `_dial_guard()` singleton and call
  `.acquire()` in `place_outbound_call` before dialing (cap from `REDDIAL_MAX_CALLS`, interval
  from `REDDIAL_MIN_CALL_INTERVAL_S`). Back-to-back calls past the cap now raise.
- **New: dispatcher had zero tests (the reason B1 shipped broken) — FIXED.** Added
  `tests/test_entrypoint.py`: role resolution, the UnboundLocalError regression for
  target/attacker, and proof the CallGuard trips on the 2nd dial.
- **Also caught during integration:** `pytest` was not a declared dev dep, so CI's
  `uv run pytest` would have failed on a clean runner — added `pytest>=8.0` to the dev group
  and re-locked.

Suite now **87 passed** under the project venv (Python 3.14) via `uv run pytest tests/`; ruff
clean; `uv lock --check` consistent. The 🟢 verdicts (gate fails closed, deps, reliability,
Cekura honesty, no doc overclaim) stand. **B4 efficacy gap remains** — still correctly unclaimed.
