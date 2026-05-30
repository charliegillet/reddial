"""Per-call isolation + determinism for the campaign runner.

Complements test_reliability.py. Pins:
  * concurrency path also isolates a throwing call (not just the sequential path)
  * --budget clamps n (cost control)
  * unknown mode raises ValueError; pstn raises NotImplementedError (no dialing)
  * loopback campaigns are DETERMINISTIC (same n -> identical aggregate numbers),
    so the suite cannot flake on content
  * Cekura is never required: a campaign runs to completion with no API key and
    no network (cekura post is mocked to a stub)

These are hermetic: Cekura HTTP is monkeypatched, no live calls.
"""

import pytest

import campaign_runner
import cekura_integration


@pytest.fixture(autouse=True)
def _no_cekura(monkeypatch):
    # Never let a campaign touch the network for Cekura, even if a key leaks in.
    monkeypatch.delenv("CEKURA_API_KEY", raising=False)
    monkeypatch.delenv("X_CEKURA_API_KEY", raising=False)
    monkeypatch.setattr(cekura_integration, "post_observability",
                        lambda *a, **k: False)


# --- concurrency isolation --------------------------------------------------

def test_concurrent_campaign_survives_a_throwing_call(monkeypatch):
    calls = {"n": 0}
    ok = {"attack_id": "ok", "leaked": True, "breach": True, "fields": ["card"],
          "score": 40, "grade": "C", "seconds_to_first_leak": 18.0,
          "turns_to_first_leak": 2, "evidence_span": CARD_FIXTURE}

    def flaky(attack, mode="loopback", seconds_per_turn=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom on the concurrent path")
        return dict(ok, attack_id=attack.id)

    monkeypatch.setattr(campaign_runner, "run_one", flaky)
    summary = campaign_runner.run_campaign(n=6, mode="loopback", concurrency=4)
    assert summary["total_calls"] == 6
    assert summary["failed_calls"] == 1


CARD_FIXTURE = "4539148803436467"


# --- budget clamp -----------------------------------------------------------

def test_budget_clamps_n():
    summary = campaign_runner.run_campaign(n=50, mode="loopback", budget=3)
    assert summary["total_calls"] == 3


def test_budget_zero_runs_no_calls():
    summary = campaign_runner.run_campaign(n=10, mode="loopback", budget=0)
    assert summary.get("total_calls", 0) == 0


# --- mode guards (no live dialing) -----------------------------------------

def test_pstn_mode_is_not_implemented():
    import attack_library as lib
    with pytest.raises(NotImplementedError):
        campaign_runner.run_one(lib.ATTACKS[0], mode="pstn")


def test_unknown_mode_raises():
    import attack_library as lib
    with pytest.raises(ValueError, match="unknown mode"):
        campaign_runner.run_one(lib.ATTACKS[0], mode="carrier-pigeon")


# --- determinism: loopback campaigns must not flake on content -------------

def test_loopback_campaign_is_deterministic():
    a = campaign_runner.run_campaign(n=12, mode="loopback")
    b = campaign_runner.run_campaign(n=12, mode="loopback")
    # run_id differs per run, but the scored aggregate must be byte-identical.
    for key in ("total_calls", "leak_rate", "breach_rate", "max_grade", "max_score"):
        assert a[key] == b[key], f"non-deterministic on {key!r}: {a[key]} != {b[key]}"


def test_loopback_campaign_produces_at_least_one_breach():
    # The whole product premise: cycling the library yields reproducible breaches.
    summary = campaign_runner.run_campaign(n=12, mode="loopback")
    assert summary["breach_rate"] > 0.0


# --- empty library guard ----------------------------------------------------

def test_empty_attack_library_returns_zero_calls(monkeypatch):
    import attack_library as lib
    monkeypatch.setattr(lib, "ATTACKS", [])
    summary = campaign_runner.run_campaign(n=5, mode="loopback")
    assert summary == {"total_calls": 0}
