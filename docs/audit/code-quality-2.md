# RedDial — Code Quality & Correctness Audit (round 2)

Dimension: **CODE QUALITY & CORRECTNESS** (production-readiness pass)
Branch: `audit/production-wiring` · Working dir: `/Users/nihalnihalani/Desktop/Github/reddial`
Scope: the auto-improve work added SINCE round 1 — `server/auto_improve.py`,
`server/gepa_mitigation.py` (`suggest_clause`), `server/mock_llm.py` (graded `GuardClause`
gating), the new `api.py` endpoints, and the four new/changed frontend views.

Builds on `docs/audit/code-quality.md` and `docs/audit/hardening-review.md` — their findings
(deploy entrypoint serves wrong bot, voice imports, uncapped `concurrency` now FIXED, attack-library
credibility) are NOT re-litigated here.

Legend: 🔴 BLOCKER (breaks in prod / on first real use) · 🟡 SHOULD-FIX (a sharp reviewer draws
blood / maintainer trap) · 🟢 OK-or-verified-good.

## Gate results (ran exactly as requested)

- `cd server && uv run --no-sync pytest tests/ -q` → **151 passed, 1 warning in 0.32s**
  (warning is a third-party `StarletteDeprecationWarning`, not our code).
- `cd frontend && npx tsc --noEmit` → **exit 0** (clean).
- `cd frontend && npm run build` → **built in 728ms**, `dist/assets/index-*.js 321.86 kB`. Clean.

All three green. Note: tsc passing does NOT clear the frontend — see 🔴-1, which tsc cannot catch
because the payload is typed by an (incorrect) cast at the `r.json()` boundary.

---

## 🔴 BLOCKERS

### 🔴-1 The "Final Hardened Guardrail" card renders `[object Object]` — API/TS contract mismatch
The headline payload of the whole auto-improve feature is broken in the UI.
`auto_improve.run_auto_improve` returns `final_guardrail` as a **list of objects**
`[{"id","text"}, …]` (`server/auto_improve.py:297-301`), and I confirmed the LIVE API does too
(`POST /auto-improve` → `final_guardrail: [{"id":"reject_authority_pretext","text":"Treat fraud-team …"}, …]`).
But the TS type declares `final_guardrail: string[]` (`frontend/src/api.ts:119`) and the view does
`result!.final_guardrail.join("\n")` (`frontend/src/views/AutoImproveView.tsx:268`). `[{…},{…}].join("\n")`
yields literally `"[object Object]\n[object Object]"` (verified in node). tsc is green only because
`get<T>` casts `r.json()` to the wrong type — the bug is invisible to the type checker.
Fix: change the TS type to `final_guardrail: { id: string; text: string }[]` and render
`result.final_guardrail.map(c => c.text).join("\n")` (or list `id — text`). One-line type + one-line render.

---

## 🟡 SHOULD-FIX

### 🟡-1 The "Rounds" control is inert — `rounds` can only RAISE the cap, never lower it
`max_rounds = max(rounds, int(max_rounds))` (`server/auto_improve.py:193`) means a requested
`rounds=2` produces `max_rounds = max(2, 8) = 8`, so the loop runs to convergence/8, not 2. Verified:
`run_auto_improve(rounds=2)` → 4-round trajectory, `rounds_to_converge=3`, yet the returned `"rounds": 2`
field (`:307`) misreports it. The UI slider (`AutoImproveView.tsx:88-95`, min 1 / max 10) therefore does
nothing observable below 8 — the same "inert control" class the team already hit in commit `968429c`.
Either the operator's `rounds` is a no-op or the echoed `rounds` lies about the run.
Fix: make `rounds` the actual cap — `max_rounds = min(int(max_rounds), max(1, int(rounds)))` (or drop the
UI control and label it "auto / runs to convergence"). Update the returned `rounds` to reflect reality.

### 🟡-2 `seed` is accepted, echoed, and documented as "Deterministic seed" but never used
`run_auto_improve(seed=0)` stores `"seed": int(seed)` (`server/auto_improve.py:307`) and the API exposes
it (`api.py:251`), but there is no RNG anywhere in the path (`grep random auto_improve|loopback|mock_llm`
→ none). The docstring's "Deterministic seed" is vacuously true. A caller passing different seeds gets
byte-identical output — harmless, but a reviewer reasonably expects `seed` to do something or not exist.
Fix: drop `seed` from the public surface, or document it as "reserved; the loop is unconditionally
deterministic, seed has no effect."

### 🟡-3 Degenerate `held_out_vector` silently trains the held-out and reports a false "did not generalise"
`_probe_breach(held_id, …)` (`auto_improve.py:288-289`) with an unknown `held_out_vector` leaves
`held_cat = held_out_vector` (a non-existent category), so `suite_ids` excludes nothing and the loop
trains the *entire* suite — including `emotional_urgency`. Verified:
`run_auto_improve(held_out_vector='nonexistent_vector')` → `breach_after=False`, which would render in the
UI as "the held-out did not breach" — the OPPOSITE of the honesty story, with no warning. The default
(`emotional_urgency`) is correct and the API never exposes this param, so severity is low; but it is a
silent foot-gun for any future caller.
Fix: if `held_attack is None`, `logger.warning(...)` and either refuse or fall back to the documented
default rather than silently dissolving the held-out guarantee.

### 🟡-4 `mock_llm.MockTargetLLM._benign` is dead code
`server/mock_llm.py:485-489` is never called (`grep _benign` → only the def). Minor clutter on a
security-boundary class where every line should earn its place.
Fix: delete it.

---

## 🟢 OK / verified-good

- 🟢 **Determinism holds end-to-end.** `test_two_runs_are_byte_identical` passes and I re-verified two
  live runs match modulo `run_id`. `_fixed_clock()` (`auto_improve.py:48-57`) + no RNG = reproducible.
