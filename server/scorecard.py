"""RedDial — campaign scorecard.

Aggregates per-call transcripts + classifier verdicts into a vulnerability
scorecard (JSON + HTML): grade, leak rate, median time-to-leak, per-vector
breakdown, evidence spans, and breach audio clip links.
See PLAN.md → "Leak classifier & vulnerability score" and "Pre-built vs day-of".
"""

import json
import statistics
from pathlib import Path


def aggregate(call_results: list[dict]) -> dict:
    """call_results: [{attack_id, leaked, fields[], score, grade,
    seconds_to_first_leak, audio_clip}]"""
    n = len(call_results)
    landed = [c for c in call_results if c.get("leaked")]
    times = [c["seconds_to_first_leak"] for c in landed if c.get("seconds_to_first_leak")]
    by_vector: dict[str, dict] = {}
    for c in call_results:
        v = by_vector.setdefault(c["attack_id"], {"runs": 0, "leaks": 0})
        v["runs"] += 1
        v["leaks"] += 1 if c.get("leaked") else 0
    return {
        "total_calls": n,
        "leak_rate": (len(landed) / n) if n else 0.0,
        "median_time_to_leak_s": statistics.median(times) if times else None,
        "max_score": max((c.get("score", 0) for c in call_results), default=0),
        "by_vector": by_vector,
    }


def write_json(summary: dict, path: str = "scorecard.json") -> None:
    Path(path).write_text(json.dumps(summary, indent=2))


def write_html(summary: dict, path: str = "scorecard.html") -> None:
    """TODO: render the dashboard the judges see (PLAN.md §demo script)."""
    rows = "".join(
        f"<tr><td>{k}</td><td>{v['leaks']}/{v['runs']}</td></tr>"
        for k, v in summary.get("by_vector", {}).items()
    )
    Path(path).write_text(
        f"<h1>RedDial Vulnerability Scorecard</h1>"
        f"<p>Calls: {summary['total_calls']} · Leak rate: {summary['leak_rate']:.0%} · "
        f"Median time-to-leak: {summary.get('median_time_to_leak_s')}s · "
        f"Max score: {summary['max_score']}</p>"
        f"<table border=1><tr><th>Attack</th><th>Leaks/Runs</th></tr>{rows}</table>"
    )
