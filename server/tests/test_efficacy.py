"""Tests for the efficacy harness — especially that it does NOT overclaim.

A loopback breach must be stamped as NOT proof of real-world efficacy, and the
live path must go through the fail-closed dialing gate.
"""

import pytest

import efficacy_run


def test_loopback_artifact_is_honest_about_provenance():
    art = efficacy_run.run_loopback_efficacy(attack_id="authority_pretext")
    assert art["mode"] == "loopback"
    assert art["target_kind"] == "self-authored-mock"
    assert art["proves_real_world_efficacy"] is False   # the critical anti-overclaim
    assert art["breach"] is True                          # pipeline still works
    assert "NOT real-world efficacy" in art["note"] or "not" in art["note"].lower()


def test_write_artifact(tmp_path):
    art = efficacy_run.run_loopback_efficacy()
    path = efficacy_run.write_artifact(art, out_dir=str(tmp_path))
    assert path.endswith(".json")


def test_live_mode_blocked_by_safety_gate_by_default(monkeypatch):
    pytest.importorskip("loguru")  # live path imports attacker_bot (voice dep)
    # No kill-switch / allowlist / consent -> the gate must refuse.
    for k in ("REDDIAL_DIALING_ENABLED", "REDDIAL_DIAL_ALLOWLIST"):
        monkeypatch.delenv(k, raising=False)
    import safety_controls
    try:
        efficacy_run.run_live_efficacy("+14155551234", consent=True)
        assert False, "live efficacy should be refused by the fail-closed gate"
    except safety_controls.DialingNotAllowed:
        pass
