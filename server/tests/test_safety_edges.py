"""Additional fail-closed edge cases for safety_controls.

Complements test_safety_controls.py. Pins the env-parsing, allowlist, E.164
boundary, host-scheme, and CallGuard corner cases that a refactor could quietly
break. Everything must FAIL CLOSED (refuse) when config is missing/ambiguous.
"""

import pytest

import safety_controls as S
from safety_controls import DialingNotAllowed


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("REDDIAL_DIALING_ENABLED", "REDDIAL_DIAL_ALLOWLIST", "REDDIAL_MAX_CALLS"):
        monkeypatch.delenv(k, raising=False)


# --- allowlist parsing -----------------------------------------------------

def test_allowlist_empty_when_unset():
    assert S.load_allowlist() == set()


def test_allowlist_strips_whitespace_and_drops_blanks(monkeypatch):
    monkeypatch.setenv("REDDIAL_DIAL_ALLOWLIST", " +14155551234 , ,+19998887777,")
    assert S.load_allowlist() == {"+14155551234", "+19998887777"}


def test_allowlist_does_not_coerce_non_e164(monkeypatch):
    # Values are kept verbatim — a non-E.164 entry stays a non-match for E.164 nums.
    monkeypatch.setenv("REDDIAL_DIAL_ALLOWLIST", "4155551234")
    assert "4155551234" in S.load_allowlist()
    assert "+14155551234" not in S.load_allowlist()


# --- E.164 boundaries -------------------------------------------------------

@pytest.mark.parametrize("n", [
    "+10000000",      # leading country digit 1, 8 digits total (min) -> ok
    "+123456789012345",  # 15 digits (max) -> ok
])
def test_is_e164_accepts_boundaries(n):
    assert S.is_e164(n) is True


@pytest.mark.parametrize("n", [
    "+1234567",            # 7 digits -> too short
    "+1234567890123456",   # 16 digits -> too long
    "+01234567",           # leading zero country code
    "1234567890",          # no plus
    "+1 415 555 1234",     # spaces
    "++14155551234",       # double plus
    None,                  # not a string
    12345,                 # not a string
])
def test_is_e164_rejects(n):
    assert S.is_e164(n) is False


# --- check_destination: order of checks ------------------------------------

def test_kill_switch_checked_before_e164(monkeypatch):
    # Even garbage destination + consent must report the kill-switch first.
    with pytest.raises(DialingNotAllowed, match="kill-switch"):
        S.check_destination("garbage", consent=True)


# --- public host scheme stripping ------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("wss://host.example/", None),     # trailing slash -> path -> reject
])
def test_validate_public_host_rejects_trailing_path(raw, expected):
    with pytest.raises(ValueError):
        S.validate_public_host(raw)


def test_validate_public_host_strips_only_one_scheme(monkeypatch):
    assert S.validate_public_host("https://a.example") == "a.example"
    # A bare host is returned unchanged.
    assert S.validate_public_host("a.example:9000") == "a.example:9000"


def test_validate_public_host_rejects_non_string():
    with pytest.raises(ValueError):
        S.validate_public_host(None)


# --- CallGuard env-driven cap ----------------------------------------------

def test_callguard_reads_cap_from_env(monkeypatch):
    monkeypatch.setenv("REDDIAL_MAX_CALLS", "1")
    g = S.CallGuard()
    g.acquire()
    with pytest.raises(DialingNotAllowed, match="cap"):
        g.acquire()


def test_callguard_malformed_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("REDDIAL_MAX_CALLS", "not-a-number")
    g = S.CallGuard()
    assert g._max_calls == S._DEFAULT_MAX_CALLS


def test_callguard_zero_cap_permits_nothing():
    g = S.CallGuard(max_calls=0)
    with pytest.raises(DialingNotAllowed, match="cap"):
        g.acquire()


def test_callguard_negative_interval_clamped_to_zero():
    g = S.CallGuard(max_calls=5, min_interval_s=-10.0)
    # Negative interval clamps to 0 -> no rate limiting, both acquire.
    g.acquire()
    g.acquire()
    assert g.count == 2


def test_callguard_rate_limit_boundary_exact_interval():
    t = [0.0]
    g = S.CallGuard(max_calls=10, min_interval_s=5.0, clock=lambda: t[0])
    g.acquire()
    t[0] = 5.0  # exactly the interval -> NOT < min_interval, so allowed
    g.acquire()
    assert g.count == 2
