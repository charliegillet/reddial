"""Tests for the RedDial control-plane API (server/api.py).

Uses fastapi.testclient.TestClient against the offline loopback. ALL DATA IS
FAKE — no live dialing is ever exercised here.
"""

from fastapi.testclient import TestClient

import api

client = TestClient(api.app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == api.VERSION


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