- 🟢 **Monotonicity assert is correct and real.** `breach_rate > prev_breach + 1e-9` (`auto_improve.py:236`)
  hard-raises `AssertionError` in mock mode, downgrades to a `logger.warning` only when `real_used`
  (`:241-244`). The float epsilon is right. `test_breach_rate_non_increasing_across_rounds` exercises it.
- 🟢 **Termination is sound — no infinite loop.** Three exits: `breach_rate==0 and leak_rate==0`
  (`:270`), `round_idx >= max_rounds` (`:273`), `suggest_clause is None` (`:279`), all setting a distinct
  `converged_reason`. `while round_idx <= max_rounds` with `round_idx += 1` only on the clause-found
  branch — bounded.
- 🟢 **`suggest_clause` edge cases handled.** `None`/`{}`/all-blocked/malformed-entry by_vector all return
  `None` cleanly (verified). The `max(...)` + `_neg_id` tie-break is deterministic; `_clause_impacts`
  guards with `set(...)`. `test_suggest_clause_returns_none_when_nothing_covers` covers it.
- 🟢 **`calls_per_attack` is honest.** `n_per_round=5` → `total_calls` 55 vs 11 at 1 (11 trained attacks ×
  reps). The control actually changes the sample volume (`auto_improve.py:146-156`).
- 🟢 **`RealTargetLLM` never breaks the loop.** Unconfigured → mock reply (`:102-103`); any call error →
  `logger.warning` + mock fallback (`:118-120`). History role mapping (`attacker/user → user`) matches the
  loopback transcript shape (`loopback.py:169-170`) and mock's `_rebuild_pressure`. Untested (no live
  endpoint here) but statically sound and key-free.
- 🟢 **API caps + error paths verified live.** Over-cap `rounds=99` → 422, `concurrency=999` → 422 (the
  round-1 uncapped-`concurrency` blocker is fixed: `MAX_CONCURRENCY=16`, `le=` + defensive `min()` at
  `api.py:237,356`). Unknown `run_id` → 404; `/readyz` reports `auto_improve:true`. Representative
  transcript capture is best-effort (`api.py:370-377`) and cannot fail the scan.
- 🟢 **In-process registry + disk fallback + thread-safety are correct.** All mutations of
  `_RUNS/_TRANSCRIPTS/_HISTORY/_METRICS/_AUTO_IMPROVE_LATEST` are under `_LOCK`; reads snapshot under the
  lock then release before I/O (`api.py:379-392, 466-473, 492-499`). History bound `del _HISTORY[:-HISTORY_LIMIT]`
  is a correct no-op under the limit and trims to the last 50 over it (verified). Disk fallbacks
  (`_read_json_disk`, `_read_transcript_disk`) swallow only `OSError`/`JSONDecodeError` and type-check the
  result. The `_warned_no_real` module global is a benign log-once flag (worst case: a duplicate warning
  under a race — not a correctness issue).
- 🟢 **Frontend defensive data access is consistent.** `pct()` guards `null`/`NaN` (`AutoImproveView.tsx:7-10`);
  `rec.summary?.breach_rate ?? 0`, `rec.vectors_newly_blocked ?? []`, `curve?.rounds ?? []`,
  `Math.min(rounds.length, rates.length)` with an `n < 2` degenerate guard (`ImprovementCurve.tsx:16-30`).
  `AnalyticsView` tolerates array-or-`{runs|scans}` shapes and `Promise.allSettled`. `ConversationView`
  feature-detects `api.transcript` and falls back to evidence-derived turns. No `console.*`, no TODOs in
  any of the four views.
- 🟢 **The always-visible/opacity rule is honored.** `ImprovementCurve` draws polyline + circles at full
  opacity; framer-motion animates only `pathLength` as a draw-on flourish (`:103-115`) with an explicit
  comment — if the tween freezes, the chart still shows. No visibility gated on opacity anywhere in the
  new views.
- 🟢 **Type hints / docstrings / no magic-number debt.** `from __future__ import annotations`, modern
  `X | None`; `_SECONDS_PER_TURN=9.0`, `MAX_*` caps, `HISTORY_LIMIT` are all named constants. Docstrings
  match behavior (the one exception is `seed`, 🟡-2). No bare `except`; the two broad `except Exception`
  sites carry `# noqa: BLE001` + a `logger.warning` (`auto_improve.py:118`, the API best-effort capture).

---

## Verdict

**Is the CODE production-quality? PARTIAL.**

The Python engine is genuinely solid: deterministic, monotone-by-assert, bounded, well-typed, thoroughly
docstringed, with real edge-case test coverage (151 passing) and correct lock discipline + disk fallback
in the API. The round-1 `concurrency` blocker is fixed. But the flagship UI of this feature is broken —
the "Final Hardened Guardrail" panel prints `[object Object]` because the API returns objects while the
TS type and render assume strings, and tsc can't see it. Combined with the inert "Rounds" control, the
two operator-facing pieces of the new feature don't behave as presented.

### Top 3 fixes
1. **🔴-1 — Fix the `final_guardrail` contract.** Type it `{id,text}[]` in `api.ts:119` and render
   `.map(c => c.text).join("\n")` in `AutoImproveView.tsx:268`. Without this the headline card shows
   `[object Object]` to anyone driving the demo.
2. **🟡-1 — Make `rounds` actually cap the loop** (`max_rounds = min(max_rounds, max(1, rounds))`) and
   return the true round count, so the UI control is not inert / the echoed `rounds` is not a lie.
3. **🟡-2/🟡-3 — Tidy the honesty surface:** drop or document the unused `seed`, and warn (don't silently
   train the held-out) on an unknown `held_out_vector` so the "did not generalise" proof can't be inverted.
