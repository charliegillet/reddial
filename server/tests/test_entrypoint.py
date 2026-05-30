"""Tests for the deploy entrypoint dispatcher (BLOCKER 1) and dial-volume guard.

These cover the gap that let the dispatcher ship broken: nothing imported `bot`
or exercised `_load_role_module` for the target/attacker roles (which raised
UnboundLocalError). Needs loguru/pipecat (the voice deps) — skipped on a bare
interpreter, runs in CI under `uv`.
"""

import types

import pytest

pytest.importorskip("loguru")  # voice layer dep; present under `uv`, skip on bare py
import bot  # noqa: E402


def test_default_role_is_target():
    import importlib as _il

    # default with no env
    import os
    os.environ.pop("REDDIAL_ROLE", None)
    assert bot._resolve_role() == "target"
    assert bot.DEFAULT_ROLE == "target"


def test_unknown_role_falls_back_to_target(monkeypatch):
    monkeypatch.setenv("REDDIAL_ROLE", "bogus")
    assert bot._resolve_role() == "target"


@pytest.mark.parametrize("role,expected_module", [
    ("target", "target_bot"),
    ("attacker", "attacker_bot"),
])
def test_load_role_module_does_not_raise_unbound(role, expected_module, monkeypatch):
    """Regression for the UnboundLocalError: the target/attacker branches must
    reach importlib.import_module without the function-local-shadowing crash."""
    captured = {}

    def fake_import(name):
        captured["name"] = name
        return types.SimpleNamespace(bot=lambda *a, **k: None)

    monkeypatch.setattr(bot.importlib, "import_module", fake_import)
    mod = bot._load_role_module(role)          # must NOT raise UnboundLocalError
    assert captured["name"] == expected_module
    assert hasattr(mod, "bot")


def test_callguard_wired_into_dial_path(monkeypatch):
    """place_outbound_call must reserve a CallGuard slot (volume control), not
    just check the destination gate."""
    import attacker_bot
    monkeypatch.setenv("REDDIAL_DIALING_ENABLED", "1")
    monkeypatch.setenv("REDDIAL_DIAL_ALLOWLIST", "+14155551234")
    monkeypatch.setenv("REDDIAL_MAX_CALLS", "1")
    # Twilio creds present so we get past the config check to the dial attempt.
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("VERIFIED_CALLER_ID", "+14155550000")
    monkeypatch.setenv("PUBLIC_HOST", "example.ngrok.io")
    attacker_bot._DIAL_GUARD = None  # reset singleton for the test

    # Stub the actual Twilio client so no network call happens.
    import sys

    import safety_controls
    fake_twilio = types.ModuleType("twilio")
    fake_rest = types.ModuleType("twilio.rest")

    class _Client:
        def __init__(self, *a, **k): pass
        class calls:  # noqa: N801
            @staticmethod
            def create(**k): return types.SimpleNamespace(sid="CA_test")
    fake_rest.Client = _Client
    fake_twilio.rest = fake_rest
    monkeypatch.setitem(sys.modules, "twilio", fake_twilio)
    monkeypatch.setitem(sys.modules, "twilio.rest", fake_rest)

    # First call allowed (cap=1); second must trip the CallGuard, proving it's wired.
    attacker_bot.place_outbound_call("+14155551234", consent=True)
    with pytest.raises(safety_controls.DialingNotAllowed, match="cap"):
        attacker_bot.place_outbound_call("+14155551234", consent=True)
