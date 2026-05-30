"""run_loopback must yield a Luhn-verified breach, deterministically, with a
transcript containing both roles. Uses an injected fake clock so timing is
deterministic. Depends on teammate modules (mock_llm, attacker_policy) being
ready; if mock_llm is absent this is skipped (integration-pending)."""

import pytest

import loopback


def _fake_clock():
    """A monotonic fake clock advancing 5s per call (deterministic timing)."""
    t = {"now": 0.0}

    def clock():
        t["now"] += 5.0
        return t["now"]

    return clock


def _have_mock_llm():
    try:
        import mock_llm  # noqa: F401
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _have_mock_llm(), reason="mock_llm not yet available (teammate module pending)"
)


def test_loopback_yields_luhn_verified_breach():
    r = loopback.run_loopback(clock=_fake_clock())
    assert r.breach is True, "expected a Luhn-verified card breach"
    assert r.leaked is True
    assert "card" in r.fields
    # The breach must be a Luhn-valid planted PAN.
    import leak_classifier
    assert leak_classifier.luhn_valid(leak_classifier.PLANTED["card"])
    assert r.seconds_to_first_leak is not None
    assert r.turns_to_first_leak is not None and r.turns_to_first_leak >= 1


def test_loopback_is_deterministic_across_two_runs():
    a = loopback.run_loopback(clock=_fake_clock())
    b = loopback.run_loopback(clock=_fake_clock())
    assert a.breach == b.breach
    assert a.leaked == b.leaked
    assert a.fields == b.fields
    assert a.score == b.score
    assert a.grade == b.grade
    assert a.turns_to_first_leak == b.turns_to_first_leak
    assert a.seconds_to_first_leak == b.seconds_to_first_leak
    # Transcript content is identical turn-for-turn.
    assert [(t["role"], t["text"]) for t in a.transcript] == \
           [(t["role"], t["text"]) for t in b.transcript]


def test_transcript_has_both_roles():
    r = loopback.run_loopback(clock=_fake_clock())
    roles = {t["role"] for t in r.transcript}
    assert "attacker" in roles
    assert "target" in roles
    # Every entry carries role + text + state per the contract.
    for entry in r.transcript:
        assert set(("role", "text", "state")).issubset(entry.keys())
