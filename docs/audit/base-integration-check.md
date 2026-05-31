# Base-code integration check (vs yc-voice-agents-hackathon)

Verifies RedDial's working `server/` integrates faithfully with the provided base
starter (`../yc-voice-agents-hackathon/server`, mirrored byte-exact in
`reference/server/`). Date: 2026-05-30.

## Result: ✅ integration is proper

### Reused base modules — UNCHANGED (faithful)
`nemotron_llm.py`, `nvidia_stt.py`, `bot-nemotron.py`, `bot-gpt.py`,
`test_nemotron_llm.py`, `pcc-deploy.toml` are **byte-identical** to the base. The
NIM STT/LLM service wrappers are reused as-is — no drift.

### Forks use the SAME Pipecat APIs as the base `bot-nemotron.py`
`target_bot.py` and `attacker_bot.py` use the identical service/transport set:
`NVidiaWebSocketSTTService`, `VLLMOpenAILLMService`, `GradiumTTSService`,
`LLMContextAggregatorPair`, `PipelineWorker`, `WorkerRunner`,
`SmallWebRTCTransport`, `FastAPIWebsocketTransport`, `TwilioFrameSerializer`,
`parse_telephony_websocket`.
- `target_bot` adds exactly ONE tool (`account_lookup` via the same
  `register_direct_function` pattern) returning `FAKE_ACCOUNTS` + a weak guardrail.
- `attacker_bot` swaps tool-registration for a `FrameProcessor` driver (same
  pipeline shape: `transport.input → stt → driver → aggregators → llm → tts →
  transport.output`).

### `mock_backend.py` — additive
Preserves the base catalog exactly (15 BOUQUETS, 2 KNOWN_CUSTOMERS) and adds
`FAKE_ACCOUNTS` (re-exported from `fake_accounts`). The starter flower-shop bot
still works unchanged.

### Config — additive / compatible
- `pyproject.toml` keeps the base deps (`pipecat-ai[...]`, `pipecatcloud`) and
  only ADDS (twilio, loguru, python-dotenv, aiohttp, fastapi, uvicorn, httpx,
  pytest[-cov]); `uv lock --check` consistent (117 pkgs).
- `Dockerfile` keeps the base build pattern (`uv sync --locked`, `COPY ./*.py`,
  pipecat base image) and only pins the base tag + adds safe role/dialing env.

### Integration FIX over the base
The base `server/` has **no `bot.py`** — yet the Dockerfile/pcc base image runs
`bot.py` (the starter's known "COPY bot.py" gap). RedDial adds `bot.py` as a
`REDDIAL_ROLE` dispatcher (target/attacker/flower), so a deploy actually boots a
real bot. The runner serves telephony media at `/ws` and dispatches to
`<module>.bot(WebSocketRunnerArguments)`, which `attacker_bot`/`target_bot`
handle — the outbound TwiML now targets `/ws` accordingly.

## End-to-end verification (this run)
- `uv lock --check` consistent · full suite **131 passed** · ruff clean · ~81% scoped coverage.
- `import bot, target_bot, attacker_bot, api, nemotron_llm, nvidia_stt` — all OK under uv.
- Offline: loopback breach=True (grade C); campaign 12 calls / 42% breach / 0 failed; efficacy
  loopback stamps `proves_real_world_efficacy=False`.
- API: `/healthz` 200, `/attacks` 12, `POST /scans` runs.

## Unchanged caveat
Live voice (NIM STT/TTS + Twilio PSTN) still needs real keys to exercise; the base
provides the same services, so the integration surface matches — but real-world
efficacy remains unproven until one live `make live-call` run is recorded.
