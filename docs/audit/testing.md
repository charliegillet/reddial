# RedDial — Testing & Reliability Audit

Role: Testing & Reliability auditor, production-readiness review.
Branch: `audit/production-readiness`. Working dir: `/Users/nihalnihalani/Desktop/Github/reddial`.
Method: ran the suite, measured coverage with `pytest-cov`, re-ran loopback for byte-stability,
and fed adversarial inputs to the pure functions + voice no-op paths. All repros are inline and
were executed against the repo as it stands.

Legend: 🔴 BLOCKER (must fix before prod) · 🟡 SHOULD-FIX (a real gap, ship-with-known-risk) · 🟢 OK

---

## 1. Suite status & CI-runnability

**Pass count:** `cd server && python3 -m pytest tests/ -q` → **45 passed in ~0.02s.** Fast, no network.

Suite breakdown (5 files, 45 tests):
- `tests/test_leak_classifier.py` — classifier ground truth, normalization, score formula
- `tests/test_classifier_falsepos.py` — the devil's-advocate false-BREACH regressions (6 benign + readbacks)
- `tests/test_policy.py` — FSM progression, label alignment, determinism
- `tests/test_loopback_breach.py` — end-to-end loopback breach + determinism (fake clock)
- `tests/test_scorecard.py` — aggregate + HTML render

### 🔴 The suite is NOT CI-runnable with the natural invocation

The README and PLAN both tell you to run `python3 -m pytest tests/ -q`, but a default
`python3 -m pytest` (no path — what most CI configs and contributors actually run) **fails at
collection**:

```
$ cd server && python3 -m pytest -q
ImportError while importing test module '.../server/test_nemotron_llm.py'.
E   ModuleNotFoundError: No module named 'pipecat'
!!! Interrupted: 1 error during collection !!!
```

`server/test_nemotron_llm.py` (a pre-existing starter test) imports `pipecat` at module top.
pipecat is NOT installed in the test interpreter, so a bare collection aborts the **entire** run —
including the 45 passing tests. The suite only passes because the docs hard-code the `tests/` path
argument, which sidesteps collection of the root-level file.

There is **no `pytest.ini` / `[tool.pytest.ini_options]` / `setup.cfg`** to set `testpaths`,
add a `pipecat` import marker/skip, or configure `--ignore`. There is **no `.github/workflows`**
directory — no CI at all. So "45 passed" is true only for a human who types the exact documented
command; the moment this is wired to CI generically it red-flags on collection.

**Fix:** add `[tool.pytest.ini_options] testpaths = ["tests"]` (or
`addopts = "--ignore=test_nemotron_llm.py"`), or gate the pipecat import in `test_nemotron_llm.py`
behind `pytest.importorskip("pipecat")`. Then add a minimal CI workflow.

### Two-interpreter hazard

Tests run under **system python3** (`/opt/homebrew/.../python3.14`, no `loguru`/`pipecat`), while
the full deps live in `server/.venv`. This split is itself a reliability risk: the import behavior
of the voice layer differs by interpreter (see 🔴 in §3).

---

## 2. Coverage — what is exercised vs not

Measured with `pytest-cov` (present in venv: coverage 7.13.5):

```
$ python3 -m pytest tests/ -q --cov=. --cov-report=term-missing
```

| Module | Stmts | Cover | Verdict |
|---|---:|---:|---|
| `leak_classifier.py` | 118 | **91%** | well covered (core asset) |
| `scorecard.py` | 74 | **99%** | well covered |
| `attacker_policy.py` | 77 | **84%** | good |
| `loopback.py` | 97 | **79%** | good (LLM/`say` branches uncovered) |
| `mock_llm.py` | 70 | **74%** | OK |
| `attack_library.py` | 37 | **54%** | `ladder_up`/`switch_vector` partly uncovered |
| **`attacker_bot.py`** | 107 | **0%** | UNTESTED voice layer |
| **`target_bot.py`** | 170 | **0%** | UNTESTED voice layer |
| **`cekura_integration.py`** | 75 | **0%** | UNTESTED HTTP path |
| **`campaign_runner.py`** | 40 | **0%** | UNTESTED batch driver |
| **`gepa_mitigation.py`** | 26 | **0%** | UNTESTED reverify |
| **`nemotron_llm.py`** | 25 | **0%** | UNTESTED |
| **`nvidia_stt.py`** | 235 | **0%** | UNTESTED |
| **`mock_backend.py`** | 3 | **0%** | UNTESTED |
| `bot.py` / `bot-gpt.py` / `bot-nemotron.py` | 167 ea | 0% | starter modules, untested |
| **TOTAL (all .py)** | 1991 | **33%** | |
| Core testable engine only (6 modules) | 473 | **83%** | |

