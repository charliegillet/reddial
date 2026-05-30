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
