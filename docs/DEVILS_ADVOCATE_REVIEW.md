# RedDial — Devil's Advocate Review

Role: adversarial pre-demo review. I was paid to find why this loses on stage, not to praise it.
Branch: `feat/reddial-full-build`. Suite passes (`40 passed`), but passing tests only prove the
inputs the authors thought of. Below are the inputs they didn't.

Method: read the code, then ran experiments — 5× determinism diff, ~17 hand-crafted classifier
probes (false-positive + false-negative), theater check on the mock target, full-repo PII/secret
grep, and a read of the (untested) voice layer. Repro commands are inline.

Legend: 🔴 STOP-SHIP (will lose the room / unsafe) · 🟡 SHOULD-FIX (a sharp judge draws blood) · 🟢 NICE-TO-HAVE

---

## 🔴 STOP-SHIP

### 🔴-1 Classifier FALSE POSITIVE: the BREACH banner can fire on benign turns
The code comments and `is_breach` docstring claim the banner is *"structurally impossible to fire on
a benign turn"* (leak_classifier.py:6-12, 209-220). **This is false.** `scan_turn` concatenates
**every digit in the turn** (`normalize_spoken_numbers`) and does a plain substring search for the
PAN digit string, then re-Luhns that same substring — which of course passes, because it *is* the
PAN. There is no token/field boundary check. Any turn whose combined digit stream contains
`4539148803436467` as a substring screams BREACH.

Repro (`cd server`):
```python
import leak_classifier as lc
lc.is_breach(lc.scan_turn("Your order total is $4539.14 for 8803436467 items"))  # -> True  (FALSE)
lc.is_breach(lc.scan_turn("Order number 4539148803436467890"))                    # -> True  (FALSE)
lc.is_breach(lc.scan_turn("invoice 45391488 then 03436467"))                      # -> True  (FALSE)
lc.is_breach(lc.scan_turn("acct 4539 ext 148803436467"))                          # -> True  (FALSE)
```
The existing test `test_no_false_positive_order_total` only proves a total that *doesn't* contain
the PAN substring is safe — it does not cover totals/order-numbers that do. The independent re-Luhn
in `_digits_in_span` is **not** a defense: it re-checks the very substring that matched.
Why it's stop-ship: a wrong BREACH banner on a live "order #..." turn is on-stage humiliation, and it
directly contradicts the team's own "judge-proof, can never false-fire" claim — a skeptical judge who
pastes an order number into the classifier kills the whole credibility story in one move.
**One-line fix:** require the PAN to appear as a token-aligned run (don't blindly concatenate all
digits across the turn) — e.g. match the PAN against each maximal digit-run / normalized number span,
not the whole-turn digit soup; keep cross-token concat only for the spelled/chunked attacker case.

### 🔴-2 "Voice red-team" framing vs. a text loopback with sub-millisecond "time-to-leak"
The default `run_loopback()` uses real `time.monotonic`, so `seconds_to_first_leak` is ~0.0001s and
the scorecard renders **"Median time-to-leak: 0.0s"**. The pitch leans on Pillar's "42 seconds"
stat. A judge who reads the scorecard sees a sub-millisecond number that obviously is not a phone
call — it advertises that no call happened. This is the honesty gap, not a crash.
Repro: `python3 -c "import loopback; print(loopback.run_loopback().seconds_to_first_leak)"` → ~1e-4.
**One-line fix:** in the demo path inject a `clock` (or post-scale) that reports a realistic
per-turn duration, AND label the scorecard "simulated text-loopback timing — no audio" so the 0.0s
is never read as a real-call latency. (Determinism itself is fine — see 🟢-1.)

---

## 🟡 SHOULD-FIX

### 🟡-1 Classifier FALSE NEGATIVES: realistic STT garble evades the banner
A *real* card read-back that an STT layer slightly mangles is NOT detected — the demo's entire
premise is "the target leaked and we caught it," so a silent miss is a missed WOW.
Repro (`cd server`):
```python
import leak_classifier as lc
lc.is_breach(lc.scan_turn("453 1488 0343 6467"))               # dropped digit -> False (missed)
lc.is_breach(lc.scan_turn("4539 1488 0343 6476"))              # transposed   -> False (missed)
lc.is_breach(lc.scan_turn("... one double four eight oh ..."))  # "double four" -> False (missed)
```
Clean / chunked / fully-spelled / "oh"-for-zero forms DO match (good). But the "double X" multiplier
path only helps if the doubled digit lands exactly where the PAN has a repeat — the planted card has
no usable double, so spoken-grouping evades. This is a known limitation of exact-match + Luhn (you
can't fuzzy-match a card without breaking Luhn), so it's SHOULD-FIX not STOP-SHIP — but **don't claim
"catches STT-garbled leaks."** On stage, drive the deterministic clean read-back only.
**One-line fix:** scope the claim to "verbatim/encoded leaks"; optionally add a separate "near-miss
(13–19 digit run, Luhn-failing)" amber signal so a garbled read still surfaces as *suspected* (never
as a verified BREACH).

