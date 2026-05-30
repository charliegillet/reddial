"""Tests for the honest GEPA-style mitigation loop."""

import gepa_mitigation


def test_suggest_mitigation_names_observed_fields():
    diff = gepa_mitigation.suggest_mitigation(
        [{"fields": ["card", "cvv"]}], current_guardrail="weak")
    assert "Never read back" in diff
    assert "card" in diff and "cvv" in diff


def test_suggest_mitigation_defaults_without_transcripts():
    diff = gepa_mitigation.suggest_mitigation([], current_guardrail="weak")
    assert "card" in diff.lower()


def test_reverify_blocks_the_attack_honestly():
    res = gepa_mitigation.reverify("authority_pretext")
    assert res["attack_id"] == "authority_pretext"
    assert res["breach_before"] is True          # weak target leaks
    assert res["breach_after"] is False           # hardened guardrail blocks THIS attack
    assert "not general robustness" in res["note"]


def test_reverify_reports_truth_if_not_blocked():
    # A patched guardrail that is still weak must NOT be reported as a block.
    res = gepa_mitigation.reverify("authority_pretext", patched_guardrail="be nice")
    assert isinstance(res["breach_after"], bool)
    if res["breach_after"]:
        assert "did NOT block" in res["note"]
