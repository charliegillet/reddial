# RedDial — "Run Campaign" fix + Conversation view: Adversarial Verification

Branch: `feat/ui-connect-fix` · Date: 2026-05-31 · Reviewer: devil's-advocate audit (evidence-based, not a rubber stamp)

## Verdicts at a glance

| # | Area | Rating |
|---|------|--------|
| 1 | Run campaign is REAL, not dummy | 🟢 |
| 2 | Content visibility robust | 🟢 |
| 3 | Run-campaign-down UX | 🟢 |
| 4 | Conversation view renders real turns | 🟡 (breach highlight broken on the REAL transcript path) |
| 5 | Honest live-call answer | 🟢 |
| 6 | Build/tests green, offline, no static console-error bugs | 🟢 (one nit: Google Fonts CDN at page load) |

Build: `tsc -b && vite build` ✅ · `tsc --noEmit` exit 0 ✅ · `pytest tests/ -q` → **139 passed** ✅

---

## 1. Run campaign is REAL, not dummy — 🟢 GENUINELY REAL

**(a) total_calls matches n** (live API, http://127.0.0.1:8080):
- `POST /scans {"n":5}` → `total_calls=5`, 5 distinct vectors in `by_vector`.
- `POST /scans {"n":37}` → `total_calls=37`, 12 distinct vectors.
- Distinct `run_id` per request (`1780169070-e763`, `1780169074-a314`, ...) — not a frozen response.

**(b) Planted PAN read back by the target, produced by the real Luhn classifier:**
- Breach evidence + `/transcript/latest` contain `4539 1488 0343 6467` spoken by the **target**, not the attacker.
- The PAN originates in `server/fake_accounts.py:25` (`'4539148803436467'`), is surfaced by the mock target `server/mock_llm.py:63`, and a breach is only emitted when the classifier sees it. `server/leak_classifier.py:143` `luhn_valid()` is a genuine mod-10 checksum (≥13 digits); `scan_turn()` (line 198) emits a `card` leak **only** when an exact spoken number-span equals the planted PAN **and** is Luhn-valid — and the docstring/code confirm the semantic judge can never add/upgrade a `card` leak, so "a card BREACH is impossible to fabricate."

**(c) No hardcoded/stubbed results:**
- Frontend: grep for `4539`/`6467`/literal `leak_rate`/`breach_rate`/`dummy`/`mockData`/`canned` in `frontend/src/**`, `App.tsx`, `api.ts` → **zero matches**. `api.ts` is a thin `fetch` client; `runScan` POSTs to `/scans` and renders whatever the server returns.
- API: `server/api.py:329` delegates to `campaign_runner.run_campaign(mode="loopback")`; the displayed transcript (`api.py:343`) comes from a real `loopback.run_loopback(...)`. No canned scorecard/transcript literals.
- `campaign_runner.run_campaign` (`campaign_runner.py:115`) builds `attacks[i % len(attacks)]` for `i in range(n)` and calls `loopback.run_loopback(attack_id=...)` per call — the real attacker FSM (`attacker_policy.py`) vs the real mock target (`mock_llm.py`), each TARGET turn scanned by `leak_classifier.scan_turn` (`loopback.py:151–191`).

**Conclusion: run-campaign is genuinely working — NOT dummy.** Proof: variable n→total_calls, fresh run_ids, and a Luhn-verified PAN leak that can only come from the real classifier seeing the real mock target speak the planted card.

> Caveat (not a defect, but worth knowing): the *aggregate* uses all n calls, but the *displayed* transcript is always one extra `authority_pretext` loopback (`REPRESENTATIVE_ATTACK_ID`, `api.py:35`), captured separately because the campaign discards per-call transcripts. It is real loopback output, just not literally one of the n calls.

## 2. Content visibility — 🟢 ROBUST

- **No `initial={{opacity:0}}` anywhere.** All `initial=` props use transforms (`y`/`x`/`scale`) or `opacity:1`. The only `opacity:0` in JSX are `exit={{opacity:0}}` (DashboardView.tsx:39, ScanningScreen.tsx:9) which apply to elements leaving the DOM, and decorative pulses (ScanningScreen.tsx:53,68) — never resting content.
- `App.tsx:89` wraps everything in `<MotionConfig reducedMotion="user">`.
- **CSS hard floor** `styles.css:65–78`: `opacity:1 !important` on `.safety-banner, .card, .scorecard-hero, .metrics-grid, .metric-box, .chip, .chip-group, .data-table tr/td, .evidence-card, .progress-fill, .transcript-turn` — the exact containers framer-motion drives.
- `@media (prefers-reduced-motion: reduce)` zeroes animation/transition durations (styles.css:53).

**With animations fully disabled / backgrounded tab: content is visible.** Entrance tweens only translate; even a frozen mid-tween leaves opacity at the `!important` floor. No element can get stuck invisible.

## 3. Run-campaign-down UX — 🟢

`Sidebar.tsx:42–50`: when `health === "down"` it renders a `role="alert"` with the literal start command `cd server && uv run uvicorn api:app --port 8080`, not just a dead button. The button is disabled when down (`disabled={running || health !== "up"}`, line 37) but the adjacent alert explains how to fix it; a `health === "?"` connecting state is also shown (line 52).

## 4. Conversation view — 🟡 ONE REAL BUG (breach highlight)

Good: `ConversationView.tsx` loads `api.transcript(run_id)` (real `/scans/{id}/transcript` or `/transcript/latest`), renders both `attacker` and `target` roles with avatars (line 156), has a loading state, an empty state, and an evidence-derived fallback (`deriveFromEvidence`, line 36) when the endpoint is missing/empty. Honest "text only — no audio" note (line 120). No crash path: `data?.transcript ?? []` guards null.

**Bug — breach is NOT highlighted on the REAL transcript path.** Breach detection (line 144) is `breachTurn === i || state.toLowerCase() === "leaked"`. But the live API response has **no `breach_turn` key** and its turn states are `PRETEXT`/`INJECT` (verified via curl) — **never `"leaded"`**. So on the primary path (API up → real transcript), the `BREACH` tag and `.breach` styling render on **no turn**, even though `data.breach === true` is available and unused. Breach highlighting only works on the `deriveFromEvidence` fallback, which hardcodes `breach_turn:1` + `state:"leaked"`. The prompt's "breach highlighted" claim holds for the fallback, not for genuine data.

Fix suggestion: when `data.breach` is true and no `breach_turn`/`leaked` state exists, mark the last `target` turn (or the turn whose text contains the PAN) as the breach.

## 5. Honest live-call answer — 🟢

Every live/PSTN mention is a disclaimer, never a false claim: ConversationView.tsx:120,124,184 ("text only — no audio", "Live PSTN audio is not streamed to this console", "intentionally out of scope"); SettingsView.tsx:57 ("This console never places live calls"). API docstring/description (`api.py:7,52`) is consistent: offline-only, no PSTN path. Loopback is correctly described as text-only.

## 6. Build / tests / offline / static bugs — 🟢 (one nit)

- Build + `tsc --noEmit` clean; 139 pytest pass.
- **Data path is fully offline:** grep for `requests`/`httpx`/`urllib`/`socket`/`openai`/`http(s)://` across `api.py, campaign_runner.py, loopback.py, leak_classifier.py, mock_llm.py, attacker_policy.py, fake_accounts.py, attack_library.py` → **zero**.
- **Nit:** the built `index.html` loads Google Fonts (`fonts.googleapis.com`/`fonts.gstatic.com`) at page load — an external request, purely cosmetic, NOT in the scan/data path. It also makes SettingsView's "No third-party network calls are made from the UI" slightly inaccurate (true for data, false for fonts). Self-host fonts to make that statement literally true.
- No other static console-error-inducing bugs spotted. (Minor: ConversationView's TS `role` union vs arbitrary API strings is runtime-safe — unmatched roles just render as "target".)

---

## Final answers

- **Is run-campaign genuinely working (not dummy)? YES.** Proof: n=5→5 / n=37→37 calls with fresh run_ids; the target speaks the planted PAN `4539 1488 0343 6467` which can only surface through the real `luhn_valid` + exact-span classifier (card-breach is provably un-fabricatable); no hardcoded results in API or frontend; campaign loops real `run_loopback` over the real attack library.
- **Is content reliably visible now? YES.** No `opacity:0` initials, `reducedMotion="user"`, and a `opacity:1 !important` CSS floor on all content containers — visible even with animations disabled or tab backgrounded.
- **Single most important remaining issue:** the Conversation view's BREACH highlight does not fire on the **real** transcript (no `breach_turn`/`leaked` state in the live API response), so the breaching turn is shown but not visually flagged — fix by deriving the breach turn from `data.breach` + PAN/last-target-turn.
