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

import json
import logging
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import attack_library as lib
import campaign_runner
import loopback
import scorecard

logger = logging.getLogger("reddial.api")

VERSION = "1.0.0"

# Attack used to capture the representative breaching transcript per scan.
REPRESENTATIVE_ATTACK_ID = "authority_pretext"
# Modeled per-turn duration for the representative loopback (matches the campaign).
REPRESENTATIVE_SECONDS_PER_TURN = 9.0
# Base dir where run_context persists per-call transcripts.
TRANSCRIPTS_DIR = "transcripts"

# Hard cap on calls per scan. Loopback is fast/deterministic, but we still bound
# request work so the synchronous API never runs unbounded. Per API_CONTRACT.md.
MAX_SCAN_N = 500
MAX_CONCURRENCY = 16  # cap thread-pool fan-out on the synchronous /scans endpoint

# Where the latest aggregate summary is persisted (scorecard.write_json).
SCORECARD_PATH = "scorecard.json"

# How many recent run summaries to keep in the in-process history (Analytics view).
HISTORY_LIMIT = 50

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
# In-process registry of one representative breaching transcript per run_id, for
# GET /scans/{run_id}/transcript. Shape: {run_id: {attack_id, breach, transcript}}.
# Survives restart only via the on-disk fallback (transcripts/<run_id>/*.json).
_TRANSCRIPTS: dict[str, dict] = {}
# Rolling in-process history of run summaries, most-recent-LAST (we reverse on read).
# Survives restart only for the LATEST entry: full history is in-process, but we
# seed it from scorecard.json on startup so the Analytics view shows at least the
# last run after a `uvicorn` restart (see _seed_from_disk).
_HISTORY: list[dict] = []
_METRICS = {
    "scans_run": 0,
    "last_breach_rate": 0.0,
    "last_run_id": None,
}


def _read_scorecard_disk() -> dict | None:
    """Read the persisted latest aggregate summary from SCORECARD_PATH, or None.

    Used as the fallback for /scorecard/latest so the dashboard does not load
    blank after a `uvicorn` restart wipes the in-process registry.
    """
    try:
        raw = Path(SCORECARD_PATH).read_text()
    except (OSError, ValueError):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _transcript_payload(run_id: str | None, result: loopback.CallResult) -> dict:
    """Project a CallResult down to the transcript-endpoint response shape."""
    return {
        "run_id": run_id,
        "attack_id": result.attack_id,
        "breach": bool(result.breach),
        "transcript": list(result.transcript),
    }


