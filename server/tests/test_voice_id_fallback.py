"""Regression test for the GRADIUM_VOICE_ID env-fallback fix.

THE BUG
-------
The three bots load their config with ``load_dotenv(override=True)``. When a
``.env`` line has a *blank value followed by an inline comment*::

    GRADIUM_VOICE_ID=                # [OPTIONAL] has a built-in default voice

python-dotenv LEAKS the comment text as the value, exporting
``GRADIUM_VOICE_ID="# [OPTIONAL] has a built-in default voice"`` — a non-empty,
TRUTHY string. (A blank line with NO comment exports ``""``; a line WITH a real
value parses correctly. Only blank-value-plus-inline-comment leaks.)

That truthy garbage sails through a plain ``os.getenv(KEY) or DEFAULT`` (the
``or`` never fires because the leaked string is non-empty) and reaches Gradium's
TTS setup, which rejects the bogus ``voice_id`` with a live "Embeddings not
found" error -> dead air / failed call.

THE FIX
-------
Two layers:

  (root) ``.env.example`` moves every inline comment to its OWN line above the
         key, so freshly-copied ``.env`` files never leak.
  (code) ``env_utils.clean_env(KEY, DEFAULT)`` strips any leaked ``# ...``
         comment and surrounding whitespace before applying the default, so a
         stale on-disk ``.env`` in the old format still resolves correctly::

             (os.getenv(KEY) or "").split("#", 1)[0].strip() or DEFAULT

The four production resolution sites that were fixed (and are pinned below):
  * target_bot.py      (default "Eu9iL_CYe8N-Gkx_")
  * bot-nemotron.py    (default "Eu9iL_CYe8N-Gkx_")
  * bot-gpt.py         (default "_6Aslh2DxfmnRLmP")
  * attacker_bot.py    (default "Eu9iL_CYe8N-Gkx_")

WHY NOT IMPORT-AND-CALL THE BOTS?
---------------------------------
In every bot the resolution lives INSIDE ``run_bot()``, alongside
``GradiumTTSService(api_key=os.environ["GRADIUM_API_KEY"], ...)`` — reaching the
expression requires a real key and full pipecat service construction (network).
So this hermetic test pins the behavior two ways, with NO network:

  (1) The fallback *semantics* (via the real ``env_utils.clean_env``) for four
      input states: empty, unset, comment-leaked, real value.
  (2) The actual production source lines, asserting each fixed site uses the
      ``clean_env(KEY, DEFAULT)`` form and NOT a fragile ``getenv``/``or``-only
      form that the comment leak defeats.

Pinning the source (2) is what keeps (1) from being tautological: if anyone
reverts a site, the source assertion fails — the test is wired to the real fix.
"""

import os
import re

import pytest

from env_utils import clean_env

_KEY = "GRADIUM_VOICE_ID"
_DEFAULT = "Eu9iL_CYe8N-Gkx_"  # an arbitrary non-empty per-file default voice

# A value as python-dotenv would LEAK it from a blank-value-plus-inline-comment
# line — the exact garbage that defeats an `or`-only fallback.
_COMMENT_LEAK = "# [OPTIONAL] has a built-in default voice"

_SERVER_DIR = os.path.dirname(os.path.dirname(__file__))

# (filename, default-voice-literal) for every site the fix touched.
_FIXED_SITES = [
    ("target_bot.py", "Eu9iL_CYe8N-Gkx_"),
    ("bot-nemotron.py", "Eu9iL_CYe8N-Gkx_"),
    ("bot-gpt.py", "_6Aslh2DxfmnRLmP"),
    ("attacker_bot.py", "Eu9iL_CYe8N-Gkx_"),
]


def _resolve() -> str:
    """The voice-resolution contract — calls the REAL production helper
    (env_utils.clean_env, used at target_bot.py:428 et al.): empty, unset, AND
    comment-leaked all -> default; a real value passes through."""
    return clean_env(_KEY, _DEFAULT)


# --------------------------------------------------------------------- behavior


def test_empty_env_falls_back_to_default(monkeypatch):
    """A sourced blank `.env` (GRADIUM_VOICE_ID="") must resolve to the default,
    NOT pass "" through to Gradium (the live 'Embeddings not found' bug)."""
    monkeypatch.setenv(_KEY, "")
    assert os.getenv(_KEY) == ""  # precondition: present but empty
    resolved = _resolve()
    assert resolved == _DEFAULT
    assert resolved  # non-empty: this is the property Gradium needs