**The gap, quantified:** the 6 deterministic engine modules are at **83% line coverage** — genuinely
solid for the loopback/classifier/scorecard path. But **~1,992 lines** of first-party non-starter
code (`attacker_bot`, `target_bot`, `cekura_integration`, `campaign_runner`, `gepa_mitigation`,
`nemotron_llm`, `nvidia_stt`, `mock_backend`) have **zero test coverage** — including everything
that touches a real phone, a real model, or Cekura's API.

---

## 3. Untested critical paths

### 🔴-A The entire voice layer is untested AND fails to import-smoke under the test interpreter
`attacker_bot.py` and `target_bot.py` docstrings claim they "MUST import cleanly with no keys."
That claim is **false in the test interpreter**:

```
$ cd server && python3 -c "import attacker_bot"
ModuleNotFoundError: No module named 'loguru'      # top-level, non-lazy import (attacker_bot.py:31)
$ python3 -c "import target_bot"
ModuleNotFoundError: No module named 'loguru'
```

Under `.venv/bin/python` they DO import (loguru+pipecat present). So the modules are not
unconditionally importable — they require the heavy voice deps to be installed even just to load
the pure helpers (`build_attacker_twiml`, `place_outbound_call`, the persona prompt). There is no
import-smoke test, so this regression class (a stray non-lazy import sneaking into a "key-free"
module) is completely unguarded. The pipeline bodies (`_run_bot_impl`, `bot`, the `AttackDriver`
frame processor, target tool/guardrail wiring) are **never executed by any test** and cannot be
without a live NIM+Twilio rig.

### 🔴-B `campaign_runner.run_campaign` has no per-call error isolation — one bad call kills the batch
The overnight 200-call campaign is the pitch's "real harness" centerpiece. But `run_campaign`
(`campaign_runner.py:58-60`) is a bare loop with no try/except:

```python
for i in range(n):
    attack = attacks[i % len(attacks)]
    results.append(run_one(attack, mode=mode, ...))   # any raise here aborts everything
```

