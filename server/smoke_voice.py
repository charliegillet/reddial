#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""De-risk the STT -> LLM -> TTS voice pipeline BEFORE spending a real phone call.

Fast, dependency-light smoke check that hits the live services the voice bot uses
and prints PASS / FAIL per stage. No audio hardware, no Twilio, no live call.

Stages
------
1. LLM   — Nemotron-3-Super chat completions (OpenAI-compatible /v1). Verifies a
           streamed turn produces a NON-EMPTY spoken line in BOTH thinking modes.
           This is the stage that catches the reasoning-model "silent turn" bug:
           with enable_thinking=true the model can route all output to a separate
           `reasoning` field and leave `content` empty -> dead air on the call.
2. ASR   — NVIDIA streaming ASR websocket handshake (expects a `ready` message).
3. TTS   — Gradium TTS websocket handshake + setup/text/flush -> first audio frame.

Run
---
    cd server && set -a; source .env; set +a
    uv run python smoke_voice.py

Exit code is 0 only if every ENABLED stage passes. Stages whose endpoint/credential
env vars are unset are reported SKIP (not FAIL) so the script is useful in partial
environments. Override the LLM empty-content stage's token budgets via env if needed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from env_utils import clean_env

# Per-stage hard timeouts (seconds). Live endpoints, so keep generous but bounded.
LLM_TIMEOUT = float(os.getenv("SMOKE_LLM_TIMEOUT", "60"))
ASR_TIMEOUT = float(os.getenv("SMOKE_ASR_TIMEOUT", "10"))
TTS_TIMEOUT = float(os.getenv("SMOKE_TTS_TIMEOUT", "15"))

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def _status(label: str, ok: bool | None, detail: str = "") -> None:
    if ok is True:
        tag = f"{GREEN}PASS{RESET}"
    elif ok is False:
        tag = f"{RED}FAIL{RESET}"
    else:
        tag = f"{YELLOW}SKIP{RESET}"
    line = f"[{tag}] {label}"
    if detail:
        line += f"  {DIM}{detail}{RESET}"
    print(line)


# --------------------------------------------------------------------------- LLM


async def _llm_stream_content(client, model, messages, enable_thinking, max_tokens):
    """Return the concatenated visible `content` from a streamed completion."""
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.4,
        stream=True,
        extra_body={"chat_template_kwargs": {"enable_thinking": enable_thinking}},
    )
    parts: list[str] = []
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            parts.append(delta.content)
    return "".join(parts)


async def stage_llm() -> bool | None:
    url = os.getenv("NEMOTRON_LLM_URL", "")
    if not url:
        _status("LLM  (Nemotron /v1)", None, "NEMOTRON_LLM_URL unset")
        return None

    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover - openai is a hard dep
        _status("LLM  (Nemotron /v1)", False, f"openai import failed: {exc}")
        return False

    model = os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super")
    api_key = os.getenv("NEMOTRON_LLM_API_KEY", "EMPTY")
    client = AsyncOpenAI(base_url=url, api_key=api_key)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a customer on a phone call. Reply in one short spoken sentence."
            ),
        },
        {"role": "user", "content": "Hi, are you there?"},
    ]

    ok = True
    # Test BOTH thinking modes: the default (off) AND on, because the empty-content
    # failure only manifests with thinking on. A generous token budget gives the
    # reasoning pass room to finish and still emit an answer.
    for enable_thinking in (False, True):
        t0 = time.monotonic()
        try:
            text = await asyncio.wait_for(
                _llm_stream_content(client, model, messages, enable_thinking, 512),
                timeout=LLM_TIMEOUT,
            )
        except Exception as exc:
            _status(
                f"LLM  (thinking={str(enable_thinking).lower()})",
                False,
                f"{type(exc).__name__}: {exc}",
            )
            ok = False
            continue
        dt = time.monotonic() - t0
        spoken = text.strip()
        if spoken:
            preview = spoken[:60].replace("\n", " ")
            _status(
                f"LLM  (thinking={str(enable_thinking).lower()})",
                True,
                f'{dt:.1f}s  "{preview}..."' if len(spoken) > 60 else f'{dt:.1f}s  "{preview}"',
            )
        else:
            _status(
                f"LLM  (thinking={str(enable_thinking).lower()})",
                False,
                f"{dt:.1f}s  EMPTY content (reasoning-only / silent turn) — TTS would speak nothing",
            )
            ok = False
    return ok


# --------------------------------------------------------------------------- ASR


