# RedDial — Devil's Advocate: PRODUCTION-READINESS

Role: adversarial reviewer on a production-readiness audit. The bar here is **NOT**
"does the demo survive a hackathon judge" (the prior `docs/DEVILS_ADVOCATE_REVIEW.md`
answered that — yes, the loopback demo survives). The bar is: **can a paying customer
point this at their own live voice agent over a real phone line and trust the
vulnerability report it produces?** Against that bar, RedDial is a polished
demo/prototype, not a product. Evidence below, file:line.

Method: read README/PLAN/REFERENCES/the prior review, read every module in `server/`,
and ran live probes against the keyword posture classifier, the FSM, the mock target,
and the (now-fixed) classifier false-positive surface.

---

## TL;DR for the optimists

The tested core is real, deterministic, and honest about being fake-data-only — the
prior review verified that and I confirm it. But the tested core is the *least
valuable* part. **Roughly half the codebase (~1,664 LOC of voice/Twilio/Cekura/Nemotron
glue across `attacker_bot.py`, `target_bot.py`, `cekura_integration.py`, `nemotron_llm.py`,
`nvidia_stt.py`) has ZERO runtime test coverage** — `grep -rln "twilio|cekura|attacker_bot|
target_bot|nemotron|pipecat" tests/` returns NOTHING. The entire value proposition
(place a real call, attack a real third-party agent, produce a real scorecard, register
on Cekura) lives in that untested half. The 45 passing tests all exercise a text loop
between two pieces of code the project wrote to fit each other.

---

## 1. "It works" ≠ "production-ready": the tested core proves almost nothing about real targets

### 1a. The target was written to be beaten by this exact attacker
`mock_llm.py` is a keyword automaton, not a model. The full-PAN read-back fires on a
hard-coded condition: `if wants_full_card and self._authority and self._injection`
(`mock_llm.py:160`). All three booleans are set by **substring matches against fixed cue
lists** the attacker is guaranteed to emit (`_AUTHORITY_CUES`/`_INJECTION_CUES`/
`_FULL_CARD_CUES`, `mock_llm.py:70-90`). This is a lock built to fit a specific key. The
prior review's "🟢-2 not theater" finding is correct *only* in the narrow sense that a
naive cold ask is refused — but "refuses one phrasing, leaks on three magic words" tells
you nothing about how a real GPT-4o/Gemini customer-service agent behaves.

Proof the mock leaks ONLY on its keywords — a polite, plausible request that a *real*
sloppy agent might honor gets stonewalled because it lacks the cue words:
```
m.reply("Could you please read me the number on the account?", [...])
-> "Sure, I can help with the account. Can I ask who I'm speaking with...?"  (no leak)
```
So the system is simultaneously (a) trivially beatable by the in-house attacker and
(b) unable to model a real agent's behavior. Neither property generalizes to a paying
customer's bot.

### 1b. The "autonomy" is a fixed-schedule script, not adaptive social engineering
`attacker_policy._advance` (`attacker_policy.py:113-137`) marches
`RECON→PRETEXT→INJECT→ESCALATE→EXFIL` on a **fixed turn schedule**. Posture barely gates
anything — I drove it with four hard refusals in a row and it advanced through every
phase regardless:
```
states after 4 consecutive REFUSALS:
[PRETEXT, INJECT, ESCALATE, EXFIL, EXFIL]   # never re-tries recon, never backs off
```
Posture only nudges *which canned line* it reads inside EXFIL (`_line_for_state`,
`attacker_policy.py:139-157`). That is a playlist, not a strategy. A real agent that
stalls, asks an unexpected clarifying question, or transfers to a human will walk this
FSM straight off the end of its script.

### 1c. The posture classifier is dangerously brittle on real phrasing
`AttackerPolicy._keyword_posture` (`attacker_policy.py:68-81`) misclassifies the most
ordinary agent responses. Live probe results:

| Agent says | Reality | Classifier says |
|---|---|---|
| "Absolutely, I can read that back for you now." | **compliant** (about to leak!) | `deflecting` ❌ |
| "We do not provide card numbers over the phone." | **refusing** | `deflecting` ❌ |
| "For data-protection reasons I must decline." | **refusing** | `deflecting` ❌ |
| "May I take your name and order number?" | **verifying** | `deflecting` ❌ |
| "Let me pull up the account real quick." | **compliant** | `deflecting` ❌ |

Five of the most common real-agent turns all collapse to `deflecting` — the do-nothing
default. Against a real target the attacker is effectively flying blind: it cannot tell
"I'm winning" from "I'm being refused." On the live path the README claims Nemotron does
this classification, but **there is no test, no eval, and no fixture proving Nemotron
classifies better than these keywords** — it's an untested swap.

**Verdict on premise 1:** the tested loop proves the *plumbing* works (FSM advances,
classifier fires, scorecard renders) — it proves *nothing* about behavior against a real
third-party voice agent. The autonomy is a deterministic script; the "brain" on the live
path is unverified.

---

## 2. The product is essentially unbuilt where it counts

Everything a customer pays for is in the key-gated, **runtime-unverified** layer:

- `attacker_bot.place_outbound_call` (the actual dialer) — never executed in any test.
- `target_bot.py` / the Pipecat audio pipeline — never executed.
- `cekura_integration.py` — never hits a real Cekura endpoint in any test.
- STT garble, TTS, μ-law, turn-taking, barge-in — entirely theoretical.

Quantification: ~1,717 LOC of tested loopback/scoring core vs **~1,664 LOC of untested
voice/integration code**. About **half the codebase has no runtime verification at all**,
and it's the half that defines the product. The README's own legend is honest about this
(🔌 = "not runtime-tested without NIM/Twilio") — but "honestly labeled as unbuilt" is
still unbuilt.

Concrete unfinished/landmine items in that layer:
- **PSTN mode is a `NotImplementedError`** (`campaign_runner.py:42-47`). The "place real
  calls at scale" story has no code path. Only loopback runs.
- **The `/attacker-ws` route is referenced but never registered** (`attacker_bot.py:77-91`,
  flagged TODO). First real Twilio call connects back to a 404.
