# RedDial — End-to-End Wiring / Integration Audit

Branch: `audit/production-wiring` · Date: 2026-05-31 · Role: wiring/integration auditor
Live targets exercised: API `http://127.0.0.1:8080` · dashboard `http://localhost:5173`

**Headline verdict: YES — everything is wired properly end-to-end.** Every traced flow
(offline scan, auto-improve, conversation, analytics/metrics, Cekura, voice/live path,
frontend nav, imports/contracts) connects with matching producer/consumer shapes. No dead
endpoint, no orphaned view, no broken import, no referenced-but-not-served path found.
Builds on prior audits ([ui-connect-review](ui-connect-review.md),
[base-integration-check](base-integration-check.md), [PRODUCTION_READINESS](../PRODUCTION_READINESS.md));
two prior UI-connect 🟡/🔴 items are now **fixed** (see §7).

Gates run this audit:
- `uv run --no-sync pytest tests/ -q` → **151 passed**, 1 warning (Starlette httpx deprecation, unrelated).
- `npx tsc --noEmit` → exit 0, clean.
- `npm run build` → built in 741ms, 321.86 kB JS / 20.07 kB CSS, no errors.
- All modules import under `uv`: `bot, target_bot, attacker_bot, api, cekura_integration, preflight, auto_improve, campaign_runner, loopback, leak_classifier, scorecard, mock_llm, gepa_mitigation` → "all import OK".
- Live curls + the vite `/api` proxy round-trip all 200.

---

## 1. Offline scan flow — 🟢 SOLID

`DashboardView`/`Sidebar` Launch → `api.runScan` (`api.ts:141`) → `POST /api/scans` →
(`api.py:348` `create_scan`) → `campaign_runner.run_campaign(mode="loopback")` →
`loopback.run_loopback` → `leak_classifier` → `scorecard.aggregate` → JSON → React render.

Live evidence — `POST /scans {n:12,concurrency:4}` returned:
`run_id`, `summary` with keys `total_calls, leak_rate, breach_rate, median_time_to_leak_s,
max_score, max_grade, distinct_fields_leaked, by_vector, evidence_samples, failed_calls,
run_id, time_note`. Sample: `breach_rate 0.5`, `max_grade "C"`, `median 18.0s`,
`evidence_samples[0].evidence_span` = the card read-back.

Producer→consumer shape match (verified field-by-field):
- `ScorecardSummary.tsx:12-78` reads `max_grade/max_score/breach_rate/leak_rate/distinct_fields_leaked/median_time_to_leak_s/total_calls` — all present.
- `VectorTable.tsx:10-65` reads `by_vector.{leak_rate,leaks,runs,breaches,fields}` — present.
- `EvidenceLog.tsx:10-44` reads `evidence_samples.{attack_id,fields,turns_to_first_leak,evidence_span}` — present.
- `api.ts` `Summary` interface (`api.ts:28-41`) matches the live payload exactly.
- `App.tsx:84` consumes `{summary}` from `runScan`; `App.tsx:65` seeds from `/scorecard/latest` on mount.

`concurrency` is double-capped (`api.py:356` clamps to `MAX_CONCURRENCY=16`; pydantic `le=16` at `api.py:237`). `n` clamped to `MAX_SCAN_N=500`. Latest persisted to `scorecard.json` (`api.py:390`) → `/scorecard/latest` survives restart via `_seed_from_disk` (`api.py:533`).

## 2. Auto-improve flow — 🟢 SOLID

`AutoImproveView` (`AutoImproveView.tsx`) → `api.runAutoImprove` (`api.ts:153`) →
`POST /api/auto-improve` (`api.py:476`) → `auto_improve.run_auto_improve(rounds,calls_per_attack,seed)`
→ `suggest_clause` + graded `mock_llm` → locked result dict → `ImprovementCurve` + trajectory table.