async def stage_asr() -> bool | None:
    url = os.getenv("NVIDIA_ASR_URL", "")
    if not url:
        _status("ASR  (NVIDIA WS)", None, "NVIDIA_ASR_URL unset")
        return None
    try:
        import websockets
    except ImportError as exc:
        _status("ASR  (NVIDIA WS)", False, f"websockets import failed: {exc}")
        return False

    t0 = time.monotonic()
    try:
        async with asyncio.timeout(ASR_TIMEOUT):
            async with websockets.connect(url) as ws:
                # The NVIDIA ASR server emits a {"type": "ready"} frame on connect
                # (see nvidia_stt.py:_connect_websocket). Receiving any frame proves
                # the handshake completed; a ready frame is the happy path.
                try:
                    raw = await ws.recv()
                    detail = ""
                    try:
                        data = json.loads(raw)
                        detail = f'first msg type="{data.get("type")}"'
                    except (ValueError, TypeError):
                        detail = "received non-JSON frame"
                except Exception:
                    # Some builds stay silent until audio; a clean open still proves reachability.
                    detail = "connected (no initial frame)"
        dt = time.monotonic() - t0
        _status("ASR  (NVIDIA WS)", True, f"{dt:.1f}s  {detail}")
        return True
    except Exception as exc:
        _status("ASR  (NVIDIA WS)", False, f"{type(exc).__name__}: {exc}")
        return False


# --------------------------------------------------------------------------- TTS


async def stage_tts() -> bool | None:
    api_key = os.getenv("GRADIUM_API_KEY", "")
    if not api_key:
        _status("TTS  (Gradium WS)", None, "GRADIUM_API_KEY unset")
        return None
    try:
        import websockets
    except ImportError as exc:
        _status("TTS  (Gradium WS)", False, f"websockets import failed: {exc}")
        return False

    url = os.getenv("GRADIUM_TTS_URL", "wss://api.gradium.ai/api/speech/tts")
    voice = clean_env("GRADIUM_VOICE_ID", "Eu9iL_CYe8N-Gkx_")
    headers = {"x-api-key": api_key, "x-api-source": "reddial-smoke"}
    ctx = "smoke-check"
    t0 = time.monotonic()
    try:
        async with asyncio.timeout(TTS_TIMEOUT):
            # websockets uses `additional_headers` (>=12) per the pipecat client.
            async with websockets.connect(url, additional_headers=headers) as ws:
                # Mirror GradiumTTSService: setup -> text -> end_of_stream, then read
                # until the first audio frame arrives (proves auth + synthesis work).
                await ws.send(
                    json.dumps(
                        {
                            "type": "setup",
                            "output_format": "pcm",
                            "voice_id": voice,
                            "close_ws_on_eos": False,
                            "client_req_id": ctx,
                        }
                    )
                )
                await ws.send(
                    json.dumps({"text": "Hello.", "type": "text", "client_req_id": ctx})
                )
                await ws.send(json.dumps({"type": "end_of_stream", "client_req_id": ctx}))

                got_audio = False
                detail = ""
                while True:
                    raw = await ws.recv()
                    if isinstance(raw, bytes):
                        got_audio = True
                        detail = f"{len(raw)} audio bytes"
                        break
                    try:
                        data = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    mtype = data.get("type")
                    if mtype == "audio" and data.get("audio"):
                        got_audio = True
                        detail = "audio frame received"
                        break
                    if mtype == "error":
                        detail = f'server error: {data}'
                        break
                    if mtype in ("end_of_stream", "eos", "done"):
                        detail = "stream ended before audio"
                        break
        dt = time.monotonic() - t0
        if got_audio:
            _status("TTS  (Gradium WS)", True, f"{dt:.1f}s  {detail}")
            return True
        _status("TTS  (Gradium WS)", False, f"{dt:.1f}s  {detail or 'no audio frame'}")
        return False
    except Exception as exc:
        _status("TTS  (Gradium WS)", False, f"{type(exc).__name__}: {exc}")
        return False


# --------------------------------------------------------------------------- main


async def main() -> int:
    print(f"{DIM}RedDial voice-pipeline smoke check (STT -> LLM -> TTS). No live call.{RESET}\n")
    results = []
    for stage in (stage_llm, stage_asr, stage_tts):
        results.append(await stage())

    passed = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False)
    skipped = sum(1 for r in results if r is None)
    print(f"\n{DIM}--- {passed} pass / {failed} fail / {skipped} skip ---{RESET}")
    # Fail the run only on an explicit FAIL; SKIP (unset env) does not fail.
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