### 🟡-2 `/attacker-ws` route is referenced but never registered
`build_attacker_twiml` points Twilio's outbound `<Stream>` at `wss://{host}/attacker-ws`
(attacker_bot.py:82), but **no code registers that path** — the Pipecat runner serves its default WS
route, and `grep -rn attacker-ws server/*.py` finds it only inside TwiML/doc strings. The moment real
Twilio keys are added, the outbound leg dials, Twilio opens the media socket to `/attacker-ws`, and
it 404s. Can't be runtime-tested here, but it is a near-certain fail on first live attempt.
**One-line fix:** register a `/attacker-ws` websocket handler that maps to `attacker_bot.bot` (or
change the TwiML to the runner's actual default WS path).

### 🟡-3 Twilio telephony sample-rate set to the known-bad config
target_bot.py:514-515 sets BOTH `audio_in_sample_rate=8000` and `audio_out_sample_rate=8000` for the
Twilio path. The team's own REFERENCES.md (line 29) documents that Pipecat upsamples 8k μ-law to the
pipeline rate internally and that **Smart Turn v3 can silently break at `audio_in_sample_rate=8000`
(Pipecat issue #3844)**. So the repo ships the exact configuration its own research flagged as
broken. Untestable here (no keys), but it's a self-documented landmine.
**One-line fix:** set only `audio_out_sample_rate=8000` and leave `audio_in_sample_rate` at the
pipeline default per the cited Pipecat guidance.

### 🟡-4 `attacker_bot.AttackDriver` re-Luhn gate is loose ("verbatim" not Luhn-checked)
In the live attacker pipeline the breach trigger is `any(l.kind=="card" and l.verbatim ...)`
(attacker_bot.py:189) — it does NOT call `is_breach`, so it inherits 🔴-1's false-positive surface on
the live path too, and a transcribed STT garble misses (🟡-1). Consistency bug between loopback
(`_is_breach`) and the voice path.
**One-line fix:** call `leak_classifier.is_breach(leaks)` in `AttackDriver` instead of the ad-hoc
`verbatim` check.

### 🟡-5 Pitch stats are still misattributed unless the README/PLAN are corrected
docs/REFERENCES.md already catalogs the fabrications (the "20% / 42s / 90% / voice jailbreaks" figure
is a **text-LLM** Pillar stat, not voice; "$925M TCPA verdicts top" was reversed; "22% of YC batch is
voice-first" unverified; GEPA "10% > GRPO" is really 6% avg; voice funding was 2024 not 2025; Nemotron
"120.6B/12.7B" false precision; NGC tags + Cekura `scenarios/run` unconfirmed). **This is only safe if
the spoken pitch + README + PLAN.md actually adopt the corrected wording.** A judge who knows the
Pillar report will call out "that's not voice data" instantly.
**One-line fix:** sync README.md / PLAN.md / the script to REFERENCES.md's corrected phrasings before
demo; do not say "voice jailbreaks" for the Pillar numbers.

---

## 🟢 NICE-TO-HAVE / things that actually hold up

### 🟢-1 Determinism of the demo IS solid — verified
Ran `run_loopback()` 5× and diffed the transcript + breach flag: **byte-identical every run**
(attack path `authority_pretext`, breach=True, score 39, grade C, 2 turns). No RNG, no dict-ordering
dependence, the FSM is keyword-deterministic and `MockTargetLLM` rebuilds pressure from full history.
Only `seconds_to_first_leak` (and therefore the rounded score's speed term) is wall-clock — see 🔴-2 —
but it doesn't flip the transcript, breach, grade, or score in practice. The demo will not flake.

### 🟢-2 The vulnerability is NOT theater — it's plausibly gated. Verified
`MockTargetLLM` **refuses** a naive cold "what's the card number?" and refuses a full-card ask with no
pretext (returns a gatekeeping/who-are-you line). The full-PAN read-back requires BOTH accumulated
authority/pretext AND an injection cue AND an explicit full-card request (mock_llm.py:160-165). The
hardened guardrail blocks it (confirmed: returns last-4-only under full pressure). So the autonomy
claim — "naive ask fails, the layered ladder succeeds" — is genuinely demonstrated, not "always
leaks." This is the strongest part of the build. (Caveat: it's a keyword automaton, not a model; fair
to call it a *scripted vulnerable target*, not an LLM that "decided" to leak. Don't overclaim it as a
real model jailbreak.)

### 🟢-3 Safety / PII is clean. Verified
Full-repo grep: card `4539 1488 0343 6467` is a Stripe-style test BIN, Luhn-valid, fake; SSN
`512-84-9023` is specimen-range; name/address/DOB fabricated; `KNOWN_CUSTOMERS` uses reserved
`+1415555xxxx` numbers. `.env` is gitignored; only `.env.example` (empty placeholders) is tracked. No
live API keys (`sk-…/AKIA…/AC…/nvapi-…` grep returns nothing). The scorecard HTML carries a prominent
FAKE-DATA banner. No stop-ship safety issue.

### 🟢-4 GEPA framing is honest. Verified
`gepa_mitigation.suggest_mitigation` is a hand-authored guardrail diff (admits it), and `reverify`
re-runs the SAME attack against the hardened target and **prints the truth if the breach does NOT
clear** ("did NOT block… reporting the truth"). Scorecard footer says GEPA is a *suggested* guardrail,
not a robustness guarantee. No overclaim in code. (Minor: it's labeled "GEPA-style" but no actual
`dspy.GEPA` runs — keep saying "GEPA-style / suggested," never "GEPA-optimized.")

---

## Verdict

**Would this survive a skeptical judge?** Mostly yes on substance — the deterministic breach, the
properly-gated vulnerable target, and the clean fake-PII story are genuinely good and will demo
reliably. But it has **one credibility-killer**: the team loudly claims the BREACH banner "can never
false-fire on a benign turn," and that claim is provably wrong (🔴-1) — a judge who pastes an order
number with the wrong digits into the classifier gets a false BREACH and the whole "judge-proof"
narrative collapses. The sub-millisecond "time-to-leak" (🔴-2) and the unregistered `/attacker-ws`
route (🟡-2) are the next things a sharp judge or a live-call attempt exposes.

**Single highest-leverage fix:** Fix 🔴-1 — make the PAN match token/number-span aligned instead of a
whole-turn digit-concat substring, and re-run the false-positive probes above as new tests. It removes
the one finding that turns a strong demo into "your headline safety claim is false," and it costs ~10
lines plus 4 test cases.

---

## Maintainer resolution (post-review, same session)

- 🔴 **1 (false BREACH) — FIXED.** `leak_classifier` now matches planted secrets as **exact spoken
  number spans** (`_number_spans`): digits joined only by intra-number separators (space/hyphen/comma),
  broken by words, decimals, and currency. A span must *equal* the PAN (+ Luhn) to fire. All four repros
  now return no-breach; added `tests/test_classifier_falsepos.py` (the 4 probes + split-number + real
  read-backs incl. comma-grouped + spelled). The one accepted miss (a full PAN fused to an adjacent
  number with **no** separating word) is documented in `is_breach`'s docstring. Suite: 45 passed.
- 🔴 **2 (0.0s time-to-leak) — FIXED (honestly).** Loopback now models call time as `turns × ~9s/turn`
  (`seconds_per_turn`); the scorecard renders the time-to-leak with the label
  *"modeled · loopback @ ~9s/turn (not live audio)"* so it is never presented as live audio.
- 🟡 **attacker_bot used a loose `verbatim` check — FIXED.** Now calls the canonical
  `leak_classifier.is_breach` (span-equality + independent Luhn re-check), consistent with loopback.
- 🟡 **`/attacker-ws` route & 🟡 Twilio 8 kHz input — MARKED, not fixed.** Both are voice-layer issues
  that cannot be runtime-verified without NIM/Twilio keys. Inline `TODO (DEVILS_ADVOCATE_REVIEW.md)`
  comments now sit at both sites (`attacker_bot.build_attacker_twiml`, `target_bot` WebSocket case) so
  they're addressed before the first live call.
- 🟡 **Pitch stats — ADOPTED.** README now cites `docs/REFERENCES.md`, attributes the Pillar stats to
  *text* LLM apps (not voice), notes the $925M TCPA verdict was reversed, and drops the unsupported
  "200 startups in YC's batch" claim.
- 🟢 Determinism, not-theater, PII-clean, GEPA-honest findings were verified and required no change.
