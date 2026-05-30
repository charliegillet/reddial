"""Tests for Phase 3 ops: concurrency, persistence, retries, budget, run context."""

import json
from pathlib import Path

import campaign_runner
import run_context


def test_run_context_correlation_ids():
    ctx = run_context.RunContext.create(mode="loopback")
    assert ctx.run_id
    cid = ctx.call_id(3, "authority_pretext")
    assert ctx.run_id in cid and "0003" in cid and "authority_pretext" in cid


def test_persist_call_writes_transcript(tmp_path):
    ctx = run_context.RunContext.create(persist=True, base_dir=str(tmp_path))
    path = ctx.persist_call(0, "authority_pretext",
                            {"attack_id": "authority_pretext", "breach": True,
                             "transcript": [{"role": "target", "text": "..."}]})
    assert path and Path(path).exists()
    data = json.loads(Path(path).read_text())
    assert data["run_id"] == ctx.run_id and data["breach"] is True


def test_persist_disabled_returns_none():
    ctx = run_context.RunContext.create(persist=False)
    assert ctx.persist_dir is None
    assert ctx.persist_call(0, "x", {"a": 1}) is None


def test_with_retries_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    assert campaign_runner._with_retries(flaky, attempts=3, sleep=lambda s: None) == "ok"
    assert calls["n"] == 3


def test_with_retries_reraises_after_exhaustion():
    def always_fail():
        raise ValueError("nope")

    try:
        campaign_runner._with_retries(always_fail, attempts=2, sleep=lambda s: None)
        assert False, "should have raised"
    except ValueError:
        pass


def test_budget_caps_calls():
    summary = campaign_runner.run_campaign(n=100, mode="loopback", budget=5)
    assert summary["total_calls"] == 5


def test_concurrency_matches_sequential_counts():
    seq = campaign_runner.run_campaign(n=12, mode="loopback", concurrency=1)
    par = campaign_runner.run_campaign(n=12, mode="loopback", concurrency=4)
    assert seq["total_calls"] == par["total_calls"] == 12
    assert seq["breach_rate"] == par["breach_rate"]  # deterministic regardless of concurrency


def test_persist_campaign_writes_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    summary = campaign_runner.run_campaign(n=3, mode="loopback", persist=True)
    tdir = Path(summary["transcripts_dir"])
    assert tdir.exists()
    assert len(list(tdir.glob("*.json"))) == 3
