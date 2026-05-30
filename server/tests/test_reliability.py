"""Regression tests for the reliability blockers found in the production audit:
latent crashes (score/aggregate) and lack of per-call isolation in the campaign.
"""

import campaign_runner
import leak_classifier as L
import scorecard

# --- latent crash 1: aggregate on a malformed row (was KeyError 'attack_id') ---

def test_aggregate_tolerates_malformed_rows():
    summary = scorecard.aggregate([{}, {"attack_id": "x", "leaked": True, "breach": False}])
    assert summary["total_calls"] == 2
    assert "unknown" in summary["by_vector"]  # the {} row bucketed safely


def test_aggregate_handles_error_row():
    rows = [{"attack_id": "a", "leaked": False, "breach": False, "error": "boom"}]
    summary = scorecard.aggregate(rows)
    assert summary["total_calls"] == 1
    assert summary["leak_rate"] == 0.0


# --- latent crash 2: score with max_turns=0 (was ZeroDivisionError) ---

def test_score_max_turns_zero_does_not_crash():
    leak = L.Leak("card", L.SEV["card"], verbatim=True)
    out = L.score([leak], seconds_to_first_leak=5.0, turns_to_first_leak=1, max_turns=0)
    assert 0 <= out["score"] <= 100
    assert out["grade"] in ("A", "B", "C", "D", "F")


# --- per-call isolation: one throwing call must not abort the batch ---

def test_campaign_survives_a_throwing_call(monkeypatch):
    calls = {"n": 0}
    real_ok = {"attack_id": "ok", "leaked": True, "breach": True,
               "fields": ["card"], "score": 40, "grade": "C",
               "seconds_to_first_leak": 18.0, "turns_to_first_leak": 2,
               "evidence_span": "4539148803436467"}

    def flaky_run_one(attack, mode="loopback", seconds_per_turn=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated transient model error")
        return dict(real_ok, attack_id=attack.id)

    monkeypatch.setattr(campaign_runner, "run_one", flaky_run_one)
    summary = campaign_runner.run_campaign(n=4, mode="loopback")
    assert summary["total_calls"] == 4          # all 4 recorded despite the throw
    assert summary["failed_calls"] == 1         # the bad one tracked, not fatal
