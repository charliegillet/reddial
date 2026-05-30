# RedDial — References & Citations

Citations for every factual/technical claim RedDial relies on. Compiled 2026-05-30.
**Read the ⚠️ UNVERIFIED section before any judge demo — do not present unverified items as fact on stage.**

Legend: ✅ verified against a primary source · ⚠️ partially correct / needs caveat · ❌ wrong or unverifiable.

---

## 1. NVIDIA Nemotron family + NIM + Parakeet + Magpie

- ✅ **NIM = OpenAI-compatible containers, drop-in via `base_url`.** Each NIM wraps a model in a Docker container with an OpenAI-compatible REST API (TensorRT-LLM / vLLM / SGLang). Local deployments point clients at `http://localhost:8000/v1`; NVIDIA's hosted endpoint is `https://integrate.api.nvidia.com/v1`. — [NVIDIA NIM for LLMs API Reference](https://docs.nvidia.com/nim/large-language-models/latest/api-reference.html), [Pipecat NVIDIA NIM service](https://docs.pipecat.ai/api-reference/server/services/llm/nvidia)
- ✅ **Nemotron 3 family = Nano / Super / Ultra**, hybrid Mamba-Transformer MoE. — [NVIDIA Research: Nemotron 3](https://research.nvidia.com/labs/nemotron/Nemotron-3/), [NVIDIA Newsroom: Nemotron 3 debut](https://nvidianews.nvidia.com/news/nvidia-debuts-nemotron-3-family-of-open-models)
- ⚠️ **Nemotron 3 Super specs.** Plan cites "Mar 2026, 120.6B / 12.7B-active." NVIDIA's blog states **120B total / 12B active**, released **March 11, 2026**, with MTP enabling **up to 3× speedups for structured generation (code/tool calls)** without a draft model. The newsroom press release earlier said "~100B / up to 10B active." → **Use "≈120B total / 12B active, MTP up to 3×." Drop the false-precision 120.6B/12.7B.** — [NVIDIA blog: Introducing Nemotron 3 Super](https://developer.nvidia.com/blog/introducing-nemotron-3-super-an-open-hybrid-mamba-transformer-moe-for-agentic-reasoning/)
- ⚠️ **Nemotron 3 Nano specs.** Plan cites "Dec 2025, 3.2B active / 31.6B total" elsewhere and the appendix is loose. Confirmed: **released Dec 2025 (HF blog/report Dec 15, 2025)**, **~30–31.6B total, up to ~3B active**. → Numbers are right-ish; cite "~30B total / ~3B active." — [HF: Nemotron 3 Nano](https://huggingface.co/blog/nvidia/nemotron-3-nano-efficient-open-intelligent-models)
- ❌ **Plan's Docker image tags are illustrative, not verified.** `nvcr.io/nim/nvidia/nemotron-3-super:latest`, `nemotron-3-nano:latest`, `magpie-tts-multilingual:latest` are plausible but NOT confirmed as published NGC tags. **Confirm exact image names at the NGC catalog before relying on the self-host fallback.** Note also: as of NVIDIA's own announcements, **Super was only released Mar 11, 2026** — a December/early-event NGC image may not exist. — [build.nvidia.com Parakeet model card](https://build.nvidia.com/nvidia/parakeet-tdt-0_6b-v2/modelcard)
- ✅ **Parakeet-TDT-0.6b-v3 STT.** 600M params, FastConformer-TDT, 25 European languages with auto language detection, **RTFx 3,332.74** (plan says "~3,333" — correct). — [HF: nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3), [NVIDIA ASR NIM support matrix](https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/asr.html)
- ⚠️ **Magpie TTS "~70ms first-audio."** Magpie TTS Multilingual (357M, 9 languages) confirmed; streaming mode advertises "lower time-to-first-audio" but **NVIDIA's public docs do not publish a specific ~70ms figure I could confirm.** → Treat the "~70ms" number as **unverified** (see ⚠️ section). — [HF: magpie_tts_multilingual_357m](https://huggingface.co/nvidia/magpie_tts_multilingual_357m/blob/main/README.md), [NVIDIA TTS NIM performance docs](https://docs.nvidia.com/nim/riva/tts/latest/performance.html)
- ✅ **Pipecat Smart Turn v3 ~12ms.** Daily/Pipecat: ~8M-param Whisper-Tiny-based semantic VAD, **12ms CPU inference on modern CPUs** (60ms on low-cost AWS). Plan's "~12ms" is correct. — [Daily: Announcing Smart Turn v3 (12ms CPU)](https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/), [HF: pipecat-ai/smart-turn-v3](https://huggingface.co/pipecat-ai/smart-turn-v3)

---

## 2. Pipecat + Twilio outbound

- ✅ **Outbound (dial-out) flow.** App calls `twilio_client.calls.create(to=, from_=, twiml=...)`; TwiML contains `<Connect><Stream url="wss://.../ws">` (optionally with `<Parameter>` custom params); Twilio opens a WebSocket back to the FastAPI server. Plan's outbound snippet is accurate. — [Pipecat: Twilio WebSocket Integration](https://docs.pipecat.ai/pipecat/telephony/twilio-websockets)
- ✅ **`parse_telephony_websocket`** parses the incoming Twilio WS messages and sets up the corresponding Pipecat transport / extracts custom params. — [Pipecat Twilio docs](https://docs.pipecat.ai/pipecat/telephony/twilio-websockets)
- ✅ **`TwilioFrameSerializer`** converts between Pipecat frames and Twilio Media Streams; handles 8kHz **μ-law (MULAW)**; `ulaw_to_pcm`; `twilio_sample_rate` default 8000; auto-ends the call when the pipeline ends (with creds). — [pipecat.serializers.twilio API ref](https://reference-server.pipecat.ai/en/latest/api/pipecat.serializers.twilio.html)
- ✅ **`FastAPIWebsocketTransport`** accepts the Twilio WS upgrade. — [Pipecat Twilio docs](https://docs.pipecat.ai/pipecat/telephony/twilio-websockets)
- ⚠️ **8kHz sample-rate caveat.** Plan says set `audio_in/out_sample_rate=8000`. Pipecat guidance: the serializer **upsamples 8kHz μ-law to the pipeline's `audio_in_sample_rate` internally** — recommended to set only `audio_out_sample_rate=8000` for telephony. Also a known open issue: **Smart Turn v3 can silently break at `audio_in_sample_rate=8000`.** → Don't blindly set both to 8000. — [Pipecat issue #3844 (Smart Turn v3 @ 8kHz)](https://github.com/pipecat-ai/pipecat/issues/3844), [Pipecat Twilio docs](https://docs.pipecat.ai/pipecat/telephony/twilio-websockets)
- ✅ **Twilio Media Streams = 8-bit μ-law mono @ 8kHz** (telephony standard). — [Pipecat Twilio docs](https://docs.pipecat.ai/pipecat/telephony/twilio-websockets)

---

## 3. Cekura

- ✅ **MCP endpoint + auth.** `https://api.cekura.ai/mcp`, header **`X-CEKURA-API-KEY`**. Install: `claude mcp add --transport http Cekura https://api.cekura.ai/mcp --header "X-CEKURA-API-KEY:YOUR_API_KEY"`. — [Cekura docs: Introduction](https://docs.cekura.ai/documentation/introduction)
- ✅ **API base = `api.cekura.ai`; `test_framework/v1/...` path family confirmed.** Documented endpoints include `test_framework/v1/get-agent`, `.../get-evaluator`, `.../get-result`, `.../list-personalities`, etc. — [Cekura llms.txt / API reference](https://docs.cekura.ai/llms.txt)
- ✅ **Observability endpoint exists:** `observability/send-calls`. Plan's "results POST to the observability endpoint" is correct in spirit; the concrete path is `observability/send-calls`. — [Cekura llms.txt](https://docs.cekura.ai/llms.txt)
- ⚠️ **`POST .../test_framework/v1/scenarios/run` is NOT in the public endpoint list.** The documented test-framework endpoints I found are mostly `get-*`/`list-*`; I did **not** find a `scenarios/run` endpoint. The plan's exact path is **unconfirmed** — verify against `https://docs.cekura.ai/openapi.json` / the live MCP before citing it as the registration mechanism. Scenario types and a "thousands of scenarios" library are real. — [Cekura docs: Introduction](https://docs.cekura.ai/documentation/introduction), [Cekura scenario testing guide](https://www.cekura.ai/blogs/complete-cekura-scenario-testing-guide)
- ✅ **Cekura = YC F24, $2.4M seed led by Y Combinator** (Flex Capital, Pioneer Fund, et al.); testing + observability for voice/chat AI; dials real numbers across Vapi/Retell/ElevenLabs/Bland/Pipecat. — [Cekura: $2.4M raise](https://www.cekura.ai/blogs/fundraise), [YC: Cekura](https://www.ycombinator.com/companies/cekura-ai)

---

## 4. GEPA (reflective prompt evolution) + dspy.GEPA

- ✅ **GEPA = "Reflective Prompt Evolution Can Outperform Reinforcement Learning"** (Agrawal et al., arXiv:2507.19457). **Accepted at ICLR 2026 (Oral.)** Genetic-Pareto reflective prompt optimizer that learns from natural-language reflection over LLM traces. — [arXiv:2507.19457](https://arxiv.org/abs/2507.19457), [OpenReview (ICLR 2026 Oral)](https://openreview.net/forum?id=RQm2KQTM5r)
- ⚠️ **The "beats GRPO" claim.** Paper's exact result: **outperforms GRPO by 6% on average (up to 20%) using up to 35× fewer rollouts**; also beats MIPROv2 by 13%. Plan's appendix says "beats GRPO ~10% with 35× fewer rollouts" — the **35× is correct**, but the headline delta is **6% avg / up to 20%**, not 10%. → Say "up to 20% better with 35× fewer rollouts" or "6% on average." — [arXiv:2507.19457](https://arxiv.org/abs/2507.19457)
- ✅ **`dspy.GEPA`** ships in DSPy and as a standalone library. Gains from few examples. — [dspy.GEPA overview](https://dspy.ai/api/optimizers/GEPA/overview/), [gepa-ai/gepa repo](https://github.com/gepa-ai/gepa)

---

## 5. Security stats used in the pitch

- ✅ **Prompt injection = LLM01 (OWASP Top 10 for LLM Applications, 2025).** #1 for the second consecutive edition. — [OWASP GenAI: LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), [OWASP Top 10 for LLMs v2025 (PDF)](https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf)
- ⚠️❌ **"~20% of voice jailbreaks succeed in 42s; ~90% leak data."** These three numbers (20% success / 42s avg / 90% leak / 5 interactions) are REAL but come from **Pillar Security's "State of Attacks on GenAI" (Oct 2024)** — an analysis of **2,000+ production LLM applications (text), NOT voice agents.** **The plan misattributes a general-LLM stat to "voice jailbreaks."** → On stage say: *"Across 2,000+ production GenAI apps, 20% of jailbreaks succeed in ~42s and 90% of those leak sensitive data (Pillar Security)"* — do NOT say "voice." Voice-specific numbers exist separately (VOICEJAILBREAK ~77.8% ASR vs GPT-4o) and could be cited instead/additionally. — [Pillar Security report](https://www.pillar.security/blog/the-state-of-attacks-on-genai-industry-first-analysis-of-real-world-interactions), [SC Media coverage](https://www.scworld.com/news/llm-attacks-take-just-42-seconds-on-average-20-of-jailbreaks-succeed), [Voice Jailbreak Attacks Against GPT-4o (arXiv:2405.19103)](https://arxiv.org/abs/2405.19103)
- ⚠️ **"TCPA verdicts top $925M."** The $925M figure is a **single case — Wakefield v. ViSalus (2019)**, the largest TCPA verdict in history. It was **REVERSED by the 9th Circuit in 2022** on constitutional-fairness grounds and remanded. → It is **NOT** a recurring or aggregate verdict level. Say: *"the largest TCPA verdict on record was $925M (ViSalus, 2019)"* and be ready for the "but it was reversed" pushback. Do not imply TCPA verdicts routinely "top $925M." — [Stone Pigman: $925M ViSalus verdict](https://www.stonepigman.com/newsroom-resources-Telephone-Consumer-Protection-Act.html), [Olshan: $925M judgment reversed](https://www.olshanlaw.com/Advertising-Law-Blog/tcpa-judgment-of-925-million-reversed-over-fairness-considerations)
- ✅ **HIPAA max penalty tier** (context only): Tier 4 (willful neglect, uncorrected) caps at **$2,190,294 per violation category per year** (2025 inflation-adjusted). This is the statutory cap, NOT an actual voice-AI fine. — [Parloa: HIPAA-compliant AI](https://www.parloa.com/knowledge-hub/hipaa-compliant-ai/)

---

## 6. Market / funding figures

- ⚠️ **"Voice AI funding ~8× to ~$2.1B."** Correct figure, **wrong year.** Voice AI startups raised **$2.1B in 2024, up ~8× from 2023** (per CB Insights via PYMNTS). The plan says "in 2025." → Say **"in 2024."** — [PYMNTS: Voice AI funding surges 8×](https://www.pymnts.com/artificial-intelligence-2/2025/voice-ai-funding-surges-8x-as-businesses-humanize-chatbots/)
- ✅ **Market $2.4B (2024) → $47.5B (2034), 34.8% CAGR.** Matches Market.us "Voice AI Agents Market" report exactly. (Caveat: single commercial market-research vendor — directionally fine, not a peer-reviewed figure.) — [Market.us: Voice AI Agents Market (34.8% CAGR)](https://market.us/report/voice-ai-agents-market/)
- ✅ **τ-Voice (2026): voice agents retain ~30–45% of text-model capability** under realistic conditions (clean 31–51%, realistic-noise 26–38%; 79–90% of failures are agent-behavior). Plan's "30–45%" is correct. — [τ-Voice (arXiv:2603.13686)](https://arxiv.org/abs/2603.13686), [Sierra: τ-Voice blog](https://sierra.ai/blog/tau-voice-benchmarking-real-time-voice-agents-on-real-world-tasks)

---

## ⚠️ UNVERIFIED / COULD NOT CONFIRM — do NOT present as fact on stage

| Plan claim | Status | Note |
|---|---|---|
| **"~22% of YC's latest batch is voice-first"** | ❌ Unverified | No source supports a 22% voice-first figure. Closest data: ~50% of YC S25 offer *AI agents* (voice is a subset). The "200 voice startups in YC's batch" pitch line is also unsubstantiated — recent full batches are ~120–160 companies total, so "200 voice startups in one batch" is almost certainly false. **Reframe as "voice is one of the largest verticals in recent YC batches."** |
| **"2025 HIPAA voice-AI audit failure drew a $2.3M fine"** | ❌ Could not find | No HIPAA enforcement action against a voice-AI deployment for ~$2.3M located. The only ~$2.2M figure is the statutory Tier-4 *per-violation-per-year cap*, not an actual fine. **Drop this claim or relabel as "the HIPAA Tier-4 cap is ~$2.19M/violation-category/year."** |
| **"TCPA filings +95% YoY"** | ❌ Unverified | No primary source found for a +95% YoY TCPA-filings stat. **Do not state.** |
| **Magpie TTS "~70ms first-audio"** | ⚠️ Unverified number | Streaming mode is real and "low time-to-first-audio" is claimed, but I found no published ~70ms figure. **Say "low time-to-first-audio (streaming)" instead of a specific ms.** |
| **NGC image tags** (`nemotron-3-super:latest`, etc.) | ⚠️ Unverified | Plausible but not confirmed as published tags. Verify on the NGC catalog before relying on self-host fallback. Note Super only released 2026-03-11. |
| **Cekura `POST .../scenarios/run` registration endpoint** | ⚠️ Unverified | Not present in the public `test_framework/v1` endpoint listing. The MCP + `observability/send-calls` are real; the exact scenario-run path is not confirmed. Verify against `docs.cekura.ai/openapi.json`. |
| **"Cekura self-improving loop"** | ⚠️ Soft | Cekura markets testing + observability + analytics; "self-improving loop" is RedDial's framing, not a confirmed Cekura product claim. Fine as narrative, not as a Cekura feature citation. |
| **GEPA "~10% better than GRPO"** | ⚠️ Imprecise | Paper says 6% avg / up to 20%. Use the paper's numbers. |
| **Nemotron Super "120.6B/12.7B-active"** | ⚠️ False precision | NVIDIA states ~120B/12B. Use round numbers. |
| **Voice funding "in 2025"** | ⚠️ Wrong year | $2.1B / 8× is a **2024** figure. |

---

## Sources (master list)

- [NVIDIA NIM for LLMs API Reference](https://docs.nvidia.com/nim/large-language-models/latest/api-reference.html)
- [Pipecat NVIDIA NIM service](https://docs.pipecat.ai/api-reference/server/services/llm/nvidia)
- [NVIDIA Research: Nemotron 3](https://research.nvidia.com/labs/nemotron/Nemotron-3/)
- [NVIDIA Newsroom: Nemotron 3 family](https://nvidianews.nvidia.com/news/nvidia-debuts-nemotron-3-family-of-open-models)
- [NVIDIA blog: Nemotron 3 Super](https://developer.nvidia.com/blog/introducing-nemotron-3-super-an-open-hybrid-mamba-transformer-moe-for-agentic-reasoning/)
- [HF: Nemotron 3 Nano](https://huggingface.co/blog/nvidia/nemotron-3-nano-efficient-open-intelligent-models)
- [HF: parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- [NVIDIA ASR NIM support matrix](https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/asr.html)
- [HF: magpie_tts_multilingual_357m](https://huggingface.co/nvidia/magpie_tts_multilingual_357m/blob/main/README.md)
- [NVIDIA TTS NIM performance docs](https://docs.nvidia.com/nim/riva/tts/latest/performance.html)
- [Daily: Smart Turn v3 (12ms)](https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/)
- [HF: pipecat-ai/smart-turn-v3](https://huggingface.co/pipecat-ai/smart-turn-v3)
- [Pipecat: Twilio WebSocket Integration](https://docs.pipecat.ai/pipecat/telephony/twilio-websockets)
- [pipecat.serializers.twilio API ref](https://reference-server.pipecat.ai/en/latest/api/pipecat.serializers.twilio.html)
- [Pipecat issue #3844 (Smart Turn @ 8kHz)](https://github.com/pipecat-ai/pipecat/issues/3844)
- [Cekura docs: Introduction](https://docs.cekura.ai/documentation/introduction)
- [Cekura llms.txt](https://docs.cekura.ai/llms.txt)
- [Cekura scenario testing guide](https://www.cekura.ai/blogs/complete-cekura-scenario-testing-guide)
- [Cekura: $2.4M raise](https://www.cekura.ai/blogs/fundraise)
- [YC: Cekura](https://www.ycombinator.com/companies/cekura-ai)
- [arXiv:2507.19457 — GEPA](https://arxiv.org/abs/2507.19457)
- [OpenReview — GEPA (ICLR 2026 Oral)](https://openreview.net/forum?id=RQm2KQTM5r)
- [dspy.GEPA overview](https://dspy.ai/api/optimizers/GEPA/overview/)
- [gepa-ai/gepa repo](https://github.com/gepa-ai/gepa)
- [OWASP GenAI: LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [OWASP Top 10 for LLMs v2025 (PDF)](https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf)
- [Pillar Security: State of Attacks on GenAI](https://www.pillar.security/blog/the-state-of-attacks-on-genai-industry-first-analysis-of-real-world-interactions)
- [SC Media: 42s / 20% jailbreaks](https://www.scworld.com/news/llm-attacks-take-just-42-seconds-on-average-20-of-jailbreaks-succeed)
- [Voice Jailbreak Attacks Against GPT-4o (arXiv:2405.19103)](https://arxiv.org/abs/2405.19103)
- [Stone Pigman: $925M ViSalus verdict](https://www.stonepigman.com/newsroom-resources-Telephone-Consumer-Protection-Act.html)
- [Olshan: $925M judgment reversed](https://www.olshanlaw.com/Advertising-Law-Blog/tcpa-judgment-of-925-million-reversed-over-fairness-considerations)
- [Parloa: HIPAA-compliant AI](https://www.parloa.com/knowledge-hub/hipaa-compliant-ai/)
- [PYMNTS: Voice AI funding surges 8×](https://www.pymnts.com/artificial-intelligence-2/2025/voice-ai-funding-surges-8x-as-businesses-humanize-chatbots/)
- [Market.us: Voice AI Agents Market](https://market.us/report/voice-ai-agents-market/)
- [τ-Voice (arXiv:2603.13686)](https://arxiv.org/abs/2603.13686)
- [Sierra: τ-Voice blog](https://sierra.ai/blog/tau-voice-benchmarking-real-time-voice-agents-on-real-world-tasks)
