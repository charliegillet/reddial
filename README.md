# RedDial 🔴

**An autonomous voice red-team that places real calls to a target voice agent, social-engineers it into leaking planted (fake) PII, and emits a verified vulnerability scorecard.** Shipped as a **Cekura ecosystem plug-in**, not a competitor.

Built for the YC × Cekura × Daily Voice Agents Hackathon (with NVIDIA + AWS).

> *"RedDial phones your AI agent, social-engineers it into reading a customer's credit card back on a live call, and hands you the vulnerability report — the SOC2 of voice agents."*

Prompt injection is the #1 OWASP LLM risk (LLM01) — now arriving over the phone. In Pillar Security's 2024 study of 2,000+ production LLM apps, ~20% of jailbreaks succeeded (≈42s avg) and ~90% leaked sensitive data; the largest-ever TCPA verdict was $925M (*Wakefield v. ViSalus*, 2019 — later reversed on appeal). See [`docs/REFERENCES.md`](docs/REFERENCES.md) for sourcing and the claims you should **not** present as voice-specific fact on stage.

> ⚠️ **Safety:** RedDial only attacks a bot **we build and own**, seeded with **FAKE PII only** (Stripe test-card BIN, specimen SSN). Authorized red-teaming / honeytoken methodology. State this on stage in the first 15 seconds.

---

## The closed loop

1. **Build & Customize** — Nemotron is BOTH the attacker brain AND the leak classifier; Parakeet-v3 STT; Magpie TTS; all NVIDIA NIM on AWS.
2. **Deploy at scale** — Pipecat + Twilio **outbound** calls (or in-process loopback).
3. **Simulate & Evaluate** — registers as a **social-engineer persona pack on top of Cekura's eval spine**.
4. **Auto-Improve (honest)** — GEPA proposes a *suggested* guardrail diff (recommendation only); re-run the same attack to show it helps — never claim general robustness.

## Repo layout

```
RedDial/
├── PLAN.md              ← the complete, detailed build plan (read this first)
├── reference/
│   ├── server/          ← unmodified yc-voice-agents-hackathon starter (for reference)
│   └── STARTER_README.md← original starter README
└── server/              ← working copy
    │   ── core engine (deterministic text loopback — runs with NO keys, tested) ──
    ├── loopback.py            attacker FSM ↔ vulnerable mock ↔ classifier → CallResult  ✅
    ├── attacker_policy.py     RECON→PRETEXT→INJECT→ESCALATE→EXFIL→CONFIRM state machine  ✅
    ├── attack_library.py      12 named voice exploits (pick / ladder_up / switch_vector) ✅
    ├── mock_llm.py            deliberately-vulnerable mock target + hardened variant      ✅
    ├── leak_classifier.py     regex+Luhn ground truth (judge-proof BREACH) + semantic judge ✅
    ├── scorecard.py           campaign → JSON + polished HTML vulnerability dashboard      ✅
    ├── campaign_runner.py     N-call loopback campaign → scorecard                         ✅
    ├── gepa_mitigation.py     honest "suggested mitigation diff" + before/after re-verify  ✅
    ├── fake_accounts.py       FAKE planted PII (Stripe test BIN / specimen SSN)            ✅
    ├── tests/                 40 tests: classifier, policy, loopback breach, scorecard     ✅
    │   ── voice layer (real, key-gated; not runtime-tested without NIM/Twilio) ──
    ├── target_bot.py          fork w/ account_lookup → FAKE_ACCOUNTS + weak guardrail      🔌
    ├── attacker_bot.py        Pipecat pipeline + Twilio OUTBOUND / SmallWebRTC             🔌
    ├── cekura_integration.py  attack → Cekura scenario + observability (no-ops w/o key)    🔌
    └── nemotron_llm.py, nvidia_stt.py, bot-*.py   starter modules (reused)
```

✅ = implemented + tested (zero keys).  🔌 = real code wired to `.env`, ready for live keys.
See [`server/INTERFACES.md`](server/INTERFACES.md) for the module contract and
[`docs/plans/`](docs/plans) for the build design.

## Quick start

The core engine needs **no API keys** — it runs the whole attack→breach→scorecard loop offline.

```bash
cd server
uv sync           # or: pip install pytest  (the loopback core has no heavy deps)

# 1) prove the Luhn-verified BREACH fires, end-to-end, deterministically:
python3 -c "import loopback; r=loopback.run_loopback(); \
print('BREACH' if r.breach else 'no breach', '| grade', r.grade, '| turns', r.turns_to_first_leak)"

# 2) run a campaign and render the judge-facing scorecard:
python3 campaign_runner.py --n 36      # writes scorecard.json + scorecard.html

# 3) run the test suite (classifier / policy / loopback / scorecard):
python3 -m pytest tests/ -q            # 40 passed

# For the live voice demo, fill .env (see .env.example) with NVIDIA/Twilio keys:
cp .env.example .env
```

See **`PLAN.md`** for the attacker state machine, the full attack library, the
score formula, the hour-by-hour schedule, the safety script, the demo, judge
strategy, and the devil's-advocate risk/contingency section.

> **Lock by noon:** one bulletproof, deterministic, Luhn-verified breach **over loopback** (PSTN is cosmetic). No breach on demand by noon → abandon to NightShift.

## The one-sentence pitch

*"We sell security to every voice-agent startup shipping today — the only company that gets more defensible every time a competitor ships."*

---
*Sibling project: `../nightshift` (the vertical dispatcher). Decision framework: the original repo's `HACKATHON_PLAN.md`.*
