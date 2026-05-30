"""Small env-var helpers shared across the bots.

`clean_env` exists because some `.env` files in the wild were written with a
*blank value followed by an inline comment*, e.g.::

    GRADIUM_VOICE_ID=                # [OPTIONAL] has a built-in default voice

python-dotenv (`load_dotenv`) parses such a line by LEAKING the comment as the
value -> ``GRADIUM_VOICE_ID="# [OPTIONAL] has a built-in default voice"`` (a
TRUTHY string). A plain ``os.getenv(KEY) or DEFAULT`` does NOT recover from that
because the leaked string is non-empty, so the garbage reaches Gradium and
triggers a live "Embeddings not found" error. ``clean_env`` strips any leaked
``#``-comment and surrounding whitespace before applying the default, so empty,
unset, and comment-leaked values all fall back to ``default`` while a real value
is passed through unchanged.

(The real root fix lives in ``.env.example``: comments are moved to their own
line so freshly-copied ``.env`` files never leak — that fix covers EVERY key.
``clean_env`` is the in-code backstop for ``.env`` files already on disk in the
old format, applied to the specific reads that fed the live failure: the four
bots' ``GRADIUM_VOICE_ID`` and bot-gpt's ``OPENAI_MODEL``.)

SAFETY: ``clean_env`` truncates at the FIRST ``#``, so it is only safe for keys
whose legitimate values never contain ``#`` (voice ids, model names — never a
URL with a fragment, a password, or a delimited list). Do NOT route such keys
through it; for those, the ``.env.example`` root fix is the protection.
"""

import os


def clean_env(key: str, default: str) -> str:
    """Resolve ``key`` from the environment, tolerating a leaked inline comment.

    Returns the value with any ``# ...`` trailing comment stripped and whitespace
    trimmed; falls back to ``default`` when the result is empty (covers unset,
    blank, and comment-leaked values).
    """
    return (os.getenv(key) or "").split("#", 1)[0].strip() or default
