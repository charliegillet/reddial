# RedDial — Devil's Advocate on "Get rid of the mock — make EVERYTHING live, nothing mock, production + submission ready"

**Date:** 2026-05-31 · **Branch:** `feat/go-live` · **Role:** adversarial reviewer.
**Premise under attack:** *"Delete the mock. Make everything live. Nothing should be mock. Everything
should actually work. Production + submission ready."*

**Method:** read `README.md`, `docs/PRODUCTION_READINESS.md`, the prior audits (especially
`production-devils-advocate.md`), and the core code — `mock_llm.py`, `loopback.py`, `auto_improve.py`,
`target_bot.py`, `attacker_bot.py`, `api.py`, `nemotron_llm.py`, `preflight.py`. Verified the *current*
state: determinism (`run_loopback` → BREACH/C/turn-2 three times, byte-stable), test suite
(`pytest tests/` → **144 passed, 2 skipped**), API auth (`grep Depends|api_key|Authorization` in
`api.py` → **nothing**; CORS `allow_origins=["*"]`, in-process `dict` state), and the previously-flagged
`_emit_live_artifact` proof regression (now **fixed** — `attacker_bot.py:101-102` stamps
`proves_real_world_efficacy: None`, `target_kind: "live-call (operator must verify…)"`).

**Bottom line up front:** "make everything live, nothing mock" is **partly achievable and partly a lie
waiting to be told.** Going live at the *LLM* layer (real Nemotron attacker + real Nemotron vulnerable
target) is genuinely more credible than a keyword mock and is worth doing. But "delete the mock entirely"
is a **regression for a submission**, "everything works live" is **unprovable in this environment** (no
Twilio/audio execution), and "production ready" stays **false** regardless of how live the LLM is, because
the real prod gaps (auth, multi-tenant, recorded third-party efficacy) are untouched by a go-live pass.

---

## Where going live is genuinely valuable (credit first — not crying wolf)

A real Nemotron target that *reasons* about an attacker's social-engineering, instead of
`mock_llm.MockTargetLLM` matching `_AUTHORITY_CUES`/`_INJECTION_CUES`/`_FULL_CARD_CUES` substrings
(`mock_llm.py:184-253`), is a categorically more honest demonstration. The mock's breach is engineered:
the "smooth descending curve" comes from a hand-built **monotone lattice** (`GUARD_CLAUSES`,
`mock_llm.py:70-131`) where each clause's `text` is constructed to contain its own `token`
(`active_clauses`, `mock_llm.py:141-149`) so a re-parse round-trips — the agent literally re-reads the
clause that defeats the exact category the attacker seeded (`_seed_category`, `mock_llm.py:304-310`).
A real LLM target removes that circularity: the attacker would have to actually *talk* a model into
leaking, and `leak_classifier` (regex + Luhn) would be judging real model output, not a string the mock
was written to emit. `auto_improve.RealTargetLLM` (`auto_improve.py:60-120`) already exists for exactly
this. **So: live LLM target+attacker = a real and worthwhile credibility upgrade.** Keep that framing.
The rest of this document is where "everything live, nothing mock, production ready" breaks.

---

## 1. The PSTN / audio path CANNOT run here — any "works live" phone claim is unprovable

This is the hardest constraint and it is non-negotiable in this environment.

- **No Twilio execution, no audio, no telephony connect-back.** The live call path is
  `attacker_bot.place_outbound_call` → Twilio `<Stream>` to `wss://$PUBLIC_HOST/ws` → pipecat telephony
  runner → STT (Parakeet) → Nemotron → TTS (Magpie) over 8 kHz μ-law. **None of that executes from this
  repo/CI.** It requires a publicly-reachable host, a Twilio-verified caller ID (`attacker_bot.py:181`),
  provisioned NIM/TTS endpoints (`preflight.enforce` *raises* on any missing — `preflight.py:72-80`), and
  a real phone leg.
