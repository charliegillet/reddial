"""RedDial — efficacy run harness (Phase 2).

Runs ONE end-to-end red-team attack and captures a single, honestly-labeled
result artifact (transcript + verdict + provenance). This is the machinery for
closing the audit's BLOCKER 4 ("never called a real agent") — but it cannot, by
itself, manufacture real-world efficacy:

  * ``--mode loopback`` (default, runs anywhere, no keys): attacks the project's
    OWN deliberately-vulnerable mock. The artifact is explicitly stamped
    ``target_kind = "self-authored-mock"`` and ``proves_real_world_efficacy =
    False`` — a passing loopback breach is NOT evidence against a real agent.

  * ``--mode live`` (requires NVIDIA + Twilio keys AND the dialing safety gate):
    places a gated outbound call via attacker_bot to a CONSENTED, allowlisted
    number. This is the only path that produces real evidence — and it must be
    run by an operator with keys + consent; it is not exercised in CI/this repo.

The artifact is written to ``results/efficacy_<run_id>.json`` so a real run can be
attached to the production-readiness record.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import loopback
import run_context

logger = logging.getLogger("reddial.efficacy")


def _artifact(run_id: str, mode: str, target_kind: str, proven: bool, **fields) -> dict:
    return {
        "run_id": run_id,
        "mode": mode,
        "target_kind": target_kind,
        "proves_real_world_efficacy": proven,
        **fields,
    }


def run_loopback_efficacy(attack_id: str | None = None,
                          ctx: run_context.RunContext | None = None) -> dict:
    """One text-loopback attack vs the self-authored mock. Honest provenance."""
    ctx = ctx or run_context.RunContext.create(mode="loopback")
    result = loopback.run_loopback(attack_id=attack_id, seconds_per_turn=9.0)
    ctx.persist_call(0, result.attack_id, result)
    return _artifact(
        ctx.run_id, "loopback",
        target_kind="self-authored-mock",
        proven=False,  # attacking our own mock is not proof against a real agent
        attack_id=result.attack_id,
        breach=result.breach,
        leaked=result.leaked,
        grade=result.grade,
        score=result.score,
        turns_to_first_leak=result.turns_to_first_leak,
        transcript=result.transcript,
        note=("Loopback attacks RedDial's own vulnerable mock. A breach here "
              "validates the attack/classifier pipeline, NOT real-world efficacy. "
              "Run --mode live against a consented real agent for evidence."),
    )


def run_live_efficacy(to_number: str, consent: bool = False,
                      ctx: run_context.RunContext | None = None) -> dict:
    """Initiate ONE gated, consented outbound call (requires keys + safety env).

    This INITIATES the call through the enforced safety gate; full audio
    transcript capture + classification happen inside the attacker_bot Pipecat
    pipeline on the connected leg. We never fabricate a breach result here.
    """
    ctx = ctx or run_context.RunContext.create(mode="live")
    import attacker_bot  # imported here so loopback mode needs no voice deps
    # The safety gate (kill-switch + E.164 allowlist + consent) is enforced
    # inside place_outbound_call and will raise DialingNotAllowed if unmet.
    call = attacker_bot.place_outbound_call(to_number, consent=consent)
    sid = getattr(call, "sid", None)
    logger.info("live efficacy call initiated (sid=%s)", sid)
    return _artifact(
        ctx.run_id, "live",
        target_kind="real-agent (operator-supplied, consented)",
        proven=None,  # decided by the captured transcript on the connected leg
        call_sid=sid,
        note=("Call initiated through the enforced safety gate. Breach verdict is "
              "produced by the attacker_bot pipeline's leak_classifier on the live "
              "transcript; attach that transcript to this artifact to claim evidence."),
    )


def write_artifact(artifact: dict, out_dir: str = "results") -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"efficacy_{artifact['run_id']}.json"
    path.write_text(json.dumps(artifact, indent=2, default=str))
    return str(path)


def main() -> None:
    p = argparse.ArgumentParser(description="RedDial single efficacy run")
    p.add_argument("--mode", default="loopback", choices=["loopback", "live"])
    p.add_argument("--attack", default=None, help="attack id (loopback mode)")
    p.add_argument("--to", default=None, help="E.164 destination (live mode)")
    p.add_argument("--consent", action="store_true",
                   help="affirm written consent exists for the destination (live mode)")
    p.add_argument("--out", default="results", help="output dir for the artifact")
    args = p.parse_args()
    run_context.setup_logging()

    if args.mode == "loopback":
        artifact = run_loopback_efficacy(attack_id=args.attack)
    else:
        if not args.to:
            p.error("--to <E.164> is required for --mode live")
        artifact = run_live_efficacy(args.to, consent=args.consent)

    path = write_artifact(artifact, out_dir=args.out)
    print(f"efficacy[{artifact['mode']}] proven_real_world={artifact['proves_real_world_efficacy']} "
          f"-> {path}")
    if artifact["mode"] == "loopback":
        print("  NOTE: loopback attacks our own mock — NOT proof against a real agent.")


if __name__ == "__main__":
    main()
