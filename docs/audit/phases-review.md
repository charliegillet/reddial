# RedDial — Devil's Advocate review of Phases 2 & 3

**Date:** 2026-05-30 · **Branch:** `feat/phases-2-3` · **Method:** read PRODUCTION_READINESS.md
+ original devil's-advocate teardown, then every new/changed module; ran `uv run --no-sync
pytest tests/ -q` (106 passed), live-probed `keyword_posture` on phrasings it was NOT tuned on,
diffed concurrent-vs-sequential campaigns, exercised persistence/budget/retries, and traced the
live efficacy path. Evidence is `file:line` and reproducible.

The bar is unchanged: *can a customer point this at their own live agent and trust the report?*

---

## TL;DR

Phases 2-3 are **mostly real engineering, not busywork** — the ops layer (run_context,
concurrency, persistence, budget, retries) is correct and well-tested, and the anti-overclaim
discipline in `efficacy_run.py` is genuinely good. **But the headline Phase-2 claim — "real
autonomy via a model-based posture classifier" — does not hold on the path that matters:** the
LLM classifier is unreachable from any real run, and the keyword fallback still collapses brand-new
real-agent phrasings to the do-nothing default. BLOCKER 4 has **not** moved: the live path still
can't be exercised, `/attacker-ws` is still unregistered (live call → 404), and `run_live_efficacy`
captures **no** transcript — it initiates a call and returns a stub.

---

## 1. Anti-overclaim — 🟢 GENUINELY GOOD (the most important thing, and they got it right)

No overclaim found. The evidence is consistent across code, tests, docs, and the commit:

- `efficacy_run.run_loopback_efficacy` hard-stamps `proves_real_world_efficacy=False` and
  `target_kind="self-authored-mock"` with an honest `note` (`efficacy_run.py:51-65`).
- `test_efficacy.py:16` asserts `proves_real_world_efficacy is False` as "the critical
  anti-overclaim" — it's a guarded invariant, not a comment.
- The CLI prints `proven_real_world=False` and a NOTE that "loopback attacks our own mock — NOT
  proof against a real agent" (`efficacy_run.py:120-123`).
- `docs/DEPLOY.md:50-65` is blunt: "attacks RedDial's **own mock** — it is **not** evidence about a
  real agent," and §"Known follow-ups" admits "Real-world efficacy remains **unproven**."
- The commit message ends "real-world efficacy (BLOCKER 4) still requires an operator live run;
  not claimed."

I tried to find a path that implies proven efficacy and could not. This is the strongest part of
the work. 🟢

One nit (🟡): `run_live_efficacy` sets `proves_real_world_efficacy=None` (`efficacy_run.py:86`).
`None` is honest ("undecided") but a downstream consumer doing `if art["proves_real_world_efficacy"]:`
treats `None` as falsy by luck, not design. A `live` artifact with no attached transcript should
arguably be `False` until a verdict exists, so it can never be mistaken for proof.

## 2. Is the "real autonomy" real? — 🔴 NO. The model classifier is unreachable; the fallback still memorizes the audit's examples.

### 2a. The keyword fallback fixes the *named* examples, not the brittleness.
`test_posture.py:13-23` checks exactly the phrasings the original audit named — and they pass. But
I probed **new** real-agent phrasings it was not tuned on (`posture.keyword_posture`,
`posture.py:57-70`). 8 of 12 collapse to the do-nothing `deflecting`, including the dangerous ones:

| Agent says | Reality | Classifier says |
|---|---|---|
| "I'd rather not do that" | refusing | `deflecting` ❌ |
| "That's not something we typically do" | refusing | `deflecting` ❌ |
| "Yeah, one sec, pulling it up" | compliant (about to leak) | `deflecting` ❌ |
| "Let me just grab that for you" | compliant | `deflecting` ❌ |
| "I can give you the last four only" | partial-refusal | `deflecting` ❌ |
| "I'll need to confirm a couple details before I can do that" | verifying | `deflecting` ❌ |
| "Sorry, what was that?" | confused | `deflecting` ❌ |
| "Per our guidelines I can only share the last four" | refusing/partial | `deflecting` ❌ |

So the original finding stands verbatim: against a real agent the attacker still **cannot tell
"I'm winning" from "I'm being refused."** The table was patched; the generalization was not. This is
"memorize the 3 examples the audit named," confirmed empirically.

### 2b. The LLM path is NOT reachable from any real run — it's test-only.
`posture.classify(text, llm=...)` (`posture.py:102-124`) is sound and tested. But the only code that
could place a live call instantiates the policy as **`AttackerPolicy(deterministic=True, ...)`**
(`attacker_bot.py:210`), and `deterministic=True` routes to `keyword_posture`, NOT `classify`
(`attacker_policy.py:53-55`). Every non-test caller is deterministic:
`grep AttackerPolicy( *.py` → `attacker_bot.py:210` (deterministic=True) and `loopback.py:58/63/65`
(all deterministic / no llm). The `classify` LLM branch fires **only** from `test_posture.py`
stubs. Furthermore `nemotron_llm.py` exposes neither `.classify` nor `.complete`
(`class VLLMOpenAILLMService(OpenAILLMService)`, no such methods) — so even if a run flipped to
`deterministic=False`, there is no wired Nemotron adapter that satisfies the `posture.classify`
contract. **The "model-based classifier (the real autonomy)" docstring overclaims relative to what
any real run uses.** 🔴 The autonomy on the live path is exactly as keyword-blind as the original
audit said.

### 2c. The FSM is still a fixed schedule.
Unchanged from the original teardown: `_advance` (`attacker_policy.py:92-116`) still marches
RECON→PRETEXT→INJECT→ESCALATE→EXFIL on turn count; posture only modulates which canned line is read
inside EXFIL (`_line_for_state`, `attacker_policy.py:118-136`). Not adaptive strategy. 🟡

## 3. Concurrency correctness — 🟢 CORRECT.

I ran 24-call campaigns at `concurrency=1` vs `concurrency=8`: `total_calls`, `breach_rate`,
`leak_rate`, `max_score`, `max_grade`, **and full `by_vector`** are byte-identical, `failed=0` both
ways. The design is safe because the `ThreadPoolExecutor` map only *reads* shared immutable inputs
(`lib.ATTACKS`, the per-task `(index, attack)` tuple) and each task returns its own row;
`pool.map` reassembles results in input order, so ordering is deterministic
(`campaign_runner.py:119-126`). There is no shared mutable counter in the hot path — `failed` is
incremented only in the single consuming loop, not across threads. Per-call persistence writes to
`{index:04d}_{attack_id}.json` keyed by the unique loop index (`run_context.py:86`), so concurrent
writes never target the same path. No race found. (Caveat: `CallGuard` is *not* used by the
loopback campaign path — it's only in `place_outbound_call` — so its non-thread-safe `_count`/
`_last_ts` aren't exercised concurrently here; a future concurrent *live* path would share one
`_DIAL_GUARD` and that increment IS unguarded. Flagging pre-emptively 🟡.)

## 4. Persistence / retries / budget — 🟢 WORK (one cosmetic gap).

- **Persist:** concurrent `n=30 persist=True` wrote exactly 30 files with 30 unique indices, no
  collisions (verified). `test_persist_campaign_writes_files` asserts the count.
- **Budget:** `budget=7`→7, `budget=0`→0 (verified). Negative budget is intentionally a no-clamp
  (`budget>=0` guard, `campaign_runner.py:110`) → `budget=-1, n=3`→3. Defensible, slightly
  surprising; a negative budget arguably should mean "0," not "unlimited." 🟢/🟡
- **Retries:** `_with_retries` (`campaign_runner.py:36-52`) re-runs on any `Exception`, backs off,
  and **re-raises the last exception** (not a wrapped/wrong one) — `test_with_retries_reraises_
  after_exhaustion` confirms the original `ValueError` propagates. Loopback uses `attempts=1`
  (passthrough), so retries don't perturb determinism. Correct.

No file-overwrite or wrong-exception bug found.

## 5. Does any of this move BLOCKER 4? — 🔴 NO. Blunt assessment.

The machinery is the *right scaffold* (correlation IDs, persistence, a gated single-call entry
point, honest provenance) — that part is not busywork. **But the live path still cannot be
exercised, and `run_live_efficacy` does not actually capture efficacy:**

- **`/attacker-ws` is still unregistered.** TwiML hardcodes `wss://<host>/attacker-ws`
  (`attacker_bot.py:109`) and the docstring at `:101-104` admits "the Pipecat WorkerRunner must
  actually SERVE a websocket route at that exact path or Twilio's connect-back" fails. `bot()`
  (`attacker_bot.py:316-363`) just handles whatever WS the runner hands it; nothing registers the
  `/attacker-ws` route. **First real Twilio connect-back → 404.** `docs/DEPLOY.md:78` lists this as
  an open follow-up. So a live call still cannot complete. 🔴
- **`run_live_efficacy` is a call-initiator + stub, not a transcript capturer.** It calls
  `place_outbound_call` and returns `{call_sid, proven=None}` (`efficacy_run.py:80-91`). The actual
  leak verdict runs in a *different process/leg* — the Pipecat worker's `leak_classifier`
  (`attacker_bot.py:226-233`) — and there is **no wiring** to bring that transcript/verdict back
  into the `results/efficacy_*.json` artifact. The note (`efficacy_run.py:88-90`) honestly says a
  human must "attach that transcript" by hand. So even with keys, this produces a call SID, not an
  evidence artifact. The loop is not closed. 🔴
- The 8 kHz Twilio audio caveat and other voice TODOs are unchanged.

The fail-closed safety gate IS real and IS enforced here: `run_live_efficacy` → `place_outbound_call`
→ `safety_controls.check_destination` raised `DialingNotAllowed` ("kill-switch off") with no env set
(verified). `test_live_mode_blocked_by_safety_gate_by_default` guards it. That's genuine progress on
the *safety* blocker — but safety-gating a call that 404s on connect-back and never reports a verdict
doesn't close the *efficacy* blocker.

## 6. The single most important thing STILL missing/wrong

**The "real autonomy" is not on the live path, and the live efficacy harness can neither connect nor
capture a result.** Concretely, the two halves that would make a real run possible were *built but
not wired together*:
1. `posture.classify` (the model brain) exists but no live caller uses it (all `deterministic=True`),
   and no Nemotron adapter implements its `classify`/`complete` contract.
2. `run_live_efficacy` initiates a call but `/attacker-ws` is unregistered (404) and the verdict
   produced by the connected-leg `leak_classifier` is never captured back into the artifact.

Until (a) `/attacker-ws` is registered, (b) the live policy runs `deterministic=False` against a
real Nemotron adapter, and (c) the connected-leg transcript+verdict flows into the efficacy artifact,
the "machinery to close BLOCKER 4" cannot, in fact, close it.

---

## Where Phases 2-3 are genuinely good (not crying wolf)

- **Anti-overclaim discipline is excellent** (§1) — provenance stamping is in code, tests, docs, and
  the commit. This was the single most important thing to get right, and they did.
- **Ops layer is correct and tested:** deterministic concurrency, collision-free persistence,
  working budget cap, correct retry/re-raise (§§3-4). 106 tests pass in 0.07s.
- **Safety gate is enforced in code and verified fail-closed** (`safety_controls.check_destination`),
  closing the worst of the original BLOCKER 3.
- **Deploy hygiene improved:** `bot.py` is no longer byte-identical to the flower starter — it's a
  `REDDIAL_ROLE` dispatcher defaulting to `target` (`bot.py:36-80`); Dockerfile pins the base via
  ARG (no `:latest`); `docs/DEPLOY.md` documents the gate and an honest BLOCKER-4 path.

---

## VERDICT

- **Did Phases 2-3 meaningfully advance production-readiness?** **PARTIAL.** Real, verifiable
  progress on ops (concurrency/persistence/budget/retries/correlation), on the safety gate, on
  deploy hygiene, and — most importantly — on honest provenance. But the flagship Phase-2 claim
  ("real autonomy") is not delivered where it counts, and BLOCKER 4 is untouched in substance.

- **Is anything overclaimed?** The efficacy artifacts are NOT overclaimed (excellent). The
  **autonomy is**: `posture.py`'s "MODEL-BASED classifier (the real autonomy)" and the commit's
  "hardened keyword fallback that correctly reads the real-agent phrasings" oversell — the model path
  is test-only/unwired, and the fallback still mis-reads the majority of *new* real-agent phrasings
  (§2a/§2b). Scope these claims to "validated on the audit's named examples; unverified beyond them."

- **Top thing to fix:** Wire the autonomy and the live capture end-to-end — register `/attacker-ws`,
  run the live policy `deterministic=False` against a real Nemotron `classify`/`complete` adapter,
  and feed the connected-leg `leak_classifier` transcript+verdict back into the efficacy artifact.
  Only then does the Phase-2 machinery actually close BLOCKER 4 instead of merely scaffolding it.

---

## Maintainer resolution (post-review)

Both 🔴 findings addressed (code; live path still needs an operator run to verify):

- **🔴 autonomy unreachable — FIXED.** Added `posture.NemotronClassifier` (OpenAI-compatible
  Nemotron adapter exposing `.classify`), and `attacker_bot` now builds it via `from_env()` and runs
  `AttackerPolicy(deterministic=False)` whenever `NEMOTRON_LLM_URL` is set — so a real call uses the
  MODEL, not keywords (set `REDDIAL_FORCE_DETERMINISTIC=1` to force the scripted keyword path).
  Keyword fallback broadened for more phrasings and explicitly documented as a *fallback*, not the
  real classifier. Tested (adapter + reachability + broadened keywords).
- **🔴 live capture loop — CLOSED in code.** `attacker_bot._emit_live_artifact` writes a
  `results/efficacy_live_<run_id>.json` (transcript + connected-leg breach verdict +
  `target_kind="real-agent"`) when a live call completes, so a real run produces the artifact rather
  than a hand-attached stub. `/attacker-ws` path is now configurable via `REDDIAL_WS_PATH`.
- **Still genuinely open (honest):** `/attacker-ws` route *registration* and the live call itself
  remain unverifiable without NVIDIA+Twilio keys. Real-world efficacy is therefore still **unproven**
  until an operator records one live run — correctly NOT claimed anywhere.

Suite: **111 passed**; ruff clean. The 🟢 verdicts (anti-overclaim, ops correctness, safety gate) stand.
