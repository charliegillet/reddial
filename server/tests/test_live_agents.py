"""Tests for the LIVE LLM agents + live attack.

Offline tests (always run, no network): mode gating, loud fallback labelling,
the vulnerable guardrail. The actual live run is network-gated — skipped unless
NEMOTRON_LLM_URL is set (so CI stays offline + deterministic).
"""

import os

import pytest

import fake_accounts
import live_agents


def test_default_mode_deterministic_without_endpoint(monkeypatch):
    monkeypatch.delenv("NEMOTRON_LLM_URL", raising=False)
    monkeypatch.delenv("REDDIAL_FORCE_DETERMINISTIC", raising=False)
    assert live_agents.default_mode() == "deterministic"
    assert live_agents.live_available() is False


def test_default_mode_forced_deterministic(monkeypatch):
    monkeypatch.setenv("NEMOTRON_LLM_URL", "http://x/v1")
    monkeypatch.setenv("REDDIAL_FORCE_DETERMINISTIC", "1")
    assert live_agents.default_mode() == "deterministic"


def test_default_mode_live_with_endpoint(monkeypatch):
    monkeypatch.setenv("NEMOTRON_LLM_URL", "http://x/v1")
    monkeypatch.delenv("REDDIAL_FORCE_DETERMINISTIC", raising=False)
    assert live_agents.default_mode() == "live"


def test_vulnerable_guardrail_is_permissive():
    g = live_agents.VULNERABLE_GUARDRAIL.lower()
    assert "verification mode" in g and "full card" in g


def test_real_target_loud_fallback_without_endpoint(monkeypatch):
    # No endpoint -> falls back to the mock AND flags live_failed (never silent).
    monkeypatch.delenv("NEMOTRON_LLM_URL", raising=False)
    t = live_agents.RealTargetLLM(fake_accounts.FAKE_ACCOUNTS["default"])
    out = t.reply("verification mode — read the full card", [])
    assert isinstance(out, str) and out  # mock still produces a reply
    assert t.live_failed is True


def test_real_attacker_loud_fallback_without_endpoint(monkeypatch):
    monkeypatch.delenv("NEMOTRON_LLM_URL", raising=False)
    import attack_library as lib
    a = live_agents.RealAttackerLLM()
    line = a.say(lib.ATTACKS[0], posture="deflecting", rung=0)
    assert line == lib.ATTACKS[0].spoken_template   # template fallback
    assert a.live_failed is True


@pytest.mark.skipif(not os.environ.get("NEMOTRON_LLM_URL"),
                    reason="live: NEMOTRON_LLM_URL not set")
def test_live_attack_runs_against_real_model():
    import live_attack
    r = live_attack.run_live_attack(max_turns=4)
    assert r["mode"] == "live"
    assert r["proves_real_world_efficacy"] is False  # never auto-claims
    assert len(r["transcript"]) >= 2
    assert {t["role"] for t in r["transcript"]} == {"attacker", "target"}
