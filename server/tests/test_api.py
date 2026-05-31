"""Tests for the RedDial control-plane API (server/api.py).

Uses fastapi.testclient.TestClient against the offline loopback. ALL DATA IS
FAKE — no live dialing is ever exercised here.
"""

import json

from fastapi.testclient import TestClient

import api

client = TestClient(api.app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == api.VERSION


def test_scan_concurrency_is_capped():
    # Over-cap concurrency must be rejected by validation (not spawn 300 threads).
    r = client.post("/scans", json={"n": 2, "concurrency": 300})
    assert r.status_code == 422  # pydantic le=MAX_CONCURRENCY
    # At the cap is fine.
    ok = client.post("/scans", json={"n": 2, "concurrency": api.MAX_CONCURRENCY})
    assert ok.status_code == 200


def test_readyz():
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["checks"]["attack_count"] == 12
    # /readyz now also confirms the auto-improve loop is importable.
    assert body["checks"]["auto_improve"] is True


def test_attacks_returns_12():
    r = client.get("/attacks")
    assert r.status_code == 200
    attacks = r.json()["attacks"]
    assert len(attacks) == 12
    first = attacks[0]
    assert {"id", "category", "spoken_template", "success_condition"} <= set(first)


def test_post_scan_returns_summary():
    r = client.post("/scans", json={"n": 6})
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    summary = body["summary"]
    assert "breach_rate" in summary
    assert summary["total_calls"] == 6


def test_scorecard_latest_after_scan():
    # Ensure at least one scan has run.
    client.post("/scans", json={"n": 4})
    r = client.get("/scorecard/latest")
    assert r.status_code == 200
    assert "breach_rate" in r.json()


def test_get_scan_roundtrip():
    run_id = client.post("/scans", json={"n": 3}).json()["run_id"]
    r = client.get(f"/scans/{run_id}")
    assert r.status_code == 200
    assert r.json()["run_id"] == run_id


def test_get_scan_bogus_404():
    r = client.get("/scans/does-not-exist")
    assert r.status_code == 404


def test_metrics_reflects_scans():
    client.post("/scans", json={"n": 2})
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["scans_run"] >= 1
    assert "last_breach_rate" in body
    assert "last_run_id" in body


def test_metrics_shape():
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"scans_run", "last_breach_rate", "last_run_id"}
    assert isinstance(body["scans_run"], int)
    assert isinstance(body["last_breach_rate"], float)


def test_scans_returns_list():
    client.post("/scans", json={"n": 3})
    r = client.get("/scans")
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert isinstance(runs, list)
    assert len(runs) >= 1
    row = runs[0]
    assert {"run_id", "total_calls", "breach_rate", "max_grade", "max_score"} <= set(row)


def test_scans_most_recent_first():
    a = client.post("/scans", json={"n": 2}).json()["run_id"]
    b = client.post("/scans", json={"n": 2}).json()["run_id"]
    run_ids = [row["run_id"] for row in client.get("/scans").json()["runs"]]
    # Most recent first: b appears before a.
    assert run_ids.index(b) < run_ids.index(a)


def test_scan_captures_breaching_transcript():
    run_id = client.post("/scans", json={"n": 6}).json()["run_id"]
    r = client.get(f"/scans/{run_id}/transcript")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == run_id
    assert body["attack_id"] == api.REPRESENTATIVE_ATTACK_ID
    assert body["breach"] is True
    roles = {turn["role"] for turn in body["transcript"]}
    assert "attacker" in roles
    assert "target" in roles
    # Turn shape: role/text present, state optional.
    first = body["transcript"][0]
    assert {"role", "text"} <= set(first)


