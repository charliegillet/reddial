"""Tests for the honest, eval-driven auto-improve loop.

Covers the binding contract in docs/plans/2026-05-31-auto-improve-design.md:
  - breach_rate is non-increasing across rounds (the monotone curve);
  - the trained suite converges to a 0 breach_rate;
  - suggest_clause is eval-driven: picks no_full_pan first on a fresh weak
    summary, and returns None once nothing covers any open vector;
  - the held-out emotional_urgency vector STILL breaches after convergence
    (the honesty assertion — the loop does NOT generalise);
  - two runs are byte-identical (determinism).

All data is SYNTHETIC (Stripe test BIN, specimen SSN); the target is a mock we own.
"""

import json

import auto_improve
import gepa_mitigation
import mock_llm


def test_breach_rate_non_increasing_across_rounds():
    r = auto_improve.run_auto_improve(rounds=8)
    breach = r["curve"]["breach_rate"]
    assert len(breach) >= 2
    for prev, cur in zip(breach, breach[1:]):
        assert cur <= prev + 1e-9, f"breach_rate rose: {prev} -> {cur}"


def test_curve_is_a_gradual_descent_not_a_cliff():
    # The targeted "fix the worst open vector with the narrowest clause" rule
    # closes ~one technique per round, so the curve descends over several rounds
    # rather than collapsing to zero in a single step.
    r = auto_improve.run_auto_improve(rounds=8)
    breach = r["curve"]["breach_rate"]
    assert len(breach) >= 4, f"expected a >=4-point descending curve, got {breach}"
    # Strictly decreasing until it reaches zero (a genuine taper, no flat cliff).
    assert breach[0] > breach[-1]
    nonzero = [b for b in breach if b > 0]
    assert all(a > b for a, b in zip(nonzero, nonzero[1:])), \
        f"breach should strictly drop each non-zero round: {breach}"
    assert breach[-1] == 0.0
    # Each round added exactly one targeted clause (one technique per round).
    clauses = [t["clause_added"] for t in r["trajectory"]]
    assert clauses[0] is None  # round 0 is the baseline
    assert all(c is not None for c in clauses[1:])


def test_final_breach_rate_zero_on_trained_suite():
    r = auto_improve.run_auto_improve(rounds=6)
    assert r["final"]["breach_rate"] == 0.0
    assert r["improvement"]["converged"] is True
    assert r["converged_reason"] in ("breach_rate_zero", "no_useful_clause")


def test_suggest_clause_picks_a_targeted_narrow_clause_first():
    # A fresh weak summary: the card-breaching vectors are open and leak the card.
    # The worst open vector (tie-break: attack_id ascending) is authority_pretext
    # (category 'pretext'); the NARROWEST clause covering it is the targeted
    # reject_authority_pretext (width 2), NOT the broad no_full_pan (width 4).
    by_vector = {
        "authority_pretext": {"runs": 1, "leaks": 1, "breaches": 1,
                              "leak_rate": 1.0, "fields": ["card"]},
        "impersonation": {"runs": 1, "leaks": 1, "breaches": 1,
                          "leak_rate": 1.0, "fields": ["card"]},
        "context_reset": {"runs": 1, "leaks": 1, "breaches": 1,
                          "leak_rate": 1.0, "fields": ["card"]},
        "cvv_minimizer": {"runs": 1, "leaks": 1, "breaches": 0,
                          "leak_rate": 1.0, "fields": ["cvv"]},
    }
    clause = gepa_mitigation.suggest_clause(by_vector, active_clause_ids=set())
    assert clause is not None
    assert clause.id == "reject_authority_pretext"
    # It is strictly narrower than the broad card field clause it beat out.
    broad = mock_llm.clause_by_id("no_full_pan")
    width = len(clause.blocks_categories) + len(clause.blocks_fields)
    broad_width = len(broad.blocks_categories) + len(broad.blocks_fields)
    assert width < broad_width


def test_suggest_clause_returns_none_when_nothing_covers():
    # No open vector at all -> nothing to cover -> None (converged).
    assert gepa_mitigation.suggest_clause({}, active_clause_ids=set()) is None
    # An open vector whose category/field no remaining clause blocks -> None.
    by_vector = {
        "authority_pretext": {"runs": 1, "leaks": 1, "breaches": 1,
                              "leak_rate": 1.0, "fields": ["card"]},
    }
    all_ids = {c.id for c in mock_llm.GUARD_CLAUSES}
    assert gepa_mitigation.suggest_clause(by_vector, active_clause_ids=all_ids) is None


def test_held_out_emotional_urgency_still_breaches_after_convergence():
    # The honesty assertion: training the rest of the suite does NOT close the
    # held-out vector. It breaches both before AND after convergence.
    r = auto_improve.run_auto_improve(rounds=6)
    assert r["held_out"]["vector"] == "emotional_urgency"
    assert r["held_out"]["breach_before"] is True
    assert r["held_out"]["breach_after"] is True
    # resist_pressure (the only clause covering social_pressure) is never trained.
    # final_guardrail is a list of clause TEXTS; check the per-round clause ids.
    trained_ids = {t["clause_added"] for t in r["trajectory"] if t["clause_added"]}
    assert "resist_pressure" not in trained_ids


def test_two_runs_are_byte_identical():
    a = auto_improve.run_auto_improve(rounds=6)
    b = auto_improve.run_auto_improve(rounds=6)
    # run_id is the only intentionally-varying field — drop it before comparing.
    a.pop("run_id")
    b.pop("run_id")
    assert json.dumps(a, sort_keys=True, default=str) == \
        json.dumps(b, sort_keys=True, default=str)