Live evidence — `POST /auto-improve {rounds:5,n_per_round:1,seed:0}` returned all locked keys:
`run_id, rounds, n_per_round, seed, trajectory, curve, start, final, improvement,
final_guardrail, held_out, converged_reason, honest_note, time_note`.
- `curve.breach_rate = [0.4545, 0.2727, 0.1818, 0.0]` — **monotone descent to zero** (the design's core claim, live-verified).
- `held_out = {vector:"emotional_urgency", breach_before:true, breach_after:true}` — **still breaches** (honest: did NOT generalize). `AutoImproveView.tsx:282` renders this plainly.
- `trajectory[1].clause_added = "reject_authority_pretext"`, `vectors_newly_blocked = ["authority_pretext","compliance_mirroring"]`; each `trajectory[i].summary` carries the full `Summary` shape (`breach_rate`, `by_vector` present) — `AutoImproveView.tsx:208` reads `rec.summary.breach_rate`.
- `converged_reason = "breach_rate_zero"`, `improvement.converged = true`.

Render-compat for the four called-out fields — all present and consumed:
`clause_added` (`AutoImproveView.tsx:221`), `curve` (`ImprovementCurve.tsx:15`),
`trajectory` (`:207`), `held_out` (`:281`). `ImprovementCurve` draws the polyline at full
opacity and only animates `pathLength` (`ImprovementCurve.tsx:104-115`) — never gated on opacity,
matching the locked design. `GET /auto-improve/latest` → 200 (disk-fallback `auto_improve.json`).
`/readyz` includes the `auto_improve` check → `true`.

## 3. Conversation flow — 🟢 SOLID

`ConversationView` → `api.transcript(runId?)` (`api.ts:139`) →
`/transcript/latest` (`api.py:418`) OR `/scans/{id}/transcript` (`api.py:437`).

Live evidence:
- `GET /transcript/latest` → `{run_id, attack_id, breach:true, transcript:[4 turns]}`,
  `turn0 = {role:"attacker", text:"Hi, this is Marcus…", state:"PRETEXT"}`.
- `GET /scans/1780177789-df9d/transcript` → `attack authority_pretext, breach true, 4 turns`.
- `GET /scans/nope/transcript` → 404 (correct unknown-run handling, `api.py:454`).

`ConversationView.tsx:73-88` calls `api.transcript`, falls back to `deriveFromEvidence(summary)`
if the endpoint is empty/absent (defensive, like AnalyticsView). Turns render in the timeline
(`:206-241`); breach turn flagged via `state==="leaked"` or PAN digit-count heuristic.
Note: the view declares its own local `TranscriptResponse` and casts `api as unknown as
MaybeTranscriptApi` — defensive belt-and-suspenders, harmless; `api.transcript` does exist and
returns the matching shape. The live `role` value ("attacker") satisfies the view's
`"attacker"|"target"` union at runtime.

## 4. Analytics / metrics / scorecard-latest / scans-history — 🟢 SOLID

- `AnalyticsView.tsx:31-40` calls `api.metrics()` + `api.scans()`, normalizes
  `Array.isArray(r) ? r : r.runs ?? r.scans ?? []`. `/scans` returns `{runs:[...]}` → `r.runs` branch hits.
- Live: `/metrics` → `{scans_run:1, last_breach_rate:0.5, last_run_id:"…"}`;
  `/scans` → 2 history rows with `{run_id,total_calls,leak_rate,breach_rate,max_grade,max_score,failed_calls}`
  matching `api.ts` `RunSummary` (`:51-59`) and `Metrics` (`:44-48`).
- `/scorecard/latest` (`App.tsx:65`) → 200, full summary. All four endpoints ↔ views aligned.

## 5. Cekura — 🟢 SOLID (wired into the normal flow, not just a make target)

- Env wiring: `CEKURA_BASE_URL/API_KEY/AGENT_ID/PERSONALITY_ID/SCENARIOS_PATH/OBSERVABILITY_PATH`
  (`cekura_integration.py:24,48-49,64,72,81`). Paths default to the corrected
  `/observability/v1/observe/` and `/test_framework/v1/scenarios/` (trailing-slash asserted to fail loud).
- **NOT orphaned:** `campaign_runner.py:24` imports it and `:53` calls
  `post_observability(result, call_id=call_id)` **per call** inside `run_campaign` — so every
  campaign (offline or live) feeds Cekura when a key is present (graceful no-op otherwise,
  errors swallowed at warning so eval ingestion never aborts a call, `:54`).
- `register_personas` (`:314`) + `check_connection` (`:220`, loud error/info, not a silent
  no-op) are additionally exposed via `make cekura-check` / `make cekura-sync`
  (`server/Makefile:34-42`). `_emit_live_artifact` (`attacker_bot.py:77`) is called on the live
  pipeline at `:299`.

## 6. Voice / live path wiring — 🟢 SOLID (statically consistent; live call not placeable here)

Full chain verified consistent:
- `bot.py` `REDDIAL_ROLE` dispatcher (`bot.py:44-85`): target/attacker/flower → lazy-imports the
  role module and awaits `module.bot(runner_args)`; runs `preflight.enforce(role)` first.
- `make serve-attacker` (`server/Makefile:52`): `REDDIAL_ROLE=attacker uv run python bot.py -t twilio --proxy …`.
- `make live-call TO=…` (`:54-56`) → `efficacy_run.py --mode live --to … --consent` →
  `run_live_efficacy` (`efficacy_run.py:68,80`) → `attacker_bot.place_outbound_call(to, consent)`.
  **PSTN is implemented** now (no `NotImplementedError`).
- `place_outbound_call` (`attacker_bot.py:152`) runs the **fail-closed** gate first
  (`safety_controls.check_destination` — kill-switch + E.164 + allowlist + consent, `safety_controls.py:76-97`),
  `CallGuard.acquire()` cap/rate-limit, sanitizes host (`validate_public_host`), then issues TwiML.
- `build_attacker_twiml` (`attacker_bot.py:133-147`): `<Connect><Stream url="wss://{host}{REDDIAL_WS_PATH:-/ws}"/>`.
- The runner ACTUALLY serves `/ws`: confirmed `'/ws' in inspect.getsource(pipecat.runner.run)` → True.
  `attacker_bot.bot()` (`:373-400`) handles `WebSocketRunnerArguments` via `parse_telephony_websocket`
  + `TwilioFrameSerializer`. The old 404'ing `/attacker-ws` default is gone.
- `run.sh` (API on 8080 + Vite on 5173, waits for `/healthz`, sets `VITE_API_TARGET`) — all referenced
  files exist; `vite.config.ts` proxies `/api` → `VITE_API_TARGET || :8080` with `^/api` rewrite.

The `/ws` route the TwiML targets and the route the runner serves are the **same path** — the
single most important live-path link, and it is consistent.

## 7. Frontend nav — 🟢 SOLID

- 6 nav items in `NAV` (`App.tsx:41-48`); router (`App.tsx:203-217`) maps every `ViewId` to a real
  view that fetches/derives real data. No `href="#"`, no no-op handler (re-confirmed; `grep` clean).
- **Fixed since ui-connect-review:** (a) `--text-tertiary` is now **defined** at `styles.css:12`
  (`rgba(255,255,255,0.55)`) — the prior 🔴 undefined grade-color fallback at `App.tsx:93` is resolved.
  (b) Settings doc links are now absolute GitHub URLs (`SettingsView.tsx:77,81`) — the prior 🟡
  relative-path-404 is resolved.
- `tsc --noEmit` clean; `npm run build` clean.
- 🟢 Minor (not a bug): `.improvement-curve` appears twice in `styles.css` (`:77` is the
  `opacity:1 !important` floor mandated by the locked design; `:1218` is the visual styling). Intentional.

## 8. Imports / contracts — 🟢 SOLID

- Whole server imports clean under `uv` (see gate list above) — no `ModuleNotFoundError`, no
  referenced-but-missing module. (The objc/av dylib warnings are a benign macOS opencv/pyav clash,
  not a wiring fault.)
- `api.ts` types vs live API responses: `Summary`, `Metrics`, `RunSummary`, `Transcript`,
  `AutoImproveResult`/`RoundRecord`/`AutoImproveCurve` all match the curled payloads field-for-field.
- `readyz` reports `attack_library_loaded:true, attack_count:12, campaign_runner:true,
  auto_improve:true` — all dependency hooks resolve.

---

## Prioritized summary

**Is everything wired properly? YES.** All 8 flows connect end-to-end with matching shapes;
gates green (151 server tests, tsc clean, build clean); live curls + the vite proxy all 200.

There are **no 🔴 broken-wiring gaps.** The "top 3" are cosmetic/nice-to-have, not breaks:

1. 🟢/nit — `ConversationView` redefines its own `TranscriptResponse` and casts the typed `api`
   client to a `MaybeTranscriptApi` (`ConversationView.tsx:24,70`) instead of importing `Transcript`
   from `api.ts`. Works at runtime; just looser typing than the rest of the app. Could import the
   shared type for a single source of truth.
2. 🟢/nit — Duplicate `.improvement-curve` block in `styles.css` (`:77` and `:1218`). Both
   intentional (opacity floor vs styling) but reads as accidental; a comment or merge would clarify.
3. 🟡/scope (carried, not a wiring break) — every wired number still grades RedDial's own mock; the
   live path is consistent but **no real third-party call has been placed** (per
   PRODUCTION_READINESS). The wiring to make that call is correct and present; the *evidence* is not.

**Bottom line:** the producer/consumer contracts hold across the API, the dashboard, the engine,
the auto-improve loop, and the (statically-verified) live voice path. Cekura is genuinely wired into
`run_campaign`, not just a make target. The two prior UI-connect defects are fixed.
