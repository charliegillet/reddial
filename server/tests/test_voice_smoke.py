"""Smoke + contract tests for the integration layer.

cekura_integration must (a) import with zero heavy deps, (b) no-op gracefully
without a key, and (c) report a CLEAR non-ok status from check_connection rather
than silently pretending to work (the production audit flagged silent no-op as a
trust hazard for an assurance product).
"""

import cekura_integration as C


class _Attack:
    id = "authority_pretext"
    category = "pretext"
    spoken_template = "Hi, this is Marcus..."
    success_condition = "card disclosed"
    escalation_ladder = ["a", "b"]


def test_to_scenario_shape():
    s = C.to_scenario(_Attack())
    assert s["name"] == "reddial::authority_pretext"
    assert "system_prompt" in s and "success_criteria" in s


def test_register_personas_noops_without_key(monkeypatch):
    monkeypatch.delenv("CEKURA_API_KEY", raising=False)
    monkeypatch.delenv("X_CEKURA_API_KEY", raising=False)
    out = C.register_personas([_Attack(), _Attack()])
    assert len(out) == 2
    assert all(r.get("_stub") is True and r.get("posted") is False for r in out)


def test_post_observability_false_without_key(monkeypatch):
    monkeypatch.delenv("CEKURA_API_KEY", raising=False)
    monkeypatch.delenv("X_CEKURA_API_KEY", raising=False)
    assert C.post_observability({"attack_id": "x", "breach": True}) is False


def test_check_connection_is_loud_without_key(monkeypatch):
    monkeypatch.delenv("CEKURA_API_KEY", raising=False)
    monkeypatch.delenv("X_CEKURA_API_KEY", raising=False)
    res = C.check_connection()
    # Must explicitly report it is NOT working — not a silent success.
    assert res["ok"] is False
    assert res["status"] == "no_key"


def test_observability_path_corrected():
    # Verified against Cekura's live OpenAPI spec: the real ingest route is
    # POST /observability/v1/observe/ (the old /observability/send-calls 404'd).
    assert "observability/v1/observe" in C._OBSERVABILITY_PATH
