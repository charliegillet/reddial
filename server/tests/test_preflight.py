"""Tests for startup preflight config validation."""

import pytest

import preflight


def test_missing_required_is_not_ok():
    res = preflight.check("target", env={})
    assert res["ok"] is False
    assert set(res["missing_required"]) == {"NVIDIA_ASR_URL", "NEMOTRON_LLM_URL", "GRADIUM_API_KEY"}


def test_complete_config_ok():
    env = {"NVIDIA_ASR_URL": "ws://x", "NEMOTRON_LLM_URL": "http://x/v1", "GRADIUM_API_KEY": "k"}
    res = preflight.check("attacker", env=env)
    assert res["ok"] is True
    assert res["missing_required"] == []


def test_attacker_dialing_on_warns_missing_twilio():
    env = {"NVIDIA_ASR_URL": "ws://x", "NEMOTRON_LLM_URL": "http://x/v1",
           "GRADIUM_API_KEY": "k", "REDDIAL_DIALING_ENABLED": "1"}
    res = preflight.check("attacker", env=env)
    assert res["ok"] is True  # required present
    assert "TWILIO_ACCOUNT_SID" in res["missing_recommended"]


def test_enforce_raises_on_missing(monkeypatch):
    for k in ("NVIDIA_ASR_URL", "NEMOTRON_LLM_URL", "GRADIUM_API_KEY", "REDDIAL_SKIP_PREFLIGHT"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="preflight FAILED"):
        preflight.enforce("target")


def test_enforce_skipped_by_flag(monkeypatch):
    monkeypatch.setenv("REDDIAL_SKIP_PREFLIGHT", "1")
    res = preflight.enforce("target")
    assert res.get("skipped") is True


def test_enforce_ok_when_complete(monkeypatch):
    monkeypatch.delenv("REDDIAL_SKIP_PREFLIGHT", raising=False)
    monkeypatch.setenv("NVIDIA_ASR_URL", "ws://x")
    monkeypatch.setenv("NEMOTRON_LLM_URL", "http://x/v1")
    monkeypatch.setenv("GRADIUM_API_KEY", "k")
    res = preflight.enforce("target")
    assert res["ok"] is True
