"""RedDial outbound-dialing safety controls — enforced in CODE, defaults OFF.

The README/PLAN promise that RedDial "only dials numbers under our control or
with written consent, is rate-limited, and is not a mass-dialer." Until now those
promises lived only in docstrings (security audit BLOCKER 3 / 🔴-1, 🔴-2, 🟡-1).
This module turns them into enforced controls:

  * a fail-closed kill-switch (REDDIAL_DIALING_ENABLED, default FALSE),
  * a destination allowlist (REDDIAL_DIAL_ALLOWLIST),
  * strict E.164 destination validation,
  * an explicit per-call consent gate,
  * a per-process call cap + minimum-interval rate limiter (CallGuard),
  * TwiML/XML-injection sanitization of the public host.

Everything fails CLOSED: if config is missing or ambiguous, dialing is refused.
Pure stdlib only (os, re, time); no external deps. Environment is read at call
time (not import time) so callers/tests can set os.environ dynamically.
"""

from __future__ import annotations

import os
import re
import time

__all__ = [
    "DialingNotAllowed",
    "dialing_enabled",
    "load_allowlist",
    "is_e164",
    "check_destination",
    "validate_public_host",
    "CallGuard",
]

# Strict E.164: '+', a nonzero leading country-code digit, then total 8..15 digits.
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

# host[:port] with no scheme, no path, no whitespace/quotes/angle brackets.
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+(:\d+)?$")

# Truthy tokens accepted for the kill-switch (case-insensitive, exact match).
_TRUTHY = frozenset({"1", "true", "yes"})

# Safe finite default call cap when REDDIAL_MAX_CALLS is unset.
_DEFAULT_MAX_CALLS = 50


class DialingNotAllowed(Exception):
    """Raised when a safety control refuses an outbound dialing action."""


def dialing_enabled() -> bool:
    """Return True only if REDDIAL_DIALING_ENABLED is an explicit 1/true/yes.

    Fail-closed kill-switch: absent/empty/any other value means disabled.
    """
    return os.environ.get("REDDIAL_DIALING_ENABLED", "").strip().lower() in _TRUTHY


def load_allowlist() -> set[str]:
    """Parse REDDIAL_DIAL_ALLOWLIST (comma-separated E.164) into a set.

    Empty/unset -> empty set. Whitespace around entries is stripped; blank
    entries are dropped. Values are not coerced — only exact strings are kept.
    """
    raw = os.environ.get("REDDIAL_DIAL_ALLOWLIST", "")
    return {entry.strip() for entry in raw.split(",") if entry.strip()}


def is_e164(number: str) -> bool:
    """Strict E.164 check: '+' then 8..15 digits, leading country digit 1-9."""
    return isinstance(number, str) and _E164_RE.match(number) is not None


def check_destination(to_number: str, *, consent: bool = False) -> None:
    """Fail-closed gate for an outbound destination.

    Raises DialingNotAllowed unless ALL of the following hold:
      * dialing_enabled() is True,
      * to_number is strict E.164,
      * to_number is in the allowlist,
      * consent is True.

    The exception message names WHICH check failed but never echoes the full
    destination number (avoid leaking dialed targets into logs).
    """
    if not dialing_enabled():
        raise DialingNotAllowed(
            "kill-switch off: set REDDIAL_DIALING_ENABLED=1 to enable dialing"
        )
    if not is_e164(to_number):
        raise DialingNotAllowed("destination not E.164 (rejected)")
    if to_number not in load_allowlist():
        raise DialingNotAllowed("destination not allowlisted (rejected)")
    if not consent:
        raise DialingNotAllowed("consent not recorded for destination (rejected)")


def validate_public_host(host: str) -> str:
    """Sanitize a host for interpolation into a TwiML <Stream url="wss://.../">.

    Strips a single leading scheme (e.g. "wss://", "https://") then accepts only
    host[:port] matching ^[A-Za-z0-9.-]+(:\\d+)?$ . Anything containing spaces,
    quotes, '/', '<', '>', or that is empty raises ValueError (XML-injection guard).
    Returns the sanitized host.
    """
    if not isinstance(host, str):
        raise ValueError("public host must be a string")
    candidate = host.strip()
    # Strip a single leading scheme delimiter if present (e.g. "wss://x" -> "x").
    if "://" in candidate:
        candidate = candidate.split("://", 1)[1]
    if not candidate or not _HOST_RE.match(candidate):
        raise ValueError("invalid public host (failed TwiML/XML-injection guard)")
    return candidate


class CallGuard:
    """Per-process outbound-call rate limiter: hard cap + minimum interval.

    The clock is injectable for tests; it defaults to time.monotonic. acquire()
    raises DialingNotAllowed when the call cap is exceeded or when invoked faster
    than min_interval_s since the previous successful acquire.
    """

    def __init__(
        self,
        max_calls: int | None = None,
        min_interval_s: float = 0.0,
        clock=None,
    ):
        if max_calls is None:
            env = os.environ.get("REDDIAL_MAX_CALLS", "").strip()
            if env:
                try:
                    max_calls = int(env)
                except ValueError:
                    max_calls = _DEFAULT_MAX_CALLS
            else:
                # Unset env -> safe finite default (never unlimited by accident).
                max_calls = _DEFAULT_MAX_CALLS
        self._max_calls = max_calls
        self._min_interval_s = max(0.0, float(min_interval_s))
        self._clock = clock if clock is not None else time.monotonic
        self._count = 0
        self._last_ts: float | None = None

    @property
    def count(self) -> int:
        """Number of successful acquire() calls so far."""
        return self._count

    def acquire(self) -> None:
        """Reserve one outbound call slot or raise DialingNotAllowed."""
        # Cap check: <=0 means no calls permitted; positive is a hard ceiling.
        if self._max_calls is not None and self._count >= self._max_calls:
            raise DialingNotAllowed(
                f"call cap reached ({self._count}/{self._max_calls})"
            )
        # Rate-limit check against the previous successful acquire.
        if self._min_interval_s > 0.0 and self._last_ts is not None:
            now = self._clock()
            elapsed = now - self._last_ts
            if elapsed < self._min_interval_s:
                raise DialingNotAllowed(
                    f"rate limited: min interval {self._min_interval_s}s "
                    f"(only {elapsed:.3f}s elapsed)"
                )
        self._count += 1
        self._last_ts = self._clock()