- **0% runtime coverage on ~1,600 LOC of the value layer.** `attacker_bot.py`, `target_bot.py`,
  `nemotron_llm.py`, `nvidia_stt.py` are all key-gated and omitted from the coverage floor. The 144
  passing tests exercise the **text loop and HTTP control plane** — not a phone call. `_emit_live_artifact`
  fires only inside `AttackDriver.process_frame` (`attacker_bot.py:304`), which no test or fixture ever
  drives.
- **What is literally unprovable here:** (a) that a Twilio connect-back ever reaches `/ws` and runs
  `bot()`; (b) that the leak survives **STT garble** — a card read as "forty-five thirty-nine…" may not
  normalize back to the planted PAN; (c) that the `nemotron_llm.py` empty-content guard (the
  reasoning-only / `finish_reason="length"` → silent-turn fallback, `nemotron_llm.py:89-102`) behaves on a
  real reasoning endpoint; (d) 8 kHz / Smart-Turn / barge-in behavior with real μ-law.

**Honest statement to make:** *"The phone-call path is wired and structurally correct (`/ws` is real in
pipecat 1.3.0), but it has never carried a call in this environment. We cannot claim it 'works live'
without a recorded real call. The loopback is the proven artifact; PSTN is cosmetic until that recording
exists."* The README already says exactly this (`PSTN is cosmetic`, line 79) — **do not let a go-live pass
quietly upgrade that to "live voice works."**

## 2. A real LLM target is still OUR OWN consented agent — the breach is still self-graded

Replacing the mock with a real Nemotron vulnerable persona changes the *mechanism* (real reasoning, not
keyword matching) but **not the epistemics**:

- `target_bot.py` / `RealTargetLLM` are **agents WE prompt to be leaky.** The persona system prompt
  literally hands the model the FAKE card and a weak guardrail (`auto_improve.py:93-99`,
  `target_bot.py:347-350`: *"call account_lookup and read back what it returns"*). Beating that proves the
  attacker beats **a target we built to lose.** That is a *demo of the attack mechanism*, not evidence
  about anyone's production agent.
- So the answer to "is that everything works?" is **no — it's still self-graded**, just with a more
  realistic adversary on both sides. The grade (`breach_rate`, "median time-to-leak 18.0s" — which is a
  *modeled* `turns × 9s`, `loopback.py:201-202`, not a measurement) is RedDial-vs-RedDial.
- **What a real third-party test requires:** (1) a consented agent the team did **not** author; (2) a real
  phone call placed through the gated dialer (`safety_controls.check_destination` + `CallGuard`); (3) the
  captured transcript + leak verdict attached as an artifact; (4) ideally a false-positive/false-negative
  rate against several real agents with real transcription. None of (1)-(4) exists in the repo
  (`find efficacy_live_*.json` → nothing).

**The most embarrassing question is unchanged and still unanswerable:** *"Show one vulnerability report
RedDial produced by calling an agent your team did NOT write — and prove the call happened."* Going live
on the LLM does **not** answer it; only a recorded non-self call does.

## 3. Determinism vs live — "delete the mock entirely" is a REGRESSION for a submission

This is the crux. Argue both sides honestly:

**FOR deleting the mock (the steelman):** the mock is a self-fulfilling prophecy — every "result" is the
attacker beating a keyword automaton the team wrote, and a skeptical judge will (correctly) discount it.
A live LLM loop is more impressive and more honest about the *mechanism*. If the keys work on stage, a
live breach is a stronger story than a deterministic one.

**AGAINST deleting the mock (the stronger case for a submission):**

- **The mock IS the reproducible artifact.** Verified just now: `run_loopback()` → BREACH, grade C, turn 2,
  **byte-identical three times.** The whole submission pitch — *"one bulletproof, deterministic,
  Luhn-verified breach"* (README:79) — depends on determinism. A live stochastic LLM at `temperature` ≥ 0
  on a shared endpoint can refuse, time out, or word the card so STT/regex misses it. **A demo that works
  4 times out of 5 is worse than a deterministic one for a judged submission.**
- **The auto-improve monotone curve is a property of the mock's lattice, not of any real model.** The
  descending-to-zero breach curve (`auto_improve.run_auto_improve`) only stays monotone because
  `_eval_suite` runs the deterministic mock; with a real target the code itself **downgrades the
  monotonicity assert to a warning** (`auto_improve.py:239-247`) and the curve can be noisy or non-monotone.
  Delete the mock and the signature visual of the product becomes flaky.
