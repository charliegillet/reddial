# RedDial UI-Connect Adversarial Review

Branch: `feat/ui-connect-fix` · Reviewer role: devil's advocate · Date: 2026-05-31

Verdict up front: **UI is mostly connected.** Build is green, tsc clean, 136 server
tests pass, every nav/bell/button has a real handler, no external network calls, no
`href="#"`. The reported "dim main content" symptom is **real but is NOT a stuck
animation** — it is a low-contrast design choice (2% white glass surface + muted text)
plus one genuinely undefined CSS variable. Details below.

---

## 1. Dead controls — 🟢 PASS

- Nav rail (Threat Console / Analytics / Attack Library), the bottom Settings button,
  and the bell all have real `onClick` handlers (`App.tsx:100,113,139`).
- Sidebar "Launch Campaign" (`Sidebar.tsx:37`) and Dashboard empty-state
  "Launch Campaign Now" (`DashboardView.tsx:48`) both call `runScan`.
- No `href="#"`, no empty `onClick`, no handler-less icon buttons anywhere in `src/`.
- 🟡 Minor: Settings doc links (`SettingsView.tsx:77,81`) point to relative repo paths
  (`docs/plans/...md`, `README.md`). Served from the SPA these resolve against the app
  origin and will 404 in the deployed dashboard. Not "dead" (they navigate) but they
  go nowhere useful. Fix: drop them or point at a hosted docs URL / `/docs`.

## 2. Views render with real + empty data — 🟢 PASS

- **Analytics** calls the exact methods that exist in `api.ts`: `metrics()` (`api.ts:71`)
  and `scans()` (`api.ts:72`). `AnalyticsView.tsx:31-40` guards both behind
  `typeof === "function"` and normalizes the `scans()` result via
  `r.runs ?? r.scans ?? []` — `api.ts` returns `{ runs: RunSummary[] }`, so the
  `r.runs` branch matches. Types line up (`Metrics`, `RunSummary`).
- Empty/loading/error all handled: `loaded` flag flips empty copy from "Loading…" to
  "No … yet" and `.catch(() => {})` swallows API-down so the view never crashes
  (`AnalyticsView.tsx:79-83,120-127`).
- **Dashboard** handles null summary (empty onboarding), running (ScanningScreen), and
  results, all with `?? 0 / ?? []` guards in child components
  (`ScorecardSummary.tsx:12-15`, `VectorTable.tsx:10`, `EvidenceLog.tsx:10`).
- **Library** handles `attacks.length === 0` (`LibraryView.tsx:20`).
- **Settings** is pure props, no fetch — always renders.
- No prop/type mismatch between views and `api.ts`.

## 3. Contrast / dim main content — 🟡 REAL SYMPTOM, design-level (one true var bug)

The orchestrator's observation is legitimate, but the cause is NOT a stuck framer-motion
`opacity:0`. I verified every component: each `initial={{opacity:0}}` has a completing
`animate={{opacity:1}}` (ScorecardSummary, VectorTable, EvidenceLog, all views,
ScanningScreen). No wrapper sits at reduced opacity; the only CSS `opacity` rules are
intentional (disabled button `0.3`, decorative borders `0.5/0.6`, doc-link hover `0.7`,
noise `0.04`). The DashboardView "results" wrapper (`DashboardView.tsx:54`) has no
opacity at all → renders at 1.

Root cause of the dim look is contrast, two parts:

1. **🟡 Glass cards barely separate from the page.** `.card` (`styles.css:486`) fills
   with `--glass-bg: rgba(255,255,255,0.02)` (`styles.css:6`) — a 2% white wash — over
   `--bg-color: #030305` (`styles.css:5`) with `backdrop-filter: blur(20px)`. The card
   surface is essentially the same luminance as the page, so the whole main panel reads
   as a flat dim field, while the sidebar pops because its content uses `--accent-acid`
   (`#ccff00`) IDs and `--text-pure` headers directly on the dark bg.
   Concrete fix: raise card surface to ~4-6% and add a subtle border lift, e.g.
   `.card { background: rgba(255,255,255,0.045); border-color: rgba(255,255,255,0.12); }`
   (and/or bump `--glass-bg`). Also `.metric-box` at `rgba(10,10,15,0.8)`
   (`styles.css:586`) is nearly black-on-black — lift it similarly.