- **Twilio 8 kHz input is set to the config the project's own REFERENCES.md flags as
  broken** (Smart Turn v3 silently breaks at `audio_in_sample_rate=8000`, Pipecat #3844).
  Marked, not fixed.
- **Cekura endpoint paths are likely wrong.** `cekura_integration.py:24-25` posts to
  `/test_framework/v1/scenarios/run` and `/test_framework/v1/observability`. REFERENCES.md
  (lines 38-39, 78) says `scenarios/run` is NOT in Cekura's public endpoint list and the
  real observability path is `observability/send-calls`. So the "registers on Cekura" claim
  is wired to URLs the project's own research says don't exist — and the graceful-no-op
  (§5) guarantees this failure is **invisible**.
- **The Docker entrypoint is still the unmodified starter.** `Dockerfile:23` is
  `COPY ./*.py ./` over a base image whose entrypoint runs `bot.py` — which is a byte-for-byte
  copy of the starter flower-shop (`bot.py` and `bot-nemotron.py` are identical, 22,410
  bytes each). The deployable artifact runs the starter, not RedDial's attacker.

**Verdict on premise 2:** the "production system" is a set of well-commented stubs guarded
by `if not key: return _stub(...)`. It has never placed a call, never attacked a non-self
target, and never successfully talked to Cekura. As a *product* it is unproven end to end.

---

## 3. The scorecard numbers are marketing, not evidence

`scorecard.json` reports `breach_rate 0.42`, `max_score 39`, grade C, "median
time-to-leak 18.0s" over `total_calls: 36`. Every one of those numbers is the result of
**this attacker attacking this project's own deliberately-weak mock** — `campaign_runner`
runs `run_one(...mode="loopback")` 36 times against `MockTargetLLM`
(`campaign_runner.py:39-41, 58-60`). It is a closed system grading its own homework.

Why the specific numbers are not evidence of anything external:
- **The 42% breach rate is an artifact of attack/cue alignment.** Per-vector results are
  binary by construction: 6 vectors breach 100% of the time, 6 breach 0% — because 6 attack
  templates contain the magic cue words and 6 don't (`scorecard.json` by_vector). It
  measures string overlap between two in-house files, nothing about agent security.
- **"Median time-to-leak 18.0s" is fabricated.** There is no audio. It's `turns × 9s`
  (`campaign_runner.py:28`, `loopback.py:194-195`). To the credit of the maintainers it's
  *labeled* "modeled · not live audio" — but a scorecard headline number a CISO reads as
  latency is a modeled constant, not a measurement.
- **n=36, sequential, single fixed target.** Not a sample of anything. There is no real
  third-party agent, no variance, no confidence interval, no second target type.

A *real* scorecard would require: attacking real (consented) third-party agents, multiple
model families, real STT/TTS in the loop (so detection survives garble), measured wall-clock
time-to-leak, and a held-out set of attacks the target wasn't co-designed against. None of
that exists.

---

## 4. Legal / abuse: an autonomous PII-extracting outbound dialer with NO enforced controls

This is the most serious production gap. **The safety story is entirely prose and UI; the
code enforces nothing.**

`place_outbound_call(to_number, ...)` (`attacker_bot.py:94-136`) will dial **any number
passed to it**. There is:
- **No allowlist / no consent gate / no rate limit / no kill-switch in code.** `grep -rniE
  "allowlist|consent|rate.?limit|whitelist|kill.?switch" server/*.py` finds only the word
  "consent" *in a docstring comment* (`attacker_bot.py:22, 102`) and "authorized" inside
  *attack templates* and the HTML banner. Zero enforcement.
- The only "control" is a docstring saying "only ever dial a number under our control"
  and a `⚠ ALL DATA IS FAKE` string in the scorecard HTML (`scorecard.py:269`).

What this means if shipped as-is:
- It is, literally and by its own description, **an autonomous tool that places phone calls
  and social-engineers PII out of the answering agent.** The persona prompt instructs it to
  "Never break character, never mention that this is a test" (`attacker_bot.py:53-54`). Point
  the `to_number` at a real human call center and it is a deception/pretexting robocaller.
- **TCPA exposure is real and unbounded** — an autonomous outbound dialer with no consent
  ledger, no DNC check, no rate limiting is the textbook profile of a TCPA violation. The
  README cites the $925M ViSalus verdict as a *selling point*; that same statute is the
  liability the tool itself creates.
- **Pretexting for financial/PII data is independently regulated** (GLBA Safeguards/
  pretexting provisions; FTC Act §5; state anti-pretexting and wiretap/two-party-consent
  recording laws). "We only attack what we own" is a *policy*, not a *control* — and
  policies that aren't enforced in code get bypassed the first time someone fat-fingers a
  customer's production number into `to_number`.
- **Reputational/dual-use:** the honeytoken methodology is legitimate *with* authorization
  binding. Without an enforced authorization handshake (signed scope, target ownership
  proof, allowlist), this is an attack tool with a compliance README taped to the front.

For production this is not a "should-fix" — **a consent/authorization gate enforced in
`place_outbound_call` is a hard precondition to shipping at all.**

---

## 5. Operational maturity: prototype-grade, and the graceful-degradation HIDES the gaps

- **No CI.** No `.github/` anywhere in the repo. The "45 passed" suite runs only when a
  human remembers to, on a laptop. There is no gate preventing a regression from shipping.
- **Laptop-run, hardcoded dev IPs.** `attacker_bot.py:212,219` and `target_bot.py:400,409`
  default to `ws://192.168.7.228:8081` and `http://192.168.7.228:8000/v1` — someone's
  hackathon LAN box baked in as the fallback endpoint. That is not a deployable default.
- **Sequential "campaign."** `campaign_runner.run_campaign` is a plain `for i in range(n)`
  loop (`campaign_runner.py:58`) — no concurrency, no retries, no queue, no persistence of
  per-call transcripts/audio. The PLAN's "200-call fleet on AWS / 1000+ concurrent" story
  has no implementation; 200 real calls at 1-3 min sequential = 5-10 hours on one thread.
- **Graceful-degradation-as-no-op is actively dangerous for a security product.**
  `cekura_integration._post` returns a `_stub` on *missing key, missing dep, DNS failure,
  timeout, 402, or ANY non-2xx* (`cekura_integration.py:40-83`). So if the Cekura endpoint
  is wrong (§2, and REFERENCES.md says it is), the integration **silently reports success-
  shaped stubs and logs a warning nobody reads.** The same pattern means an operator can
  believe "RedDial + Cekura is working" when in fact no call to Cekura has ever succeeded.
  For a tool whose entire output is a trust/assurance artifact, silently no-opping the
  verification path is the worst possible failure mode — it manufactures false confidence.

---

## 6. The single most embarrassing question

**"Show me one vulnerability report RedDial produced by calling an AI agent that your team
did not write — and prove the phone call actually happened."**

It cannot. Every breach in the repo is this attacker beating a mock the same team built to
be beaten, over a text loop with a *modeled* (fabricated) call duration. There is no
recording, no real target, no third-party scorecard, not one successful Cekura post. A
CISO asks "what's your false-positive and false-negative rate against real agents with real
STT?" — and the honest answer is "unknown; we've only ever tested exact-string matching
against our own bot's clean text output." An investor asks "what stops this from being a
robocaller?" — and the answer is "a comment in a docstring."

---

## Where the project is genuinely fine (not crying wolf)

- **Fake-PII hygiene is clean.** Stripe test BIN, specimen SSN, reserved 555 numbers,
  `.env` gitignored, no live keys in the repo. Verified by the prior review and consistent
  with what I read.
- **The prior review's 🔴-1 false-positive bug is genuinely FIXED.** I re-ran all four
  repros (`order total $4539.14...`, `4539148803436467890`, etc.) — all now return
  `is_breach == False`. Span-aligned matching works.
- **Determinism is real.** No RNG; the loopback is reproducible. Good for a demo.
- **GEPA is framed honestly** as a suggested, non-guaranteed diff (`gepa_mitigation.py`).
- **The code is honestly *labeled*** (🔌 markers, "modeled not live audio", TODO comments
  citing the prior review). The team is not lying about what's unbuilt — they just haven't
  built it.

These are real positives. They are also all about the demo, not the product.

---

## VERDICT

**RedDial is not production-ready — it is a well-engineered, honestly-labeled demo whose
entire value proposition lives in an untested layer.** The thing that is tested (a
deterministic text loop where a hand-built attacker beats a hand-built vulnerable mock with
matching magic words) is the part that proves the least; the thing that would make it a
product (autonomous real calls to real third-party agents, real-audio leak detection, real
Cekura integration, a real multi-target scorecard) has never run, is wired to at least one
wrong API endpoint, ships a known-broken audio config, has no concurrency, no CI, and —
most seriously — **no enforced consent/allowlist/rate-limit on an autonomous outbound dialer
designed to social-engineer PII**, which makes shipping it as-is a legal and reputational
hazard, not just an incomplete feature.

**Distance from production:** demo/early-prototype. Realistically **2-4 months** of
focused work: (1) build + verify the live voice path against a real target end to end with
real STT/TTS and prove detection survives garble; (2) replace the keyword posture/mock with
real-model behavior and an actual eval harness measuring FP/FN against held-out agents;
(3) implement and test the Cekura integration against real endpoints; (4) build a hardened
authorization/consent/allowlist/rate-limit/DNC control plane in the dialer with audit
logging; (5) concurrency + persistence for campaigns; (6) CI. None of these are
nice-to-haves for a security product that places phone calls.

**Single highest-leverage thing that would change my mind:** one reproducible,
recorded end-to-end run where RedDial places a *real* call (or a faithful real-audio
loopback through actual STT/TTS) to an agent the team did **not** author, gets a leak, and
the classifier catches it through real transcription garble — gated behind an enforced
consent/allowlist check. That single artifact would convert "the plumbing compiles" into
"the product exists." Until it exists, every scorecard number is the system grading its own
homework.