- **CI dies.** 144 tests pass with **zero keys** precisely because the mock is the default target. A
  live-default test suite needs live endpoints in CI (secrets in GitHub Actions, network egress, cost,
  flakiness) — or it can't run at all. That is a strict regression in testability.
- **The held-out honesty proof depends on the mock.** `emotional_urgency` is held out and *must still
  breach* after convergence (`auto_improve.py:290-292`) — this is the project's best honesty signal
  ("the loop doesn't magically generalize"). It is only meaningful because the mock's behavior is
  controlled and reproducible.

**Verdict on premise 3:** *"Delete the mock entirely"* is a **net regression** for a submission. The
correct move is **dual-mode**: keep the deterministic mock as the default for the reproducible demo + CI +
auto-improve curve, and ADD a live LLM mode (`target_mode="real"` already exists) as the *credibility*
path. "Live by default, mock deleted" trades a guaranteed-working demo for a flaky one and breaks CI.

## 4. Reliability — a live-default product WILL break on stage; the honest fallback story

The Nemotron endpoint has **already** demonstrated the failure modes the team feared: `content=None`
once, and a TCP probe timeout. The code's own comments are the confession:

- `nemotron_llm.py:39-43` documents a **verified-live** turn finishing with `finish_reason="length"`,
  full `reasoning`, and **zero visible `content`** → silent spoken turn. The guard synthesizes a fallback
  ("Sorry, could you say that again?") — but a fallback chunk is **not a red-team attacker line**; on a
  live call that's a wasted/degraded turn.
- `RealTargetLLM.reply` catches **every** exception and silently falls back to the mock
  (`auto_improve.py:118-120`). So "live mode" can quietly degrade to *mock mode mid-run* and the operator
  may believe the live model produced the result. For an assurance product this **silent live→mock
  fallback is itself a dishonesty hazard** (see §6).
- `preflight.enforce` *raises* if any of `NVIDIA_ASR_URL` / `NEMOTRON_LLM_URL` / `GRADIUM_API_KEY` is
  unset (`preflight.py:72-80`) — good fail-fast, but it means a live-default deploy **fails on day one**
  until every endpoint is provisioned and reachable.

**Honest fallback story:** a robust product **keeps the deterministic mode as the fallback and labels
which mode produced each result.** "Everything is live, nothing is mock" is incompatible with robustness
here — the only reason the current loop *never breaks* is that the mock is the default. The honest
framing is: *"Live LLM is the credibility mode; the deterministic loopback is the reliability mode and the
on-stage default. If the endpoint is slow/empty/down, we fall back **loudly** and say so."* Silent
fallback that lets a live banner sit over a mock result is the trap.

## 5. "Production ready" — going live does NOT move the production-readiness needle

Even with a fully live LLM layer, the API verified just now is **not a product**:

- **No auth anywhere.** `grep Depends|api_key|Authorization|Bearer` in `api.py` → nothing. `POST /scans`
  and `POST /auto-improve` run with no credential. Anyone who reaches the port runs scans and the
  auto-improve loop.
- **CORS `allow_origins=["*"]`** (`api.py:75`). The comment claims this is fine because the API is
  "offline-only … no live actions" (`api.py:70-71`) — but that comment is now **false on a go-live
  branch**: `/scans` runs real campaigns and the same process hosts the live-call dispatcher. Going live
  makes the existing "no live actions" justification a lie.
- **Single-process, in-memory state.** `_RUNS` / `_TRANSCRIPTS` are module-level `dict`s under one
  `threading.Lock` (`api.py:82-90`). A restart loses all history; not multi-instance, not horizontally
  scalable. No API rate limiting (only input clamps `n ≤ 500`, `concurrency ≤ 16`).
- **The scorecard is still self-graded** (§2, §3) no matter how live the LLM is.