2. **🔴 Undefined CSS variable in the grade color fallback.** `App.tsx:77`:
   `GRADE_VAR[...] ?? "var(--text-tertiary)"`. `--text-tertiary` is **never defined**
   in `styles.css` (palette only has `--text-pure / --text-muted / --text-faint`).
   When `summary.max_grade` is missing/unknown, `gradeColor` becomes an invalid value;
   the browser drops it and the grade orb + Vuln-Score number fall back to inherited
   `currentColor`, which is dim/unpredictable. This is a concrete "not working" bug.
   Fix: change the fallback to a defined token, e.g. `"var(--text-faint)"` or
   `"var(--accent-acid)"`, at `App.tsx:77`.

3. **🟡 Heavy reliance on `--text-muted` (0.7) and `--text-faint` (0.4)** for in-card
   labels/body (`.metric-label`, `.cell-numeric`, `.chip`, `.data-table th` at 0.4).
   `--text-faint` table headers on the glass surface are close to the WCAG floor.
   Consider promoting body text to `--text-muted` minimum and headers to ~0.55.

## 4. Offline integrity — 🟢 PASS

- No `http(s)://` references in `src/` except the allowed Google Fonts `@import`
  (`styles.css:1`). dicebear is fully removed (avatar is now an inline SVG,
  `App.tsx:169-182`). No telemetry/CDN calls.

## 5. Build + tests — 🟢 PASS

- `npx tsc --noEmit` → exit 0, clean.
- `npm run build` → built in ~0.7s, no errors (304 kB JS / 15.5 kB CSS).
- `uv run --no-sync pytest tests/ -q` → **136 passed**, 1 unrelated Starlette deprecation
  warning.

## 6. State coverage — 🟢 PASS (intentional)

- Loading: `ScanningScreen` (scanline + spinner) on `running`.
- Empty: Dashboard onboarding (no summary), Analytics "No campaign metrics / No runs",
  Library "No attacks loaded", EvidenceLog "target held the line", VectorTable returns
  null when no vectors. All deliberate.
- Error: API-down surfaces in sidebar `err` banner (`Sidebar.tsx:41`) and the health pill
  flips to "API Offline"; the Launch button disables when `health !== "up"`
  (`Sidebar.tsx:37`). Analytics/Dashboard initial fetches `.catch` to empty states.

---

## Prioritized summary

1. 🔴 **`App.tsx:77` references undefined `--text-tertiary`** — invalid grade-color
   fallback. Replace with a defined token. (Single highest-value fix; small.)
2. 🟡 **Dim main content is a contrast/design issue, not a broken animation.** Raise
   `.card` / `--glass-bg` surface (~2% → ~4-6%) and lift `.metric-box`
   (`styles.css:6,486,586`) so cards separate from `#030305`.
3. 🟡 **Card body/label text leans on `--text-muted`/`--text-faint`** — promote in-card
   text contrast (esp. `.data-table th` at 0.4).
4. 🟡 **Settings doc links** (`SettingsView.tsx:77,81`) are relative repo paths that 404
   in the SPA — point at hosted docs or remove.

**Is the UI fully connected?** Mostly. All controls work, all views render with real and
empty/error data, offline-clean, build + tests green.

**Single most important remaining issue:** the undefined `--text-tertiary` fallback at
`App.tsx:77` (breaks the grade orb/score color in the no-grade path).

**Is the dim-content symptom real, and root cause?** Yes, real. Root cause is contrast,
not a stuck opacity: 2% glass card surface over a near-black background gives the main
panel no elevation, compounded by the undefined `--text-tertiary` token and heavy use of
muted/faint text. No framer-motion `opacity:0` is stuck — all have completing `animate`.
