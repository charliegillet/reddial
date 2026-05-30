"""RedDial — bridge the *basic evalset* into Cekura so the judge can SEE it.

This module makes RedDial's deterministic basic evalset (the named pass/fail
scenarios defined in ``evalset.py``) VISIBLE in the Cekura dashboard:

  - ``publish_evalset()``      registers each evalset scenario in Cekura as a
                               named scenario (so the evalset itself shows up).
  - ``post_evalset_results()`` posts each scenario's pass/fail from a
                               ``run_evalset(...)`` result as a Cekura
                               observability entry (so the verdict shows up).

It is a THIN bridge: it REUSES ``cekura_integration`` (``to_scenario``,
``register_personas``, ``post_observability``) and never re-implements any HTTP,
auth, stub, or PII-guard logic. ``cekura_integration`` is NOT modified.

GRACEFUL NO-OP: with no ``CEKURA_API_KEY`` present, every function returns a
clearly-labeled status dict and performs no network calls — importing and
running the offline path never requires a key and never crashes. This mirrors
``cekura_integration``'s stub pattern (it short-circuits inside ``_post`` /
``post_observability`` when the key is absent).

LAZY IMPORT: ``evalset`` is imported lazily inside each function because a
teammate is still creating it — this module must import cleanly even when
``evalset.py`` does not yet exist.
"""

from __future__ import annotations

import logging
import os

import cekura_integration

logger = logging.getLogger("reddial.evalset_cekura")


def _has_key() -> bool:
    """True iff a Cekura API key is configured (mirrors cekura_integration)."""
    return bool(os.environ.get("CEKURA_API_KEY") or os.environ.get("X_CEKURA_API_KEY"))


def _load_evalset():
    """Lazily import the teammate's ``evalset`` module.

    Returns the imported module, or ``None`` if it does not exist yet (the
    teammate may not have created ``evalset.py`` at this module's import time).
    Tries the flat import first (matches this package's convention) then the
    ``server.`` prefixed form, mirroring cekura_integration's dual-import style.
    """
    try:
        import evalset  # type: ignore

        return evalset
    except Exception:
        try:
            from server import evalset  # type: ignore

            return evalset
        except Exception:
            return None


def publish_evalset() -> dict:
    """Register every basic-evalset scenario in Cekura as a named scenario.

    REUSES ``cekura_integration.register_personas`` (which itself calls
    ``to_scenario`` + ``_post`` per attack). We filter ``attack_library.ATTACKS``
    down to the attack ids referenced by ``BASIC_EVALSET`` so only the evalset's
    attacks are published — that is exactly the set the judge expects to see.

    Graceful no-op without a key: returns ``stub=True`` and publishes nothing
    (no network calls). Returns::

        {"published": int, "stub": bool, "scenario_ids": [...]}

    where ``scenario_ids`` are the Cekura scenario response ids (when the API
    returned them) or the RedDial scenario names as a fallback identifier.
    """
    evalset = _load_evalset()
    if evalset is None:
        logger.warning("publish_evalset: evalset module not available yet")
        return {"published": 0, "stub": True, "scenario_ids": [],
                "_reason": "evalset module not importable"}

    basic = list(getattr(evalset, "BASIC_EVALSET", []) or [])
    attack_ids = [e.get("attack_id") for e in basic if e.get("attack_id")]

    # Filter the attack library to just the evalset's attacks, preserving the
    # evalset's order and de-duplicating while keeping the first occurrence.
    by_id = getattr(__import__("attack_library"), "ATTACK_BY_ID", {})
    seen: set[str] = set()
    attacks = []
    for aid in attack_ids:
        if aid in seen:
            continue
        seen.add(aid)
        attack = by_id.get(aid)
        if attack is not None:
            attacks.append(attack)

    if not _has_key():
        logger.warning(
            "publish_evalset: no CEKURA_API_KEY — no-op (would publish %d scenarios)",
            len(attacks),
        )
        return {"published": 0, "stub": True, "scenario_ids": [],
                "_reason": "CEKURA_API_KEY absent"}

    # REUSE: register_personas maps each attack via to_scenario and posts it.
    results = cekura_integration.register_personas(attacks)

    scenario_ids: list = []
    published = 0
    for attack, result in zip(attacks, results):
        if result.get("posted"):
            published += 1
            response = result.get("response")
            sid = response.get("id") if isinstance(response, dict) else None
            scenario_ids.append(sid if sid is not None else f"reddial::{attack.id}")

    return {"published": published, "stub": False, "scenario_ids": scenario_ids}


def post_evalset_results(result: dict) -> dict:
    """Post each evalset scenario's pass/fail to Cekura observability.

    Given a ``run_evalset(...)`` result (``{scenarios, passed, pass_rate, ...}``),
    each per-scenario entry is posted via ``cekura_integration.post_observability``
    — so we REUSE its CreateCallLog construction AND its fail-closed PII egress
    guard (``_egress_pan_safe``). We never re-implement that guard here; a
    refused (foreign-PAN) entry simply counts as not posted.

    Graceful no-op without a key: returns ``stub=True`` and posts nothing.
    Returns::

        {"posted": int, "stub": bool, "total": int, "call_ids": [...]}
    """
    scenarios = list((result or {}).get("scenarios", []) or [])

    if not _has_key():
        logger.warning(
            "post_evalset_results: no CEKURA_API_KEY — no-op (would post %d results)",
            len(scenarios),
        )
        return {"posted": 0, "stub": True, "total": len(scenarios), "call_ids": [],
                "_reason": "CEKURA_API_KEY absent"}

    posted = 0
    call_ids: list[str] = []
    for scenario in scenarios:
        # Scenario id and attack id locate the result in Cekura. We accept either
        # an explicit scenario id or fall back to attack_id-derived correlation.
        attack_id = scenario.get("attack_id") or scenario.get("id") or "unknown"
        scenario_id = scenario.get("id") or attack_id
        call_id = f"reddial-evalset::{scenario_id}"

        # Normalize pass/fail into the verdict fields post_observability reads.
        # An evalset scenario "passes" when the target did NOT leak (defended).
        passed = bool(scenario.get("passed"))
        leaked = scenario.get("leaked")
        if leaked is None:
            leaked = not passed
        breach = bool(scenario.get("breach", False))

        # Hand cekura_integration a plain dict in the shape post_observability
        # accepts (its dict branch reads transcript + the metadata fields).
        call_result = {
            "attack_id": attack_id,
            "leaked": bool(leaked),
            "breach": breach,
            "fields": scenario.get("fields", []),
            "score": scenario.get("score", 0),
            "grade": scenario.get("grade", "A"),
            "seconds_to_first_leak": scenario.get("seconds_to_first_leak"),
            "turns_to_first_leak": scenario.get("turns_to_first_leak"),
            "transcript": scenario.get("transcript", []),
        }

        # REUSE: post_observability builds the CreateCallLog, applies the
        # fail-closed PAN egress guard, and posts. Returns True only on a real
        # successful post (False on any stub/no-op/refusal).
        if cekura_integration.post_observability(call_result, call_id=call_id):
            posted += 1
            call_ids.append(call_id)

    return {"posted": posted, "stub": False, "total": len(scenarios),
            "call_ids": call_ids}
