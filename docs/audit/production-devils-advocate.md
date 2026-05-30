# RedDial — Devil's Advocate on "production level + fully wired"

**Date:** 2026-05-31 · **Branch:** `audit/production-wiring` · **Role:** adversarial reviewer.
**Bar:** not "does the loopback demo survive a judge" — it's *"can a paying customer point this at
their own live voice agent over a real phone line and trust the report, and is the system
hardened/multi-tenant enough to operate?"* Against that bar: **no.**

**Method:** read README, `PRODUCTION_READINESS.md`, and the five prior audit docs
(devils-advocate, fix-review, phases-review, hardening-review, auto-improve-review) to avoid
repeating settled findings; then verified the *current* state with `file:line`, live curls against
`:8080`, the running dashboard `:5173`, the installed pipecat 1.3.0 runner source, `pytest`
(151 passed), and a scan of `results/` + git history. I build on the known story and report what has
**moved** since those audits, plus one **new overclaim regression** I found.

---

## What genuinely improved since the last audits (credit where due — not crying wolf)

The maintainers closed several specific blockers. I verified each:

- **`/ws` is real, not a 404.** Prior audits flagged the outbound TwiML pointing at the never-registered
  `/attacker-ws` (guaranteed connect-back 404). I read the installed runner: pipecat 1.3.0
  `pipecat/runner/run.py:1096` registers `@app.websocket("/ws")` → `_run_telephony_bot` →
  `bot_module.bot()` and the docstring at `:1049` says `/ws` is *always* registered when telephony
  deps are present. `_get_bot_module()` (`:286-301`) returns `__main__` (the base image's `bot.py`),
  which dispatches by `REDDIAL_ROLE`. `attacker_bot.build_attacker_twiml` (`attacker_bot.py:142`) now
  defaults to `/ws`. **So the structural assumption behind `place_outbound_call` is correct in this
  pipecat version.** This is a genuine fix.
- **Cekura is wired into the actual product flow, not just `make cekura-sync`.** A normal dashboard
  scan (`POST /scans` → `campaign_runner.run_campaign` → `run_one` → `_maybe_post_cekura`,
  `campaign_runner.py:99`) now attempts a Cekura observability post per call. Endpoint paths were
  corrected (`cekura_integration.py:48-49`: `/test_framework/v1/scenarios/` and
  `/observability/v1/observe/`, with asserts that they end in `/`; the old wrong paths are documented
  at `:28-37`). So premise 4 is **partly answered**: it is wired, not a side script.
- **Safety gate is enforced in code and fail-closed** (`safety_controls.check_destination` + `CallGuard`,
  exercised by `tests/test_entrypoint.py:98-100` and verified live in the prior audits).
- **Concurrency cap holds:** `POST /scans {"concurrency":999}` → **422** ("less than or equal to 16").
- **Offline harness, auto-improve honesty, classifier false-positive fix, fake-PII hygiene, CI/coverage**
  are all real (confirmed by the prior reviews; `pytest tests/ -q` → **151 passed** here).

These are real. They are also, almost entirely, about **operability and structural correctness of code
that has still never executed against a real agent.** The needle moved from "demo" toward "alpha that's
safe to attempt" — not to "production."

---

## 1. "Everything is wired" — the live voice path is still UNEXECUTED (the wires are connected; no current has ever flowed)

The whole product value — call a real agent, social-engineer it, detect a real leak through real
STT/TTS garble, score it — lives in a layer that **has never run end-to-end, not once, anywhere.**

- **Zero recorded live runs.** `results/` does not exist; `find . -name "efficacy_live_*.json"` →
  nothing; no `real-agent` artifact anywhere in the repo; git log has no "recorded live run" commit.
- **Every test stops at the wire.** The only tests touching the voice layer (`test_entrypoint.py`)
  assert the **TwiML string** (`:51-63`) and the **safety gate** with a **stubbed Twilio client**
  (`:80-100`). Nothing instantiates the Pipecat pipeline, the STT/TTS services, or `bot()`.
- **`_emit_live_artifact` is unreachable except on a real call.** It only fires inside
  `AttackDriver.process_frame` (`attacker_bot.py:299`), which requires a live pipecat pipeline with a
  connected media leg producing `TextFrame`s. No test, no run, no fixture ever drives it. The
  "capture loop is CLOSED in code" claim (phases-review maintainer note) means *the code exists*, not
  *the loop has ever closed*.
- **STT → Nemotron → TTS over μ-law audio is 100% theoretical.** Smart-Turn/8 kHz handling,
  barge-in, transcription garble, the Nemotron reasoning empty-output guard (`nemotron_llm.py:33-43`,
  a thoughtfully-written but **runtime-unverified** patch) — none has touched real audio or a real
  model.

**Is `/ws` actually served the way `place_outbound_call` assumes?** *Structurally yes* (verified in
pipecat 1.3.0 source above) — but "the route exists in the library" ≠ "a Twilio connect-back has ever
reached our `bot()` and run a pipeline." The route registration depends on the runner being started
with telephony transport (`-t twilio --proxy <host>`), the `--proxy` host matching `PUBLIC_HOST`, the
base-image entrypoint resolving to RedDial's `bot.py`, and the WS upgrade surviving Twilio's
handshake. Every one of those is **unproven in practice.**

**Quantification:** the entire ~1,600+ LOC voice/Twilio/Nemotron/STT/TTS layer
(`attacker_bot.py`, `target_bot.py`, `nemotron_llm.py`, `nvidia_stt.py`) is excluded from the coverage
floor (`pyproject.toml` omit list — honestly so, since it needs live keys) and has **0% runtime
coverage**. The product's value proposition lives there. The 151 passing tests exercise a text loop
and an HTTP control plane, not a phone call.

**Verdict on premise 1:** the wires are connected and the `/ws` assumption is structurally sound, but
**no current has ever flowed.** "Everything is wired" is true only in the sense that nothing is *known
broken* — and the one path most likely to break (telephony connect-back + audio + reasoning model) is
exactly the path with zero verification.

## 2. "Production level" vs a single-user laptop demo — it is the latter

I probed the live API at `:8080`:

- **No authentication, anywhere.** `POST /scans` with no header → **200** and ran a full scan.
  `POST /auto-improve` with `{}` → **200**. `grep` for `Depends|api_key|Authorization|Bearer|auth` in
  `api.py` → nothing. **Anyone who can reach `:8080` can run scans and the auto-improve loop.**
- **CORS `allow_origins=["*"]`** (`api.py:73-79`) — fine for a single-user FAKE-data tool with
  `allow_credentials=False`, but it is **not** a multi-tenant posture; any web page can drive the API.
- **In-process, single-process state.** Run registry is a module-level `dict` + `threading.Lock`
  (`api.py:83-84`). No DB, no persistence of the registry across restart — a process restart loses all
  run history. Not multi-instance, not horizontally scalable.
- **No API rate limiting.** No `slowapi`/throttle middleware. The only limits are input clamps
  (`n ≤ 500`, `concurrency ≤ 16`). A synchronous endpoint that runs a thread-pool campaign per request
  with no per-client throttle is a trivial self-DoS for an internet-exposed deployment.
- **No real concurrency for *live* calls.** `_DIAL_GUARD` is a per-process singleton with a
  non-thread-safe `_count`/`_last_ts` (phases-review §3 flagged this pre-emptively). The "200-call
  fleet / 1000+ concurrent" story in PLAN has no implementation on the live path.

**Verdict on premise 2:** this is a **single-operator laptop tool** with a clean offline core and a web
console. Calling it "production level" conflates "the code is tidy and CI is green" with "hardened,
authenticated, multi-tenant, operable under load." It is not the latter.

## 3. The numbers are still self-graded — and one knob is honesty theatre's opposite

Unchanged from the prior teardown and confirmed live: every scorecard number
(`breach_rate 0.42`, grade C, "median time-to-leak 18.0s") is **this attacker beating this project's
own keyword-gated mock** (`mock_llm.py`), over a text loop, with a **modeled** `turns × 9s` duration
(`time_note: "modeled · loopback @ ~9s/turn (not live audio)"` in the live response I captured). The
per-vector results are binary string-overlap. To the team's credit this is **honestly labeled**
everywhere (banner, `time_note`, `proves_real_world_efficacy=false` on loopback).

**Auto-improve** is the same closed system, and the auto-improve-review correctly found it *real and
honest within its scope*: failing-vector eval → derived keyword clause → re-parsed by the mock → fewer
breaches next round, monotone to zero, with a fair held-out (`emotional_urgency`). I do not relitigate
that — it is a legitimate, *self-contained* "eval data flows back into the agent" demo. **But be blunt
about what it proves for a real customer: nothing.** It hardens a keyword automaton against
keyword-matched clauses. The descending curve is a property of a hand-built monotone lattice, not of
any learned robustness against a GPT-4o/Gemini support agent over a phone line. The held-out proves the
loop doesn't trivially cheat — it does **not** prove the technique generalizes.

**What this does NOT prove for a customer:** real false-positive / false-negative rates against real
agents, detection survival through STT garble, behavior of a real model under social pressure, or that
a single clause RedDial "suggests" would actually harden a customer's bot.

## 4. Cekura — wired into the flow, but the connection itself is unproven and silently no-ops

Premise 4 is the one the team most clearly advanced (see "improved" above): a normal scan now attempts
a Cekura post per call. **But:**

- It is a **graceful no-op on missing key / missing dep / DNS / timeout / 402 / any non-2xx**
  (`cekura_integration._post` → `_stub`, `cekura_integration.py:92-135`), and `_maybe_post_cekura`
  swallows every exception (`campaign_runner.py:54-55`). For an *assurance* product, a verification sink
  that fails **invisibly** is the worst failure mode — an operator can believe "RedDial + Cekura is
  live" while no post has ever succeeded.
- The endpoint paths were *corrected in code*, but there is **no captured evidence of a real 2xx** from
  a live Cekura tenant in the repo — no fixture, no recorded `posted: true` artifact. `make cekura-sync`
  / `make cekura-check` exist, but "the endpoints are probably right now" is still a claim, not a
  verified round-trip. The integration's correctness rests on comments asserting the old paths 404/405.

So: **wired, yes; proven against real Cekura, no** — and built to hide its own failure by default.

## 5. Operational reality — point a phone at a fresh Pipecat Cloud deploy; what breaks first?

Ordered by likely failure:

1. **Missing live config kills it before audio.** `preflight.enforce` (`preflight.py:21-24, 72-80`)
   hard-requires `NVIDIA_ASR_URL`, `NEMOTRON_LLM_URL`, `GRADIUM_API_KEY` per role and **raises** if any
   is unset — so a deploy without all NIM/TTS endpoints fails fast (good hygiene, but it *will* fail on
   day one until every endpoint is provisioned and reachable from the cloud).
2. **`PUBLIC_HOST` / `--proxy` mismatch → connect-back never lands.** The TwiML streams to
   `wss://$PUBLIC_HOST/ws`; if `PUBLIC_HOST` ≠ the actual public hostname the runner is served on (or
   the runner wasn't started with `-t twilio --proxy <host>`), Twilio's `<Stream>` dials a host that
   doesn't serve `/ws`. Unverified end-to-end.
3. **Caller-ID verification.** `from_number` must be a Twilio-verified caller ID
   (`attacker_bot.py:181`); an unverified number → Twilio API error at `calls.create`. Never exercised.
4. **Nemotron reasoning empty-output.** If thinking is enabled and the model emits only `reasoning`
   deltas with empty `content`, the spoken turn is silent — the guard in `nemotron_llm.py` is *supposed*
   to synthesize a fallback chunk, but this has **never run against a real reasoning endpoint.**
5. **8 kHz audio / Smart-Turn.** `target_bot.py:521-524` sets `audio_in/out_sample_rate=8000` for
   telephony — the prior audits cite a known Pipecat caveat here; unverified with real μ-law.

In short: a fresh deploy + a real phone call has **at least five unproven failure points in series**
before a single leak could ever be detected.

## 6. The single most embarrassing question (unchanged, still unanswerable)

**"Show me one vulnerability report RedDial produced by calling an AI agent your team did NOT write —
and prove the phone call actually happened."**

It still cannot. There is no recording, no real third-party target, no `efficacy_live_*.json`, no
verified Cekura round-trip. A CISO's follow-up — *"what's your false-positive/false-negative rate
against real agents with real transcription?"* — has the honest answer: *"unknown; we've only ever run
exact-string matching against our own mock's clean text output."*

## NEW finding this pass — an anti-overclaim REGRESSION in the live artifact (🔴)

The careful discipline elsewhere (`efficacy_run.run_loopback_efficacy` stamps `proven=False`;
`run_live_efficacy` uses `proven=None` pending a human verdict — `efficacy_run.py:54, 68`) is
**contradicted** by the live capture path:

`attacker_bot._emit_live_artifact` writes
`"proves_real_world_efficacy": bool(breached)` (`attacker_bot.py:98`) with
`"target_kind": "real-agent"` (`:97`).

So the *very first* live call — including a self-test where the attacker dials your **own**
`target_bot` (the only target you can run today) — that produces a breach will write an artifact
asserting `proves_real_world_efficacy: true, target_kind: "real-agent"`. The human-readable `note`
says "verify the target is a consented agent your team did NOT author for this to be evidence," but the
**boolean is already True** and a downstream consumer doing `if art["proves_real_world_efficacy"]:`
will treat your own mock-beats-mock loopback-over-the-phone as real-world proof. For an assurance
product, the one place that must *never* auto-assert proof just does. **Fix:** stamp `None`/`False` and
`target_kind="unverified"` until an operator records a consent + non-self-authorship verdict — mirror
`run_live_efficacy`'s discipline.

---

## VERDICT

- **"Production level + fully wired"? — NO.** The wires are connected (and the `/ws` assumption is, to
  the maintainers' credit, structurally correct in pipecat 1.3.0), but the live product has **never
  executed**: no real call, no real-audio leak detection, no verified Cekura round-trip, no recorded
  artifact. The API is unauthenticated, single-process, in-memory, CORS-`*`, with no rate limiting —
  not a hardened multi-tenant service. Every number is still the system grading its own homework.

- **Maturity label:** **late-alpha / pre-beta.** The offline harness + control plane + dashboard +
  CI/CD + safety gate are *beta-grade for an internal tool*; the live voice product — the thing
  customers would pay for — is **pre-alpha (unexecuted).** Net: **alpha that's safe to attempt**, as the
  prior audits concluded. The new wiring (`/ws`, Cekura-in-flow) is real progress *toward* a first live
  run, not evidence one happened.

- **Distance to production:** unchanged at roughly **2–4 months** of focused work, gated on: (1) one
  recorded end-to-end live run against a consented non-self agent with real STT/TTS, proving detection
  survives garble; (2) AuthN/Z + rate limiting + persistent state on the API before any non-laptop
  exposure; (3) a *verified* Cekura 2xx round-trip with a fail-loud (not silent-no-op) default;
  (4) fix the `_emit_live_artifact` proof regression; (5) replace keyword posture with a real,
  evaluated model classifier on the live path.

- **Single highest-leverage fix:** **place one real, recorded, gated call against an agent the team did
  not author, capture the transcript + leak verdict, and attach it** — with the live-artifact proof flag
  corrected so it can't lie. That one artifact converts "the plumbing compiles and the route exists"
  into "the product has run once," and it simultaneously exercises (and would expose) every one of the
  five operational failure points above. Until it exists, "production level + fully wired" is a claim
  about *code that has never carried a phone call.*