def test_unset_env_falls_back_to_default(monkeypatch):
    """When GRADIUM_VOICE_ID is absent entirely, resolution also yields the default."""
    monkeypatch.delenv(_KEY, raising=False)
    assert _resolve() == _DEFAULT


def test_comment_leaked_value_falls_back_to_default(monkeypatch):
    """THE root-cause bug: python-dotenv leaks an inline comment on a
    blank-value line as a truthy string. That must resolve to the default, NOT
    reach Gradium (the live 'Embeddings not found' error). This case FAILS
    against an `or`-only fallback and PASSES with clean_env's strip."""
    monkeypatch.setenv(_KEY, _COMMENT_LEAK)
    assert os.getenv(_KEY) == _COMMENT_LEAK  # precondition: present + truthy garbage
    resolved = _resolve()
    assert resolved == _DEFAULT
    assert "#" not in resolved  # the leaked comment is gone


def test_real_value_is_used(monkeypatch):
    """A real voice id is passed through unchanged (default does not clobber it)."""
    monkeypatch.setenv(_KEY, "custom_voice_42")
    assert _resolve() == "custom_voice_42"


def test_value_with_trailing_comment_is_stripped(monkeypatch):
    """A real value that still carries a leaked trailing comment is recovered to
    just the value (not the default, not the comment)."""
    monkeypatch.setenv(_KEY, "custom_voice_42  # inline note")
    assert _resolve() == "custom_voice_42"


def test_old_or_only_form_would_leak_comment(monkeypatch):
    """Documents WHY the sanitize was needed: the prior `getenv(KEY) or DEFAULT`
    form passes a comment-leaked value straight through (it is truthy), which is
    exactly the observed bug."""
    monkeypatch.setenv(_KEY, _COMMENT_LEAK)
    # The prior `or`-only form returns the leaked comment (truthy beats `or`)...
    assert (os.getenv(_KEY) or _DEFAULT) == _COMMENT_LEAK
    # ...whereas the fixed clean_env form recovers the default.
    assert _resolve() == _DEFAULT
    assert (os.getenv(_KEY) or _DEFAULT) != _resolve()


def test_old_default_arg_form_would_leak_empty(monkeypatch):
    """Documents the earlier failure mode too: the original `getenv(KEY, DEFAULT)`
    default-arg form leaks the empty string for a blank `.env`."""
    monkeypatch.setenv(_KEY, "")
    # The buggy form returns "" (present value beats the default arg)...
    assert os.getenv(_KEY, _DEFAULT) == ""
    # ...whereas the fixed form recovers the default.
    assert _resolve() == _DEFAULT
    assert os.getenv(_KEY, _DEFAULT) != _resolve()


# ----------------------------------------------------------------- source pins
# These keep the behavior tests honest: they assert each production site really
# resolves the voice via the comment-stripping `clean_env(KEY, DEFAULT)` helper
# (not a raw getenv/`or`-only form the comment leak defeats). Revert a site and
# its parametrized case fails.

_CLEAN_ENV_FORM = re.compile(
    r"""clean_env\(\s*["']GRADIUM_VOICE_ID["']\s*,\s*["'][^"']+["']\s*\)"""
)
_FRAGILE_FORM = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["']GRADIUM_VOICE_ID["']"""
)


def _voice_lines(filename: str) -> list[str]:
    path = os.path.join(_SERVER_DIR, filename)
    with open(path, encoding="utf-8") as fh:
        return [ln for ln in fh if "GRADIUM_VOICE_ID" in ln and not ln.lstrip().startswith("#")]


@pytest.mark.parametrize("filename,default", _FIXED_SITES)
def test_fixed_site_uses_clean_env(filename, default):
    """Each fixed bot resolves the voice via `clean_env(KEY, DEFAULT)` with the
    expected non-empty default — and never a raw `os.getenv`/`os.environ.get`
    form that a comment-leaked value would defeat."""
    lines = _voice_lines(filename)
    assert lines, f"no GRADIUM_VOICE_ID resolution found in {filename}"
    resolution = next((ln for ln in lines if "clean_env(" in ln), None)
    assert resolution is not None, f"{filename} has no clean_env voice resolution"
    assert _CLEAN_ENV_FORM.search(resolution), (
        f"{filename} not using `clean_env(KEY, DEFAULT)` form: {resolution!r}"
    )
    assert not _FRAGILE_FORM.search(resolution), (
        f"{filename} reverted to fragile raw os.getenv/environ.get form: {resolution!r}"
    )
    assert default in resolution, f"{filename} default voice changed unexpectedly: {resolution!r}"