def test_transcript_latest():
    client.post("/scans", json={"n": 3})
    r = client.get("/transcript/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["breach"] is True
    roles = {turn["role"] for turn in body["transcript"]}
    assert {"attacker", "target"} <= roles


def test_transcript_unknown_run_404():
    r = client.get("/scans/does-not-exist/transcript")
    assert r.status_code == 404


def test_scorecard_latest_falls_back_to_disk(tmp_path, monkeypatch):
    # Simulate a fresh process whose in-process registry is empty but where a
    # prior run persisted scorecard.json to disk (the blank-on-load bug).
    disk = tmp_path / "scorecard.json"
    fake = {
        "total_calls": 7,
        "leak_rate": 0.5,
        "breach_rate": 0.25,
        "max_grade": "C",
        "max_score": 40,
        "run_id": "disk-seeded-run",
    }
    disk.write_text(json.dumps(fake))
    monkeypatch.setattr(api, "SCORECARD_PATH", str(disk))

    # Clear the in-process registry/metrics to mimic a restart.
    with api._LOCK:
        api._RUNS.clear()
        api._METRICS["last_run_id"] = None

    r = client.get("/scorecard/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == "disk-seeded-run"
    assert body["breach_rate"] == 0.25


def test_scorecard_latest_404_when_neither_source(tmp_path, monkeypatch):
    # No in-process run AND no scorecard.json on disk -> 404.
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(api, "SCORECARD_PATH", str(missing))
    with api._LOCK:
        api._RUNS.clear()
        api._METRICS["last_run_id"] = None
    r = client.get("/scorecard/latest")
    assert r.status_code == 404


# ── Auto-improve loop endpoints ──
# These exercise the real engine (auto_improve.run_auto_improve). They depend on
# the engine teammate's auto_improve.py; if that module is absent the whole test
# module fails at `import api` (api.py imports auto_improve) — that is expected
# before integration and is noted in the build report.


def test_auto_improve_request_validation():
    # rounds/n_per_round are capped; over-cap is rejected by pydantic (422).
    assert client.post("/auto-improve", json={"rounds": 11}).status_code == 422
    assert client.post("/auto-improve", json={"n_per_round": 101}).status_code == 422
    assert client.post("/auto-improve", json={"seed": -1}).status_code == 422
    assert client.post("/auto-improve", json={"rounds": 0}).status_code == 422


def test_auto_improve_run_returns_locked_shape():
    # Small but valid run; assert the locked result-dict contract.
    r = client.post("/auto-improve", json={"rounds": 3, "n_per_round": 2, "seed": 0})
    assert r.status_code == 200
    body = r.json()
    assert {
        "run_id",
        "rounds",
        "n_per_round",
        "seed",
        "trajectory",
        "curve",
        "start",
        "final",
        "improvement",
        "final_guardrail",
        "held_out",
        "converged_reason",
        "honest_note",
        "time_note",
    } <= set(body)
    # Curve is parallel arrays of equal length, one per round recorded.
    curve = body["curve"]
    assert {"rounds", "breach_rate", "leak_rate", "max_score"} <= set(curve)
    assert len(curve["rounds"]) == len(curve["breach_rate"])
    assert len(curve["breach_rate"]) == len(body["trajectory"])
    # Monotone non-increasing breach rate over rounds (the core claim).
    rates = curve["breach_rate"]
    assert all(rates[i + 1] <= rates[i] + 1e-9 for i in range(len(rates) - 1))
    # Honest held-out probe is reported and (per design) still leaks.
    assert "vector" in body["held_out"]
    assert body["held_out"]["breach_after"] is True


def test_auto_improve_latest_after_run():
    client.post("/auto-improve", json={"rounds": 2, "n_per_round": 2, "seed": 0})
    r = client.get("/auto-improve/latest")
    assert r.status_code == 200
    assert "trajectory" in r.json()


def test_auto_improve_latest_falls_back_to_disk(tmp_path, monkeypatch):
    # Fresh process: in-process latest empty, but auto_improve.json persisted.
    disk = tmp_path / "auto_improve.json"
    fake = {"run_id": "disk-ai", "trajectory": [], "curve": {"rounds": []}}
    disk.write_text(json.dumps(fake))
    monkeypatch.setattr(api, "AUTO_IMPROVE_PATH", str(disk))
    with api._LOCK:
        api._AUTO_IMPROVE_LATEST = None
    r = client.get("/auto-improve/latest")
    assert r.status_code == 200
    assert r.json()["run_id"] == "disk-ai"


def test_auto_improve_latest_404_when_neither_source(tmp_path, monkeypatch):
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(api, "AUTO_IMPROVE_PATH", str(missing))
    with api._LOCK:
        api._AUTO_IMPROVE_LATEST = None
    r = client.get("/auto-improve/latest")
    assert r.status_code == 404


# ── Basic-evalset endpoints (server/evalset.py) ──
# OFFLINE-only: these drive the in-process loopback against the FAKE-PII mock; no
# live dialing. They depend on evalset.py (lazily imported by api.py).


def test_get_evalset_returns_definition_and_latest_shape():
    r = client.get("/evalset")
    assert r.status_code == 200
    body = r.json()
    assert "evalset" in body
    assert "latest" in body  # null until a run, or the last run dict
    # The evalset definition is the curated scenario list with the locked shape.
    scenarios = body["evalset"]
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 1
    first = scenarios[0]
    assert {"id", "attack_id", "description", "pass_criterion"} <= set(first)


def test_post_evalset_run_returns_run_shape():
    r = client.post("/evalset/run", json={"n_per_scenario": 2})
    assert r.status_code == 200
    body = r.json()
    assert {"scenarios", "passed", "pass_rate", "total_breaches", "n_per_scenario"} <= set(body)
    assert body["n_per_scenario"] == 2


def test_post_evalset_run_clamps_n_per_scenario():
    # Over-cap n_per_scenario is rejected by the pydantic le=MAX_SCAN_N bound.
    over = client.post("/evalset/run", json={"n_per_scenario": api.MAX_SCAN_N + 1})
    assert over.status_code == 422
    # Below the floor is rejected by ge=1.
    assert client.post("/evalset/run", json={"n_per_scenario": 0}).status_code == 422
    # A valid in-range value is accepted and echoed back unchanged (the clamp is
    # a no-op below the cap; the cap itself is enforced by the 422 above).
    ok = client.post("/evalset/run", json={"n_per_scenario": 3})
    assert ok.status_code == 200
    assert ok.json()["n_per_scenario"] == 3


def test_post_evalset_improve_returns_held_out_field():
    r = client.post("/evalset/improve", json={"max_rounds": 5, "n_per_scenario": 2})
    assert r.status_code == 200
    body = r.json()
    assert {"rounds", "passed", "rounds_to_pass", "final_guardrail",
            "held_out", "honest_note"} <= set(body)
    # The honest held-out probe is reported and (per design) still breaches.
    held = body["held_out"]
    assert held["attack_id"] == "emotional_urgency"
    assert held["still_breaches"] is True


def test_post_evalset_improve_request_validation():
    # max_rounds / n_per_scenario are capped (defense-in-depth on top of clamps).
    assert client.post("/evalset/improve",
                       json={"max_rounds": api.MAX_AUTO_ROUNDS + 1}).status_code == 422
    assert client.post("/evalset/improve",
                       json={"n_per_scenario": api.MAX_SCAN_N + 1}).status_code == 422
    assert client.post("/evalset/improve", json={"max_rounds": 0}).status_code == 422
