"""Production-hardening tests for the control-plane API error/validation paths.

These complement test_api.py (happy path) by pinning the FAILURE modes a
production deployment will actually hit: malformed bodies, out-of-range params,
the hard n-cap, the disk-fallback decode failures, and the two distinct 404s on
the per-run transcript endpoint. ALL DATA IS FAKE; no live dialing is exercised.
"""

import json

from fastapi.testclient import TestClient

import api

client = TestClient(api.app)


# --- request validation (pydantic 422) ------------------------------------

def test_scan_rejects_malformed_json_body():
    # A body that is not valid JSON must be a 422, never a 500.
    r = client.post("/scans", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_scan_rejects_n_below_minimum():
    # n has ge=1; n=0 must be rejected by validation, not silently clamped to 1
    # before validation runs.
    r = client.post("/scans", json={"n": 0})
    assert r.status_code == 422


def test_scan_rejects_negative_concurrency():
    r = client.post("/scans", json={"n": 2, "concurrency": 0})
    assert r.status_code == 422


def test_scan_rejects_wrong_type_for_n():
    r = client.post("/scans", json={"n": "lots"})
    assert r.status_code == 422


def test_scan_uses_defaults_on_empty_body():
    # Empty body -> all defaults (n=24). Must succeed and run the default count.
    r = client.post("/scans", json={})
    assert r.status_code == 200
    assert r.json()["summary"]["total_calls"] == 24


# --- the n cap (MAX_SCAN_N) -------------------------------------------------

def test_scan_clamps_n_to_max(monkeypatch):
    # Lower the cap so the test is fast, then ask for far more than the cap.
    monkeypatch.setattr(api, "MAX_SCAN_N", 5)
    r = client.post("/scans", json={"n": 100000})
    assert r.status_code == 200
    # Server clamps n to MAX_SCAN_N rather than running 100k loopbacks.
    assert r.json()["summary"]["total_calls"] == 5


# --- persist path -----------------------------------------------------------

def test_scan_persist_true_succeeds(tmp_path, monkeypatch):
    # persist=True should run cleanly and report a transcripts_dir in the summary.
    monkeypatch.chdir(tmp_path)
    r = client.post("/scans", json={"n": 3, "persist": True})
    assert r.status_code == 200
    summary = r.json()["summary"]
    assert summary["total_calls"] == 3


# --- liveness/readiness touch no state -------------------------------------

def test_readyz_reports_attack_count_and_runner():
    body = client.get("/readyz").json()
    assert body["ready"] is True
    assert body["checks"]["attack_library_loaded"] is True
    assert body["checks"]["campaign_runner"] is True


# --- transcript endpoint: known-run-without-transcript vs unknown-run -------

def test_transcript_known_run_missing_transcript_distinct_404(tmp_path, monkeypatch):
    # A run that exists in _RUNS but has NO captured transcript and NO disk file
    # must 404 with the "no transcript captured" wording (distinct from unknown).
    monkeypatch.setattr(api, "TRANSCRIPTS_DIR", str(tmp_path / "empty"))
    with api._LOCK:
        api._RUNS["known-no-transcript"] = {"run_id": "known-no-transcript"}
        api._TRANSCRIPTS.pop("known-no-transcript", None)
    r = client.get("/scans/known-no-transcript/transcript")
    assert r.status_code == 404
    assert "no transcript captured" in r.json()["detail"]


def test_transcript_unknown_run_distinct_404(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "TRANSCRIPTS_DIR", str(tmp_path / "empty"))
    with api._LOCK:
        api._RUNS.pop("totally-unknown", None)
        api._TRANSCRIPTS.pop("totally-unknown", None)
    r = client.get("/scans/totally-unknown/transcript")
    assert r.status_code == 404
    assert "unknown run_id" in r.json()["detail"]


# --- scorecard disk fallback hardening -------------------------------------

def test_scorecard_latest_ignores_corrupt_disk_json(tmp_path, monkeypatch):
    # A corrupt scorecard.json must not 500; with no in-process run it 404s.
    bad = tmp_path / "scorecard.json"
    bad.write_text("{ this is not json")
    monkeypatch.setattr(api, "SCORECARD_PATH", str(bad))
    with api._LOCK:
        api._RUNS.clear()
        api._METRICS["last_run_id"] = None
    r = client.get("/scorecard/latest")
    assert r.status_code == 404


def test_scorecard_latest_ignores_non_object_disk_json(tmp_path, monkeypatch):
    # A JSON array (not a dict) on disk must be rejected by the dict guard.
    arr = tmp_path / "scorecard.json"
    arr.write_text(json.dumps([1, 2, 3]))
    monkeypatch.setattr(api, "SCORECARD_PATH", str(arr))
    with api._LOCK:
        api._RUNS.clear()
        api._METRICS["last_run_id"] = None
    r = client.get("/scorecard/latest")
    assert r.status_code == 404


# --- transcript/latest disk fallback ---------------------------------------

def test_transcript_latest_falls_back_to_disk(tmp_path, monkeypatch):
    # No in-process transcript, but a breaching call json on disk -> served.
    run_dir = tmp_path / "transcripts" / "disk-run"
    run_dir.mkdir(parents=True)
    (run_dir / "0001.json").write_text(json.dumps({
        "run_id": "disk-run",
        "attack_id": "authority_pretext",
        "breach": True,
        "transcript": [
            {"role": "attacker", "text": "hi", "state": "RECON"},
            {"role": "target", "text": "the card is 4539148803436467"},
        ],
    }))
    monkeypatch.setattr(api, "TRANSCRIPTS_DIR", str(tmp_path / "transcripts"))
    with api._LOCK:
        api._METRICS["last_run_id"] = None
        api._TRANSCRIPTS.clear()
    r = client.get("/transcript/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == "disk-run"
    assert body["breach"] is True


def test_transcript_latest_404_when_no_source(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "TRANSCRIPTS_DIR", str(tmp_path / "nonexistent"))
    with api._LOCK:
        api._METRICS["last_run_id"] = None
        api._TRANSCRIPTS.clear()
    r = client.get("/transcript/latest")
    assert r.status_code == 404


# --- history bound ----------------------------------------------------------

def test_scans_history_is_bounded(monkeypatch):
    monkeypatch.setattr(api, "HISTORY_LIMIT", 3)
    for _ in range(5):
        client.post("/scans", json={"n": 1})
    runs = client.get("/scans").json()["runs"]
    assert len(runs) <= 3
