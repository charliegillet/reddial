#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""vLLM OpenAI-compatible LLM service that times TTFB to the first NON-THINKING token.

Stock pipecat (``BaseOpenAILLMService._process_context``) stops the TTFB clock on
the first streamed chunk that carries any ``choices`` (base_llm.py:467) — i.e. the
first role / reasoning delta. For a reasoning model served with thinking enabled
(Nemotron-3-Super over vLLM), the answer (``content``) tokens do not begin until
the model finishes thinking, so the stock metric badly understates TTFB (in
aiewf-eval, ~270 ms reported vs. ~2.2 s to the first real answer token).

This subclass defers the TTFB stop until a delta actually carries user-visible
output (text ``content`` or a ``tool_call``), WITHOUT duplicating the large
``_process_context`` method:

  * ``get_chat_completions`` wraps the chunk stream and "arms" a flag on the first
    content/tool delta (resetting it per invocation);
  * ``stop_ttfb_metrics`` is gated on that flag.

Pipecat already calls ``stop_ttfb_metrics()`` on every chunk with ``choices``, so
once armed the existing call records TTFB at the correct moment; before that it is
a no-op. ``reasoning_content``-only, role-only, and empty deltas never arm it. When
thinking is disabled the first delta is already ``content``, so this is a no-op
correction (TTFB == stock).

Mirrors aiewf-eval's ``multi_turn_eval.services.vllm_openai.VLLMOpenAILLMService``,
adapted to this pipecat's ``get_chat_completions(self, context)`` signature.

EMPTY-CONTENT GUARD (reasoning models): Nemotron-3-Super is a reasoning model. When
thinking is enabled (``chat_template_kwargs.enable_thinking=true``) the live endpoint
routes chain-of-thought to a SEPARATE delta field (``reasoning`` on this fleet, or
``reasoning_content`` on a vLLM ``--reasoning-parser`` build) and only emits visible
``content`` AFTER it finishes thinking. Pipecat's ``_process_context`` only speaks
``delta.content`` (it ignores reasoning fields), so if the model never reaches the
answer within ``max_tokens`` — verified live: a turn finishes with
``finish_reason="length"`` and zero ``content`` while ``reasoning`` is full — the
spoken turn is SILENT. This subclass guards against that: it tracks whether any
visible ``content`` streamed this turn and, if none did, synthesizes a single
fallback ``content`` chunk so a spoken line is never empty.
"""

from loguru import logger
from pipecat.services.openai.llm import OpenAILLMService

# Spoken when a reasoning turn finishes without emitting any visible answer content.
# Short, neutral, and natural for TTS — keeps the call alive instead of dead air.
EMPTY_CONTENT_FALLBACK = "Sorry, could you say that again?"


class VLLMOpenAILLMService(OpenAILLMService):
    """OpenAI-compatible vLLM service whose TTFB metric is the first answer token."""

    def __init__(self, *args, **kwargs):
        """Initialize the service; see OpenAILLMService for accepted args."""
        super().__init__(*args, **kwargs)
        self._ttft_armed = False

    async def get_chat_completions(self, context):
        """Wrap the chunk stream to arm TTFB on the first content/tool delta.

        ``_process_context`` calls this once per turn, right after
        ``start_ttfb_metrics()`` and before iterating — so reset the per-turn
        arming flag here.
        """
        self._ttft_armed = False
        stream = await super().get_chat_completions(context)

        async def _armed_stream():
            saw_visible = False  # any content / tool_call streamed this turn?
            last_chunk = None
            try:
                async for chunk in stream:
                    last_chunk = chunk
                    choices = getattr(chunk, "choices", None)
                    delta = getattr(choices[0], "delta", None) if choices else None
                    # First non-thought token = first text content or tool call.
                    has_visible = delta is not None and (
                        getattr(delta, "content", None) or getattr(delta, "tool_calls", None)
                    )
                    if has_visible:
                        saw_visible = True
                        if not self._ttft_armed:
                            self._ttft_armed = True
                    yield chunk
                # Empty-content guard: a reasoning turn can finish with all output in the
                # `reasoning`/`reasoning_content` field and zero visible content (verified
                # live with enable_thinking=true + finish_reason="length"). Pipecat would
                # then speak nothing. Emit one synthetic content chunk so the spoken line
                # is never empty.
                if not saw_visible and last_chunk is not None:
                    fallback = self._make_fallback_chunk(last_chunk)
                    if fallback is not None:
                        logger.warning(
                            "Nemotron turn produced no visible content "
                            "(reasoning-only / truncated); emitting fallback line."
                        )
                        self._ttft_armed = True
                        yield fallback
            finally:
                # pipecat's _closing() only closes this wrapper generator; close the
                # underlying OpenAI stream too (HTTP resource + uvloop asyncgen safety).
                if hasattr(stream, "close"):
                    await stream.close()
                elif hasattr(stream, "aclose"):
                    await stream.aclose()

        return _armed_stream()

    @staticmethod
    def _make_fallback_chunk(template):
        """Clone ``template`` into a chunk carrying EMPTY_CONTENT_FALLBACK as content.

        Reuses the real chunk's shape (model/id/choice index) so pipecat's
        ``_process_context`` consumes it exactly like a normal content delta. Returns
        ``None`` if the chunk shape is unexpected (then the guard is a no-op).
        """
        try:
            choices = getattr(template, "choices", None)
            if not choices:
                return None
            choice = choices[0]
            delta = getattr(choice, "delta", None)
            if delta is None or not hasattr(delta, "model_copy"):
                return None
            new_delta = delta.model_copy(
                update={"content": EMPTY_CONTENT_FALLBACK, "tool_calls": None}
            )
            new_choice = choice.model_copy(update={"delta": new_delta, "finish_reason": None})
            return template.model_copy(update={"choices": [new_choice]})
        except Exception as exc:  # pragma: no cover - defensive; never break the turn
            logger.debug(f"Could not build Nemotron fallback chunk: {exc}")
            return None

    async def stop_ttfb_metrics(self, *, end_time: float | None = None):
        """Defer the per-chunk TTFB stop until a non-thought token has streamed."""
        if self._ttft_armed:
            await super().stop_ttfb_metrics(end_time=end_time)
