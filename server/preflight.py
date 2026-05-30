"""RedDial — startup preflight config validation.

Production hardening: instead of a deep ``KeyError`` from inside the Pipecat
pipeline (or a silent timeout against a missing endpoint), validate the
environment for the selected role at startup and fail with ONE readable message
that names exactly what's missing. Recommended-but-not-fatal gaps log a warning.

The offline harness needs none of this — preflight only matters for the live
voice path. Pure stdlib; reads ``os.environ`` at call time.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("reddial.preflight")

# Hard-required env for each role's LIVE voice pipeline. All three forks use the
# NVIDIA STT/LLM endpoints + Gradium TTS.
_HARD_REQUIRED = {
    "target": ("NVIDIA_ASR_URL", "NEMOTRON_LLM_URL", "GRADIUM_API_KEY"),
    "attacker": ("NVIDIA_ASR_URL", "NEMOTRON_LLM_URL", "GRADIUM_API_KEY"),
    "flower": ("NVIDIA_ASR_URL", "NEMOTRON_LLM_URL", "GRADIUM_API_KEY"),
}

# Recommended-but-not-fatal: dialing config for the attacker. The safety gate
# already fails closed at call time, so these are warnings (the bot can still run
# over local WebRTC without dialing).
_DIAL_RECOMMENDED = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "VERIFIED_CALLER_ID", "PUBLIC_HOST")


def check(role: str, env: dict | None = None) -> dict:
    """Return {ok, role, missing_required, missing_recommended} for a role.

    Never raises; ``enforce`` decides whether missing-required is fatal.
    """
    env = os.environ if env is None else env
    role = (role or "target").strip().lower()
    required = _HARD_REQUIRED.get(role, _HARD_REQUIRED["target"])
    missing_required = [k for k in required if not env.get(k)]

    missing_recommended: list[str] = []
    if role == "attacker":
        dialing_on = env.get("REDDIAL_DIALING_ENABLED", "").strip().lower() in ("1", "true", "yes")
        if dialing_on:
            # If dialing is turned ON, the Twilio config should be present.
            missing_recommended = [k for k in _DIAL_RECOMMENDED if not env.get(k)]

    return {
        "ok": not missing_required,
        "role": role,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
    }


def enforce(role: str, raise_on_missing: bool = True) -> dict:
    """Validate config for ``role``; log clearly and (by default) raise on a
    hard-missing var so a misconfigured deploy fails fast and readably.

    Skipped entirely when REDDIAL_SKIP_PREFLIGHT is truthy.
    """
    if os.environ.get("REDDIAL_SKIP_PREFLIGHT", "").strip().lower() in ("1", "true", "yes"):
        logger.warning("preflight skipped (REDDIAL_SKIP_PREFLIGHT set)")
        return {"ok": True, "skipped": True, "role": role}

    result = check(role)
    for k in result["missing_recommended"]:
        logger.warning("preflight: %s not set — outbound dialing will be limited/blocked", k)

    if result["missing_required"]:
        msg = (
            f"RedDial preflight FAILED for role={result['role']!r}: missing required "
            f"env: {', '.join(result['missing_required'])}. Set these (see .env.example) "
            f"or run the offline harness (no keys needed). Bypass with REDDIAL_SKIP_PREFLIGHT=1."
        )
        logger.error(msg)
        if raise_on_missing:
            raise RuntimeError(msg)
    else:
        logger.info("preflight OK for role=%s", result["role"])
    return result
