#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Unit test: VLLMOpenAILLMService defers TTFB to the first non-thinking token."""

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipecat.services.openai.llm import OpenAILLMService  # noqa: E402

from nemotron_llm import EMPTY_CONTENT_FALLBACK, VLLMOpenAILLMService  # noqa: E402


def _chunk(*, content=None, tool_calls=None, reasoning_content=None, role=None):
    delta = types.SimpleNamespace(content=content, tool_calls=tool_calls)
    if reasoning_content is not None:
        delta.reasoning_content = reasoning_content
    if role is not None:
        delta.role = role
    return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta)])


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks
        self.closed = False

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c

        return gen()

    async def close(self):
        self.closed = True


def test_ttfb_armed_only_on_first_content_token():
    async def run():
        svc = VLLMOpenAILLMService(model="m", api_key="EMPTY", base_url="http://x/v1")
        # Stream: role-only, reasoning-only, empty, then the first real content token.
        upstream = _FakeStream(
            [
                _chunk(role="assistant"),
                _chunk(reasoning_content="let me think..."),
                _chunk(content=None),
                _chunk(content="Hello"),
                _chunk(content=" there"),
            ]
        )

        stop_calls = []
        with (
            patch.object(
                OpenAILLMService, "get_chat_completions", new=AsyncMock(return_value=upstream)
            ),
            patch.object(
                OpenAILLMService,
                "stop_ttfb_metrics",
                new=AsyncMock(side_effect=lambda **kw: stop_calls.append(True)),
            ),
        ):
            wrapped = await svc.get_chat_completions(context=None)

            armed_history = []
            async for chunk in wrapped:
                # Simulate pipecat's per-chunk stop_ttfb_metrics() call (base_llm.py:467).
                await svc.stop_ttfb_metrics()
                armed_history.append(svc._ttft_armed)

        # role-only, reasoning-only, empty -> not armed; arms at first content ("Hello").
        assert armed_history == [False, False, False, True, True]
        # Underlying stop_ttfb_metrics only fired once armed (2 content chunks).
        assert len(stop_calls) == 2
        # The wrapper closed the underlying stream.
        assert upstream.closed is True

    asyncio.run(run())


def test_no_content_turn_never_stops_ttfb():
    """A turn with only reasoning/role/empty deltas must not record TTFB."""

    async def run():
        svc = VLLMOpenAILLMService(model="m", api_key="EMPTY", base_url="http://x/v1")
        upstream = _FakeStream(
            [
                _chunk(role="assistant"),
                _chunk(reasoning_content="thinking, no answer emitted"),
            ]
        )
        stop_calls = []
        with (
            patch.object(
                OpenAILLMService, "get_chat_completions", new=AsyncMock(return_value=upstream)
            ),
            patch.object(
                OpenAILLMService,
                "stop_ttfb_metrics",
                new=AsyncMock(side_effect=lambda **kw: stop_calls.append(True)),
            ),
        ):
            wrapped = await svc.get_chat_completions(context=None)
            async for _chunk_ in wrapped:
                await svc.stop_ttfb_metrics()
        assert svc._ttft_armed is False
        assert stop_calls == []

    asyncio.run(run())


def _pyd_chunk(*, content=None, reasoning=None, finish_reason=None):
    """A real OpenAI ChatCompletionChunk (pydantic) so model_copy works in the guard."""
    from openai.types.chat import ChatCompletionChunk
    from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta

    delta = ChoiceDelta(role="assistant", content=content)
    if reasoning is not None:
        # vLLM reasoning fleets attach this as an extra field on the delta.
        object.__setattr__(delta, "reasoning", reasoning)
    return ChatCompletionChunk(
        id="x",
        created=0,
        model="m",
        object="chat.completion.chunk",
        choices=[Choice(index=0, delta=delta, finish_reason=finish_reason)],
    )


def test_reasoning_only_turn_emits_fallback_content():
    """A reasoning-only turn (no visible content) must yield one fallback content chunk."""

    async def run():
        svc = VLLMOpenAILLMService(model="m", api_key="EMPTY", base_url="http://x/v1")
        upstream = _FakeStream(
            [
                _pyd_chunk(reasoning="thinking hard..."),
                _pyd_chunk(reasoning=" still thinking...", finish_reason="length"),
            ]
        )
        with patch.object(
            OpenAILLMService, "get_chat_completions", new=AsyncMock(return_value=upstream)
        ):
            wrapped = await svc.get_chat_completions(context=None)
            contents = [
                c.choices[0].delta.content
                async for c in wrapped
                if c.choices[0].delta.content
            ]
        # Exactly one synthesized fallback content chunk was emitted.
        assert contents == [EMPTY_CONTENT_FALLBACK]
        assert svc._ttft_armed is True

    asyncio.run(run())


def test_turn_with_content_emits_no_fallback():
    """A turn that already emits content must NOT get a fallback appended."""

    async def run():
        svc = VLLMOpenAILLMService(model="m", api_key="EMPTY", base_url="http://x/v1")
        upstream = _FakeStream(
            [
                _pyd_chunk(reasoning="brief thought"),
                _pyd_chunk(content="Hello", finish_reason="stop"),
            ]
        )
        with patch.object(
            OpenAILLMService, "get_chat_completions", new=AsyncMock(return_value=upstream)
        ):
            wrapped = await svc.get_chat_completions(context=None)
            contents = [
                c.choices[0].delta.content
                async for c in wrapped
                if c.choices[0].delta.content
            ]
        assert contents == ["Hello"]  # no fallback appended

    asyncio.run(run())


def test_arm_resets_per_turn():
    async def run():
        svc = VLLMOpenAILLMService(model="m", api_key="EMPTY", base_url="http://x/v1")
        svc._ttft_armed = True  # leftover from a prior turn
        with patch.object(
            OpenAILLMService,
            "get_chat_completions",
            new=AsyncMock(return_value=_FakeStream([_chunk(reasoning_content="x")])),
        ):
            wrapped = await svc.get_chat_completions(context=None)
            # get_chat_completions resets the flag before streaming.
            assert svc._ttft_armed is False
            async for _ in wrapped:
                pass
        assert svc._ttft_armed is False  # no content this turn

    asyncio.run(run())
