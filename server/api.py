"""RedDial — control-plane API (FastAPI).

Exposes the OFFLINE red-team harness + results over HTTP so the web dashboard
and monitoring can drive it. Every endpoint is JSON.

SAFETY: this API only ever runs the in-process text loopback against the
FAKE-PII mock target we built and own. ALL DATA IS FAKE (Stripe test BIN /
specimen SSN). It does NOT and CANNOT place live calls — there is no PSTN /
Twilio path here; live dialing stays on the CLI behind the fail-closed safety
gate. Scans run synchronously but ``n`` is hard-capped, and loopback is fast and
deterministic, so requests never block for long.

Contract: server/API_CONTRACT.md (binding).
Run: ``uvicorn api:app``.
"""

from __future__ import annotations

import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import attack_library as lib
import campaign_runner
import scorecard

VERSION = "1.0.0"

# Hard cap on calls per scan. Loopback is fast/deterministic, but we still bound
# request work so the synchronous API never runs unbounded. Per API_CONTRACT.md.
MAX_SCAN_N = 500

# Where the latest aggregate summary is persisted (scorecard.write_json).
SCORECARD_PATH = "scorecard.json"

_DESCRIPTION = (
    "RedDial control-plane API — OFFLINE only. ALL DATA IS FAKE (Stripe test "
    "BIN / specimen SSN against a mock target we own). This API only runs the "
    "in-process text loopback; it does NOT expose live/PSTN dialing. Scans run "
    "synchronously with a hard cap on the number of calls."
)

app = FastAPI(
    title="RedDial Control-Plane API",
    version=VERSION,
    description=_DESCRIPTION,
)

# Permissive CORS for the dashboard. Acceptable here because the API is
# offline-only and serves FAKE data exclusively (no secrets, no live actions).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- state

_LOCK = threading.Lock()
# In-process registry of run summaries, keyed by run_id, for GET /scans/{run_id}.
_RUNS: dict[str, dict] = {}
_METRICS = {
    "scans_run": 0,
    "last_breach_rate": 0.0,
    "last_run_id": None,
}


# --------------------------------------------------------------------------- models

class ScanRequest(BaseModel):
    n: int = Field(default=24, ge=1, description="Number of loopback attack calls.")
    persist: bool = Field(default=False, description="Persist per-call transcripts to disk.")
    concurrency: int = Field(default=1, ge=1, description="Parallel calls (>1 = thread pool).")


class ScanResponse(BaseModel):
    run_id: str
    summary: dict


class AttackOut(BaseModel):
    id: str
    category: str
    spoken_template: str
    success_condition: str


class AttacksResponse(BaseModel):
    attacks: list[AttackOut]


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadyResponse(BaseModel):
    ready: bool
    checks: dict


class MetricsResponse(BaseModel):
    scans_run: int
    last_breach_rate: float
    last_run_id: str | None


# --------------------------------------------------------------------------- routes

@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness — touches no dependencies."""
    return HealthResponse(status="ok", version=VERSION)


@app.get("/readyz", response_model=ReadyResponse)
def readyz() -> ReadyResponse:
    """Readiness — confirms the attack library is loaded and runner is importable."""
    attacks_loaded = bool(getattr(lib, "ATTACKS", None))
    runner_ready = hasattr(campaign_runner, "run_campaign")
    checks = {
        "attack_library_loaded": attacks_loaded,
        "attack_count": len(lib.ATTACKS),
        "campaign_runner": runner_ready,
    }
    return ReadyResponse(ready=attacks_loaded and runner_ready, checks=checks)


@app.get("/attacks", response_model=AttacksResponse)
def attacks() -> AttacksResponse:
    """List the attack library (id / category / template / success condition)."""
    out = [
        AttackOut(
            id=a.id,
            category=a.category,
            spoken_template=a.spoken_template,
            success_condition=a.success_condition,
        )
        for a in lib.ATTACKS
    ]
    return AttacksResponse(attacks=out)


@app.post("/scans", response_model=ScanResponse)
def create_scan(req: ScanRequest) -> ScanResponse:
    """Run an OFFLINE loopback campaign and return the aggregate summary.

    Forces ``mode='loopback'`` — there is no way to trigger live/PSTN dialing
    through this API. ``n`` is clamped to ``MAX_SCAN_N``.
    """
    n = min(max(1, req.n), MAX_SCAN_N)
    summary = campaign_runner.run_campaign(
        n=n,
        mode="loopback",
        concurrency=req.concurrency,
        persist=req.persist,
    )
    run_id = summary.get("run_id")

    with _LOCK:
        if run_id:
            _RUNS[run_id] = summary
        _METRICS["scans_run"] += 1
        _METRICS["last_breach_rate"] = float(summary.get("breach_rate", 0.0))
        _METRICS["last_run_id"] = run_id
    # Persist the latest aggregate so /scorecard/latest survives across calls.
    scorecard.write_json(summary, SCORECARD_PATH)

    return ScanResponse(run_id=run_id, summary=summary)


@app.get("/scans/{run_id}", response_model=ScanResponse)
def get_scan(run_id: str) -> ScanResponse:
    """Return the summary for a prior run from the in-process registry, else 404."""
    with _LOCK:
        summary = _RUNS.get(run_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id}")
    return ScanResponse(run_id=run_id, summary=summary)


@app.get("/scorecard/latest")
def scorecard_latest() -> dict:
    """Return the most recent aggregate summary, or 404 if no scan has run."""
    with _LOCK:
        last_run_id = _METRICS["last_run_id"]
        summary = _RUNS.get(last_run_id) if last_run_id else None
    if summary is None:
        raise HTTPException(status_code=404, detail="no scorecard yet — run a scan first")
    return summary


@app.get("/metrics", response_model=MetricsResponse)
def metrics() -> MetricsResponse:
    """Lightweight in-process metrics."""
    with _LOCK:
        return MetricsResponse(
            scans_run=_METRICS["scans_run"],
            last_breach_rate=_METRICS["last_breach_rate"],
            last_run_id=_METRICS["last_run_id"],
        )