def _read_transcript_disk(run_id: str | None = None) -> dict | None:
    """Fall back to a persisted per-call transcript json on disk, or None.

    If ``run_id`` is given, look under ``transcripts/<run_id>/``; otherwise scan
    all runs. Picks the newest file (prefer a breaching call so the UI shows a
    real breach after a restart). Returns the transcript-endpoint payload shape.
    """
    def _mtime(p: Path) -> float:
        # Resilient stat: a file/dir removed concurrently (e.g. a parallel
        # persist run or external cleanup, racing this read) must not raise out
        # of the sort key and 500 the endpoint — treat it as oldest.
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    base = Path(TRANSCRIPTS_DIR)
    if run_id:
        dirs = [base / run_id]
    else:
        try:
            dirs = sorted(
                (p for p in base.iterdir() if p.is_dir()),
                key=_mtime,
                reverse=True,
            )
        except OSError:
            return None
    files: list[Path] = []
    for d in dirs:
        try:
            files.extend(p for p in d.glob("*.json"))
        except OSError:
            continue
    if not files:
        return None
    files.sort(key=_mtime, reverse=True)

    def _load(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or "transcript" not in data:
            return None
        return data

    # Prefer a breaching call (newest first); else fall back to the newest call.
    chosen = None
    for path in files:
        data = _load(path)
        if data is None:
            continue
        if chosen is None:
            chosen = data
        if data.get("breach"):
            chosen = data
            break
    if chosen is None:
        return None
    return {
        "run_id": chosen.get("run_id", run_id),
        "attack_id": chosen.get("attack_id", ""),
        "breach": bool(chosen.get("breach", False)),
        "transcript": list(chosen.get("transcript", [])),
    }


def _history_summary(summary: dict) -> dict:
    """Project a full aggregate dict down to the compact run-history row shape."""
    return {
        "run_id": summary.get("run_id"),
        "total_calls": summary.get("total_calls", 0),
        "leak_rate": summary.get("leak_rate", 0.0),
        "breach_rate": summary.get("breach_rate", 0.0),
        "max_grade": summary.get("max_grade", "A"),
        "max_score": summary.get("max_score", 0),
        "failed_calls": summary.get("failed_calls", 0),
    }


def _seed_from_disk() -> None:
    """Seed in-process state from scorecard.json on startup (restart resilience).

    Populates the run registry, metrics, and history with the last persisted
    summary so /scorecard/latest, /scans and /metrics are non-empty right after a
    restart, even before any new scan has run this process.
    """
    summary = _read_scorecard_disk()
    if not summary:
        return
    run_id = summary.get("run_id")
    with _LOCK:
        if _HISTORY:  # already seeded / scans already recorded this process
            return
        if run_id:
            _RUNS[run_id] = summary
            _METRICS["last_run_id"] = run_id
        _METRICS["last_breach_rate"] = float(summary.get("breach_rate", 0.0))
        _HISTORY.append(_history_summary(summary))


# --------------------------------------------------------------------------- models

class ScanRequest(BaseModel):
    n: int = Field(default=24, ge=1, description="Number of loopback attack calls.")
    persist: bool = Field(default=False, description="Persist per-call transcripts to disk.")
    concurrency: int = Field(default=1, ge=1, le=MAX_CONCURRENCY,
                             description="Parallel calls (>1 = thread pool; capped).")


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


class RunSummaryOut(BaseModel):
    run_id: str | None
    total_calls: int
    leak_rate: float
    breach_rate: float
    max_grade: str
    max_score: int
    failed_calls: int


class ScansResponse(BaseModel):
    runs: list[RunSummaryOut]


class TranscriptTurn(BaseModel):
    role: str
    text: str
    state: str | None = None


class TranscriptResponse(BaseModel):
    run_id: str | None
    attack_id: str
    breach: bool
    transcript: list[TranscriptTurn]


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
    concurrency = min(max(1, req.concurrency), MAX_CONCURRENCY)  # defense-in-depth cap
    summary = campaign_runner.run_campaign(
        n=n,
        mode="loopback",
        concurrency=concurrency,
        persist=req.persist,
    )
    run_id = summary.get("run_id")

    # Capture ONE representative breaching transcript for display. The campaign
    # aggregates many calls but discards transcripts, so we run a single extra
    # OFFLINE loopback against a known-breaching attack to get full attacker/target
    # turns. Best-effort: a failure here must not fail the scan.
    transcript_payload: dict | None = None
    try:
        rep = loopback.run_loopback(
            attack_id=REPRESENTATIVE_ATTACK_ID,
            seconds_per_turn=REPRESENTATIVE_SECONDS_PER_TURN,
        )
        transcript_payload = _transcript_payload(run_id, rep)
    except Exception:  # noqa: BLE001 — representative capture is best-effort
        transcript_payload = None

    with _LOCK:
        if run_id:
            _RUNS[run_id] = summary
            if transcript_payload is not None:
                _TRANSCRIPTS[run_id] = transcript_payload
        _METRICS["scans_run"] += 1
        _METRICS["last_breach_rate"] = float(summary.get("breach_rate", 0.0))
        _METRICS["last_run_id"] = run_id
        _HISTORY.append(_history_summary(summary))
        del _HISTORY[:-HISTORY_LIMIT]  # bound the rolling history
    # Persist the latest aggregate so /scorecard/latest survives a process restart.
    # Best-effort: the scan already ran and in-process state is committed, so a
    # disk error (read-only fs, disk full) must NOT turn a successful scan into a
    # 500 the client can't interpret. Log and continue.
    try:
        scorecard.write_json(summary, SCORECARD_PATH)
    except OSError as exc:
        logger.warning("scorecard persist failed for run_id=%s: %s", run_id, exc)

    return ScanResponse(run_id=run_id, summary=summary)


@app.get("/scans", response_model=ScansResponse)
def list_scans() -> ScansResponse:
    """Recent run summaries, most recent first, for the Analytics view.

    History is in-process (bounded to HISTORY_LIMIT) but seeded from
    ``scorecard.json`` on startup, so at least the latest run survives a restart.
    OFFLINE-only: this only reads recorded loopback summaries; it dials nothing.
    """
    with _LOCK:
        runs = [RunSummaryOut(**row) for row in reversed(_HISTORY)]
    return ScansResponse(runs=runs)


@app.get("/scans/{run_id}", response_model=ScanResponse)
def get_scan(run_id: str) -> ScanResponse:
    """Return the summary for a prior run from the in-process registry, else 404."""
    with _LOCK:
        summary = _RUNS.get(run_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id}")
    return ScanResponse(run_id=run_id, summary=summary)


@app.get("/transcript/latest", response_model=TranscriptResponse)
def transcript_latest() -> TranscriptResponse:
    """Return the latest run's representative breaching transcript.

    Reads the in-process registry first (keyed by the last run_id); if empty
    (e.g. right after a `uvicorn` restart) FALLS BACK to the newest persisted
    per-call transcript json under ``transcripts/``. 404 if neither source has one.
    OFFLINE-only — these are loopback transcripts against the FAKE-PII mock.
    """
    with _LOCK:
        last_run_id = _METRICS["last_run_id"]
        payload = _TRANSCRIPTS.get(last_run_id) if last_run_id else None
    if payload is None:
        payload = _read_transcript_disk()
    if payload is None:
        raise HTTPException(status_code=404, detail="no transcript yet — run a scan first")
    return TranscriptResponse(**payload)


@app.get("/scans/{run_id}/transcript", response_model=TranscriptResponse)
def get_scan_transcript(run_id: str) -> TranscriptResponse:
    """Return the representative breaching transcript for a run, else 404.

    In-process registry first, then a disk fallback to ``transcripts/<run_id>/``
    so a known run still resolves after a restart. OFFLINE-only loopback data.
    """
    with _LOCK:
        payload = _TRANSCRIPTS.get(run_id)
        known = run_id in _RUNS
    if payload is None:
        payload = _read_transcript_disk(run_id)
    if payload is None:
        if known:
            raise HTTPException(
                status_code=404, detail=f"no transcript captured for run_id: {run_id}"
            )
        raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id}")
    return TranscriptResponse(**payload)


@app.get("/scorecard/latest")
def scorecard_latest() -> dict:
    """Return the most recent aggregate summary.

    Reads the in-process registry first; if it is empty (e.g. right after a
    `uvicorn` restart) it FALLS BACK to the persisted ``scorecard.json`` on disk
    so the dashboard does not load blank. 404 only if neither source has data.
    """
    with _LOCK:
        last_run_id = _METRICS["last_run_id"]
        summary = _RUNS.get(last_run_id) if last_run_id else None
    if summary is None:
        summary = _read_scorecard_disk()
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


# Seed history/metrics from the last persisted scorecard so the dashboard's
# Analytics + scorecard views are non-empty immediately after a restart.
_seed_from_disk()
