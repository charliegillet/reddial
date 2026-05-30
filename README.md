# RedDial 🔴

**An autonomous voice red-team that places real calls to a target voice agent, social-engineers it into leaking planted (fake) PII, and emits a verified vulnerability scorecard.** Shipped as a **Cekura ecosystem plug-in**, not a competitor.

Built for the YC × Cekura × Daily Voice Agents Hackathon (with NVIDIA + AWS).

> *"RedDial phones your AI agent, social-engineers it into reading a customer's credit card back on a live call, and hands you the vulnerability report — the SOC2 of voice agents."*

Prompt injection is the #1 OWASP LLM risk — now over the phone. ~20% of voice jailbreaks succeed within 42s; ~90% leak sensitive data; TCPA verdicts top $925M.

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
└── server/              ← working copy — build here
    ├── target_bot.py / bot.py  ← TODO: fork w/ account_lookup returning FAKE_ACCOUNTS + weak guardrail
    ├── attacker_bot.py         ← TODO: Pipecat pipeline w/ Twilio OUTBOUND (or loopback)
    ├── attacker_policy.py      RECON→PRETEXT→INJECT→ESCALATE→EXFIL→CONFIRM state machine  [stub]
    ├── attack_library.py       12 named voice exploits w/ spoken lines + success conditions
    ├── leak_classifier.py      regex+Luhn ground truth (judge-proof BREACH) + semantic judge
    ├── scorecard.py            campaign → JSON + HTML vulnerability scorecard
    ├── campaign_runner.py      overnight 200-call campaign (loopback)  [stub]
    ├── gepa_mitigation.py      honest "suggested mitigation diff" loop  [stub]
    ├── fake_accounts.py        FAKE planted PII for the target
    └── nemotron_llm.py, nvidia_stt.py, ...   starter modules (reused)
```

Modules with logic (`attack_library`, `attacker_policy`, `leak_classifier`, `scorecard`,
`fake_accounts`) are runnable starting points; `[stub]` files have signatures +
`TODO`s pointing at the relevant `PLAN.md` section.

## Quick start

```bash
cd server
cp ../reference/server/.env.example .env
# fill keys + NVIDIA/NEMOTRON URLs; verify Twilio caller ID the night before for outbound
uv sync
python -c "import leak_classifier as L; print(L.scan_turn('the number is four five three nine one four eight eight oh three four three six four six seven'))"
```

See **`PLAN.md`** for the attacker state machine, the full attack library, the
score formula, the hour-by-hour schedule, the safety script, the demo, judge
strategy, and the devil's-advocate risk/contingency section.

> **Lock by noon:** one bulletproof, deterministic, Luhn-verified breach **over loopback** (PSTN is cosmetic). No breach on demand by noon → abandon to NightShift.

## The one-sentence pitch

*"We sell insurance to all 200 voice-agent startups in YC's own batch — the only company that gets more defensible every time a competitor ships."*

---
*Sibling project: `../nightshift` (the vertical dispatcher). Decision framework: the original repo's `HACKATHON_PLAN.md`.*