**Verdict on premise 5:** "make everything live" **swaps a deterministic mock for a flaky live call while
leaving every real prod gap (auth, multi-tenancy, persistence, recorded third-party efficacy) untouched.**
It does not move the needle from "single-operator laptop tool" toward "hardened SaaS." If anything, a
naive go-live makes it *less* production-ready, because the live path is the unproven, flakiest surface and
it now sits behind an unauthenticated, CORS-`*` endpoint.

## 6. The single most dishonest thing the project could claim after a "go live" pass

**"RedDial is fully live and production-ready — it really calls agents and proves real-world
vulnerabilities."**

Why it's the worst lie, and how each clause is false:
- *"really calls agents"* — no recorded call exists; the path has never executed here (§1).
- *"proves real-world vulnerabilities"* — every result grades **our own consented leaky agent** (§2);
  even live-LLM, it's self-graded.
- *"fully live"* — the silent live→mock fallback (`auto_improve.py:118-120`) means a result labeled
  "live" may have been produced by the mock (§4).
- *"production-ready"* — no auth, single-process, CORS `*` (§5).

**The specific mechanism that makes this lie easy to tell by accident:** the silent live→mock fallback +
a "LIVE" banner in the UI. A judge sees "live," the endpoint times out, the code falls back to the mock,
and the demo still shows a breach — **manufacturing false confidence is the cardinal sin for a security
product.** Avoid it by (a) labeling every result with the mode that actually produced it
(`real_used` is already tracked in `auto_improve` — surface it); (b) failing **loudly** on live error
instead of silently substituting the mock during an explicitly-live run; (c) keeping
`proves_real_world_efficacy` honest (already fixed to `None` in `_emit_live_artifact`).

---

## VERDICT — how much of "everything live, nothing mock, production + submission ready" is truthful?

**Truthfully achievable here:**
- ✅ A **live LLM mode** (real Nemotron attacker + real Nemotron leaky target over the **text** loop via
  `RealTargetLLM` / `auto_improve target_mode="real"`). This is more credible than the keyword mock and is
  worth shipping as an *option*.
- ✅ Live Cekura **posting attempt** in the flow (already wired) — but unproven round-trip; must fail loud.

**NOT achievable / would be a lie here:**
- ❌ "The live **phone** path works" — unprovable without a recorded real call (no Twilio/audio in this
  env). PSTN stays cosmetic.
- ❌ "Real-world efficacy proven" — every target is our own consented agent; self-graded regardless of
  liveness.
- ❌ "Production ready" — auth/multi-tenant/persistence gaps are untouched by a go-live pass.

**What MUST keep a deterministic mode, and why:**
1. **The submission demo** — the "one bulletproof, Luhn-verified breach" pitch *requires* the byte-stable
   mock (verified deterministic). A flaky live breach is a worse submission.
2. **CI / the 144-test suite** — runs with zero keys only because the mock is the default; live-default
   breaks CI.
3. **The auto-improve monotone curve + held-out honesty proof** — both are properties of the mock lattice;
   the code itself demotes the monotonicity guarantee to a warning under a real target.
4. **The reliability fallback** — the only reason the loop "never breaks" is the deterministic default;
   it is the honest on-stage safety net (used **loudly**, never silently).

**Honest framing for the submission (say this on stage):**
> *"The deterministic loopback is our proven, reproducible artifact — one Luhn-verified breach, every
> time, with FAKE PII against an agent we built and own. We ALSO run the exact same loop against a real
> Nemotron target+attacker to show the mechanism is real, not keyword theatre. The live **phone** path is
> wired and gated but unproven — we have not placed a recorded call to a third-party agent, so we do not
> claim real-world efficacy. The number you see grades our own consented bot; closing that is our next
> milestone, not a claim we make today."*

**Single highest-leverage action:** make it **dual-mode, not mock-deleted** — keep the deterministic mock
as default (demo/CI/curve/fallback), promote the existing live LLM mode to a first-class *labeled* option,
and make the live→mock fallback **fail loud** so a "live" label can never sit over a mock result. Then,
separately, place **one recorded gated call against a non-self agent** — that single artifact is the only
thing that converts "the plumbing compiles" into "the product has run," and no amount of deleting the mock
substitutes for it.
