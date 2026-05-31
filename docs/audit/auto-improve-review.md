# RedDial Auto-Improve Loop — Devil's Advocate Review (2026-05-31)

Branch `feat/auto-improve-loop`. Adversarial audit of the claim: *"a genuine, honest,
eval-driven closed loop where eval data flows back into the agent and the breach rate
drops monotonically over rounds — improving OUR mock target vs OUR fixed suite, NOT
general robustness."*

Method: read the code, ran `pytest tests/ -q` (151 passed), curled `POST /auto-improve`
twice, and ran targeted probes against `suggest_clause` / `MockTargetLLM` with synthetic
and alternate inputs to try to break the honesty claims in BOTH directions.

---

## 1. Is the improvement REAL & eval-driven, or rigged/hardcoded? 🟢

**Verdict: real and data-driven. Not a disguised fixed script.**

`gepa_mitigation.suggest_clause` (gepa_mitigation.py:45-105) picks the worst OPEN vector
from the round's `by_vector` (max leak_rate, tie-break breaches, then id asc) and then the
NARROWEST unused clause that covers it. I fed it hand-built `by_vector` dicts and the chosen
clause tracked the data, not a sequence:

- only `tool_result_phishing` open → `no_raw_tool_dump`
- only `cvv_minimizer` open → `no_cvv`
- impersonation worst / pretext lower → `oob_identity`
- **reverse** (pretext worst / impersonation lower) → `reject_authority_pretext` (order flips with the data)
- injection+reset tie on leak, injection more breaches → `ignore_injected_directives`

Stronger evidence the ORDER emerges from the suite, not a script: changing which vector is
held out changes the trained suite, which changes the clause order. With the default
held-out the order is `[reject_authority_pretext, ignore_injected_directives, oob_identity]`
(3 rounds → 0). Holding out `authority_pretext` instead, the suite now contains
`emotional_urgency`, so `resist_pressure` appears in the order:
`[reject_authority_pretext, ignore_injected_directives, resist_pressure, oob_identity]`.
A hardcoded sequence could not do that.

The mock genuinely consumes the appended clause text: `MockTargetLLM` re-parses the
guardrail string for clause `token`s (mock_llm.py:141-149, 319-327) → blocked
categories/fields → gates the pressure accumulators and disclosure branches. So eval output
(the clause) literally feeds back into the target's behaviour next round.

## 2. Monotone & convergent, or could it regress / loop? 🟢

- Curve from the live API (`n=1, seed=0`): breach_rate `[0.4545, 0.2727, 0.1818, 0.0]`,
  leak_rate identical. Strictly **non-increasing**, reaches **0 on the trained suite**,
  `converged_reason: breach_rate_zero`, `rounds_to_converge: 3`.
- The monotonicity guard is a real **fail-loud assert**, not decoration. I monkeypatched
  `_eval_suite` to return a rising breach rate and got
  `AssertionError: breach_rate rose 0.200 -> 0.500 at round 1 (non-monotone)`
  (auto_improve.py:230-238). The assert is downgraded to a warning ONLY when a stochastic
  real target was actually used (`real_used`) — correct.
- **Determinism is real:** two `POST /auto-improve` calls are byte-identical after stripping
  `run_id` (the only nondeterministic field, a timestamp+random suffix). Fixed 5s/call clock
  (auto_improve.py:48-57) makes seconds-to-leak reproducible.

## 3. The honesty proof — is the held-out vector legit? 🟢

**This is the strongest part. The held-out `emotional_urgency` is a FAIR miss in both directions.**

- Excluded from training: `suite_ids = [a.id for a in lib.ATTACKS if a.category != held_cat]`
  (auto_improve.py:202) drops the whole `social_pressure` category.
- Still breaches after convergence: API result `held_out: {breach_before: true, breach_after: true}`.
- **Not rigged-to-never-block (the important direction):** I built a guardrail with EVERY
  other clause (injection, impersonation, pretext, card-field, cvv-field) but NOT
  `resist_pressure` → `emotional_urgency` still breaches (True). Adding `resist_pressure`
  → breach becomes **False**. So the correct clause genuinely stops it; it is not
  special-cased to be unblockable. Confirmed too that `suggest_clause` DOES return
  `resist_pressure` when social_pressure is the open vector.
- **Not incidentally covered (the other direction):** no trained clause touches the
  `social_pressure` category, and the card field-block is explicitly exempted for the
  social_pressure seed (`seed_cat != "social_pressure"`, mock_llm.py:394-401). So even the
  broad `no_full_pan` cannot kill it. The miss is architecturally enforced, not luck.