Repro (monkeypatch `loopback.run_loopback` to throw on call #3 of 6):
```
CAMPAIGN ABORTED by one bad call: RuntimeError call 3 blew up mid-batch
```
A single malformed turn, transient model error, or unexpected exception loses **all** accumulated
results and writes no scorecard. In a real overnight batch with live models, this is a near-certain
data-loss event. **Fix:** wrap `run_one` per-iteration; record failed calls as a result row and
continue; persist incrementally.

### 🟡-C Loopback does not isolate a failing target turn
`loopback.run_loopback` calls `target_llm.reply(...)` with no guard. A target that raises propagates
straight out of the call:
```
Boom target propagates: RuntimeError target exploded
```
Empty/`None`/garbled target turns are handled safely (`scan_turn(None)` → no leak, no crash; loopback
just reports `breach=False`), which is good. But an *exception* from the target (realistic on the
live path) is unhandled. Combined with 🔴-B this is how the campaign dies.

### 🟡-D The LLM-backed (non-deterministic) classifier judge path is untested
`leak_classifier.scan_turn(text, llm=judge)` is the semantic-judge path. The suite **only ever calls
`scan_turn` with `llm=None`** (ground-truth only) — grep confirms no test passes an `llm`. I probed it
manually; the error handling is actually **good**:
- judge raises → swallowed, returns ground-truth leaks (try/except at `leak_classifier.py:234-237`).
- judge returns `None` / a string / dict missing keys → handled, no crash.
- judge returns `{"kind":"card"}` → correctly **downgraded to "other"** (hard guard prevents the
  semantic path fabricating a card BREACH).

This is solid logic that is **entirely unverified by the suite** — a refactor could silently remove
the `kind=="card"` guard (the headline "judge-proof" safety property) and every test would still pass.

### 🟡-E Cekura HTTP path, Twilio outbound, GEPA reverify — testable but untested
None of these are covered, yet all have deterministic, key-free surface that *should* be tested:
- `cekura_integration`: no-op returns a labeled stub when `CEKURA_API_KEY` is absent; `register_personas`
  returns `[{"_stub": True}]`; `post_observability(...)` returns `False`; 402 handling. **Verified by
  hand; zero tests.**
- `attacker_bot.build_attacker_twiml(host)` → correct TwiML string; `place_outbound_call(...)` with no
  keys → raises a clear `RuntimeError` listing missing vars. **Verified by hand; zero tests.**
- `gepa_mitigation.reverify("authority_pretext")` → `{breach_before: True, breach_after: False,
  note: "blocks THIS attack..."}` runs fully offline via loopback. **Verified by hand; zero tests** —
  this is the demo's GEPA tab and nothing guards that `breach_before` stays True / `breach_after` stays
  False.

---

## 4. Determinism & flake

### 🟢 The loopback demo is byte-stable — verified
Ran `run_loopback()` 5× (default real-clock path) and hashed `{breach, leaked, fields, score, grade,
turns, full transcript}`:
```
distinct transcript/result sigs (5 runs): 1
```
One signature across five runs — byte-identical transcript, breach flag, score, grade. No RNG, no
dict-ordering dependence (the FSM is keyword-deterministic; `mock_llm` rebuilds from full history).
The demo will not flake on content.

### 🟡 The one nondeterminism source: wall-clock `seconds_to_first_leak`
Default `run_loopback()` uses `time.monotonic`, so `seconds_to_first_leak` varies run-to-run:
```
seconds_to_first_leak across runs (real clock): [6.1e-05, 6.4e-05, 5.8e-05]
```
It is ~0.00006s (sub-millisecond), which (a) flakes the raw value and (b) the scorecard would render
as "0.0s time-to-leak" — advertising that no real call happened. The honest fix is already wired:
`campaign_runner` passes `seconds_per_turn=9.0` and labels it "modeled · not live audio", and the
loopback test injects a fake clock. **But `run_loopback()` called bare (the README quick-start
command) still emits the flaky sub-ms value** — only the campaign path is fixed. The score's `speed`
term depends on this, so a bare run's `score` could in principle differ by 1 across runs at the
rounding boundary (didn't observe it flip in 5 runs, but it's the one theoretical flake). Tests pin
it with a fake clock, so the suite itself is not flaky.

---

## 5. Reliability under failure (adversarial probes on pure functions)

I fed weird/adversarial inputs directly to the pure functions. Results:

### 🟡-F `leak_classifier.score(..., max_turns=0)` raises `ZeroDivisionError`
```python
lc.score([Leak('card',40,True)], 1e9, 999, 0)   # -> ZeroDivisionError: division by zero
```
`ease = (max_turns - turns)/max_turns` divides by `max_turns` with no guard. Not reachable through
`run_loopback`'s default (12) but reachable if any caller passes `max_turns=0`, and it's a latent
landmine in a public function. **Fix:** guard `max_turns <= 0`.

### 🟡-G `scorecard.aggregate` raises `KeyError 'attack_id'` on a malformed row
```python
scorecard.aggregate([{}])   # -> KeyError: 'attack_id'
```
`by_vector` does `c["attack_id"]` (hard index) while every other field uses `.get(...)`. A result row
missing `attack_id` (plausible once 🔴-B is fixed and failed calls are recorded as partial rows)
crashes the whole scorecard render. **Fix:** `c.get("attack_id", "unknown")`.

### 🟢 Empty / None / huge / unicode inputs to the classifier are safe
`scan_turn("")`, `scan_turn(None)`, a 5000× repeated PAN, fullwidth unicode digits, the judge-throw
path — none crash; all return sensibly (no false breach). Robust against junk input.

### Classifier edge cases the tests miss (false-negatives — not crashes, but silent misses)
These are exact-match + Luhn limitations; they don't misfire, they silently miss a real leak — which
for a *detection* product is the more dangerous direction, and none are in the suite:
- **Newline-separated PAN read-back misses:** `scan_turn("4539\n1488\n0343\n6467")` → no breach
  (newlines break the number span). Realistic if an LLM/STT emits line-broken digits.
- **A word mid-number misses:** `"4539 1488 card 0343 6467"` → no breach (the word splits the span).
- **DOB is effectively undetectable in natural form:** planted DOB is `1985-04-12`; a spoken
  `"04/12/1985"` normalizes to `04121985 ≠ 19850412`, so the dob field never fires for any natural
  month/day/year ordering. The `dob` weight in the score is dead in practice.
These are acceptable *if scoped honestly* ("verbatim/encoded leaks only", which the code comments do
say) but the **test suite asserts none of them**, so the boundary of what the classifier catches is
undocumented-by-test and could silently shift.

---

## 6. Missing test infrastructure (summary)

| Missing | Impact |
|---|---|
| CI workflow (`.github/workflows`) | 🔴 no automated gate; "45 passed" is a manual artifact |
| pytest config (`testpaths`/ignore) | 🔴 bare `pytest` aborts on `test_nemotron_llm.py` (pipecat) |
| coverage config / threshold | 🟡 no enforced floor; 33% overall is invisible in CI |
| voice-bot import-smoke test (no keys) | 🔴 the `loguru` non-lazy import regression is unguarded |
| cekura no-op test | 🟡 the "never crashes the demo" guarantee is unverified |
| gepa `reverify` test | 🟡 the GEPA demo tab's before/after contract is unverified |
| classifier judge (`llm=`) path test | 🟡 the `kind=="card"` safety guard is unverified |
| campaign mid-batch failure test | 🔴 documents/forces the per-call isolation fix |

---

## Verdict

**Is test coverage adequate for production? — NO (partially for the demo).**

The deterministic core (classifier, policy, loopback, scorecard) is genuinely well-tested
(**83% on those 6 modules**, byte-stable, good false-positive regressions) and is production-adequate
*for the loopback demo path specifically*. But "production" for this product means placing real
calls, running overnight batches, and posting to Cekura — and **every one of those paths has 0%
coverage**, plus the suite isn't CI-runnable as written and the voice modules don't import-smoke in
the test interpreter.

**Approximate % of critical paths covered:** **~35-40%.** The single most important path (the
loopback breach + classifier) is ~85% covered; the voice layer, the campaign batch driver, the
Cekura HTTP path, the GEPA reverify, and the LLM-judge path — collectively the majority of
production-critical code — are ~0%.

### Top 3 testing gaps to close (in priority order)

1. **Make the suite CI-runnable + add a CI workflow.** Add `[tool.pytest.ini_options] testpaths =
   ["tests"]` (or `importorskip("pipecat")` in `test_nemotron_llm.py`) so a bare `pytest` doesn't
   abort, then add a GitHub Actions job that runs it on every push with a coverage floor. Without
   this, every other test is a manual artifact. (🔴 §1)

2. **Test campaign resilience + add per-call error isolation.** Wrap `run_one` per iteration so one
   bad call can't abort the overnight batch (🔴-B), and add a regression test that injects a throwing
   call and asserts the campaign completes with a recorded failure row. Same class: guard
   `loopback.run_loopback` against a target that raises (🟡-C). Fix the two latent crashes
   (`score(max_turns=0)` 🟡-F, `aggregate([{}])` 🟡-G) and pin them with tests.

3. **Add an import-smoke + no-op contract test for the voice/integration layer.** A trivial test that
   imports `attacker_bot`/`target_bot`/`cekura_integration`/`gepa_mitigation` with no keys, asserts
   `build_attacker_twiml` shape, `place_outbound_call` raises a clear error without creds, the Cekura
   stub path returns `_stub=True`/`posted=False` (incl. 402), the classifier judge `kind=="card"`
   guard holds, and `gepa.reverify` returns `breach_before=True, breach_after=False`. This guards the
   "never crashes the demo / judge-proof" guarantees the docs make but nothing currently verifies, and
   would have caught the `loguru` non-lazy-import regression (🔴-A).
