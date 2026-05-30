"""Tests for the outbound-dialing safety controls (BLOCKER 3 enforcement).

The whole point is that dialing FAILS CLOSED: with no env configured, no call is
permitted. These tests pin that contract so a future refactor can't silently
re-open the autodialer.
"""

import pytest

import safety_controls as S
from safety_controls import DialingNotAllowed

ALLOWED = "+14155551234"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("REDDIAL_DIALING_ENABLED", "REDDIAL_DIAL_ALLOWLIST", "REDDIAL_MAX_CALLS"):
        monkeypatch.delenv(k, raising=False)


def _enable(monkeypatch, allowlist=ALLOWED):
    monkeypatch.setenv("REDDIAL_DIALING_ENABLED", "1")
    monkeypatch.setenv("REDDIAL_DIAL_ALLOWLIST", allowlist)


# --- fail-closed defaults --------------------------------------------------

def test_default_is_fail_closed():
    # No env at all: even a valid, consented number is refused (kill-switch off).
    with pytest.raises(DialingNotAllowed):
        S.check_destination(ALLOWED, consent=True)
    assert S.dialing_enabled() is False


def test_kill_switch_requires_explicit_truthy(monkeypatch):
    for val in ("", "0", "false", "no", "maybe", "TRUE "):
        monkeypatch.setenv("REDDIAL_DIALING_ENABLED", val)
        # only exact 1/true/yes (case-insensitive, trimmed) enable
        assert S.dialing_enabled() is (val.strip().lower() in {"1", "true", "yes"})


# --- the four-part gate ----------------------------------------------------

def test_all_conditions_met_passes(monkeypatch):
    _enable(monkeypatch)
    S.check_destination(ALLOWED, consent=True)  # no raise


def test_missing_consent_refused(monkeypatch):
    _enable(monkeypatch)
    with pytest.raises(DialingNotAllowed, match="consent"):
        S.check_destination(ALLOWED, consent=False)


def test_not_allowlisted_refused(monkeypatch):
    _enable(monkeypatch, allowlist="+19998887777")
    with pytest.raises(DialingNotAllowed, match="allowlist"):
        S.check_destination(ALLOWED, consent=True)


def test_non_e164_refused(monkeypatch):
    _enable(monkeypatch, allowlist="4155551234")
    with pytest.raises(DialingNotAllowed):
        S.check_destination("4155551234", consent=True)


def test_exception_never_echoes_full_number(monkeypatch):
    _enable(monkeypatch, allowlist="+19998887777")
    try:
        S.check_destination(ALLOWED, consent=True)
        assert False, "expected refusal"
    except DialingNotAllowed as e:
        assert ALLOWED not in str(e)


# --- E.164 ------------------------------------------------------------------

@pytest.mark.parametrize("n,ok", [
    ("+14155551234", True), ("+441632960961", True),
    ("4155551234", False), ("+0123456", False), ("+1", False),
    ("+1415555123456789", False), ("", False), ("+1-415-555-1234", False),
])
def test_is_e164(n, ok):
    assert S.is_e164(n) is ok


# --- public host injection guard -------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("example.ngrok.io", "example.ngrok.io"),
    ("host:8080", "host:8080"),
    ("wss://example.io", "example.io"),
    ("https://a.b.c:443", "a.b.c:443"),
])
def test_validate_public_host_ok(raw, expected):
    assert S.validate_public_host(raw) == expected


@pytest.mark.parametrize("bad", ['a b', 'h"/><x', 'x/y', '', '<script>', 'a b.io'])
def test_validate_public_host_rejects_injection(bad):
    with pytest.raises(ValueError):
        S.validate_public_host(bad)


# --- CallGuard -------------------------------------------------------------

def test_callguard_cap_enforced():
    g = S.CallGuard(max_calls=2, min_interval_s=0.0)
    g.acquire(); g.acquire()
    assert g.count == 2
    with pytest.raises(DialingNotAllowed, match="cap"):
        g.acquire()


def test_callguard_rate_limit_with_fake_clock():
    t = [100.0]
    g = S.CallGuard(max_calls=10, min_interval_s=5.0, clock=lambda: t[0])
    g.acquire()                 # first ok
    with pytest.raises(DialingNotAllowed, match="rate"):
        g.acquire()             # too soon
    t[0] += 6.0
    g.acquire()                 # enough time elapsed
    assert g.count == 2


def test_callguard_default_cap_is_finite(monkeypatch):
    monkeypatch.delenv("REDDIAL_MAX_CALLS", raising=False)
    g = S.CallGuard()
    assert isinstance(g._max_calls, int) and g._max_calls > 0