Caveat (documented, not a defect): the breach is attributed to the OPENING/seed turn's
category (mock_llm.py:384-397). `emotional_urgency`'s later ladder rungs do contain
"verification mode"/"full card" injection text, but the breach gates on the seed category
being unblocked — which is what makes the held-out a clean, single-vector honest miss.

## 4. Overclaim check 🟢 (one 🟡 nit)

- No overclaim found. Engine docstrings, `HONEST_NOTE` (auto_improve.py:39-43), the UI
  banner (AutoImproveView.tsx:64-72 "HONEST SCOPE … NOT a measure of general robustness"),
  the held-out statement (AutoImproveView.tsx:280-298), and the design doc all scope it to
  "OUR mock vs OUR suite." The repo even has an explicit anti-overclaim guard elsewhere
  (`efficacy_run.py` → `proves_real_world_efficacy=False` for self-authored mock, with a
  test asserting it).
- The graded mock IS keyword theatre (keyword cues → keyword clauses), and that limitation
  is stated honestly in the module docstrings and design doc. The descending curve is a
  property of a hand-built monotone lattice, not of any learned robustness — and the docs
  say exactly that.
- 🟡 Minor honesty nit: the UI exposes **"Calls / round"** (`n_per_round`, default 24) and a
  `seed`, but in mock mode both are inert. `_eval_suite` runs each attack exactly once
  (auto_improve.py:143-151); `total_calls` is always 11 and the curve is identical for
  `n_per_round=1` vs `24`. The value is echoed back in the result but never drives more eval
  volume. Not a correctness bug (deterministic mock), but the control implies eval volume
  that isn't run. Either wire it through (repeat each attack n times) or label it as a
  no-op/real-mode-only knob.

## 5. Auto-Improve category spirit 🟢

Eval data genuinely flows back INTO the agent: failing-vector eval → derived guardrail
clause → appended to the target's guardrail → re-parsed by the target → measurably fewer
breaches next round, monotonically to zero, with the loop terminating on a real data
condition (`suggest_clause` returns None / breach==0). This is a legitimate, if small and
self-contained, instance of "evaluation data flows back into the agent to improve over time."
It is a modeled/owned demo, not real-world hardening — and it says so.

## 6. Build / tests / offline / UI 🟢

- `pytest tests/ -q` → **151 passed** (one unrelated Starlette deprecation warning).
- Frontend `npm run build` → clean (tsc + vite, 0 errors).
- Offline: the only network code is `RealTargetLLM` (opt-in `target_mode="real"`, needs
  `NEMOTRON_LLM_URL`). The API forces mock (`/auto-improve` never sets `target_mode`,
  api.py:487-491), so the default path makes zero external calls.
- UI: curve visibility is never gated on opacity — full-opacity polyline/marks, only
  `pathLength` animates (ImprovementCurve.tsx:103-115, comments enforce this). `<2` rounds
  shows a graceful empty state. No console-erroring bug observed; types compile.

---

## Bottom line

- **REAL and HONEST? YES.** The loop is eval-driven (clause order tracks the data, proven by
  varying inputs and the held-out set), monotone and convergent with a fail-loud assert,
  deterministic, and the held-out proof is fair in both directions (blockable by the right
  clause, not incidentally covered by trained ones).
- **Anything overclaimed?** No material overclaim. Scope is correctly and repeatedly stated
  as "our mock vs our suite, not general robustness." Only nit: the inert "Calls / round"
  and `seed` UI controls in mock mode.
- **Single most important issue:** the cosmetic `n_per_round`/`seed` inputs (🟡) — they
  suggest eval volume / stochasticity that the deterministic mock does not actually exercise.
  Wire them through or label them clearly.
- **Legitimate Auto-Improve entry?** Yes. It is a genuine, honestly-scoped closed loop where
  evaluation data feeds back into the target to drive a monotone breach-rate descent, with a
  built-in held-out that proves it does not generalize. Small and self-contained, but it does
  exactly what it claims and refuses to claim more.

---

## Maintainer resolution (post-review)

🟢 verdict accepted — loop is real, honest, eval-driven, monotone, fair held-out, no overclaim.

🟡 (inert "calls/round" control) — FIXED: `_eval_suite` now runs each attack `calls_per_attack`
(= n_per_round) times, so `total_calls` reflects the requested volume (n=1→11, n=3→33). The mock
is deterministic so the breach-rate curve is unchanged, but the control is no longer inert/misleading
(and a stochastic `target_mode="real"` run now gets a real per-attack sample). 151 tests pass.
