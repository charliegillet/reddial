"""RedDial — campaign runner.

Drives N attack calls (cycling the attack library), scores each via the text
loopback, and writes the scorecard (JSON + HTML). Run the big batch OVERNIGHT in
loopback mode for volume (PLAN.md "Pre-built vs day-of") — PSTN is reserved for
the single live stage call and is not implemented here (needs Twilio).

Usage:
    python campaign_runner.py --n 24 --mode loopback --out scorecard.json
    python campaign_runner.py --n 200            # full overnight batch

SAFETY: loopback only ever talks to the FAKE-PII mock target we own.
Contract: server/INTERFACES.md  campaign_runner.py.
"""

from __future__ import annotations

import argparse

import attack_library as lib
import loopback
import scorecard


# Modeled per-turn call duration for loopback timing (text loopback has no real
# call audio). ~9s/turn is a realistic phone-call exchange; the scorecard labels
# the resulting time-to-leak as "modeled" so it is never presented as live audio.
MODELED_SECONDS_PER_TURN = 9.0


def run_one(attack: "lib.Attack", mode: str = "loopback",
            seconds_per_turn: float | None = MODELED_SECONDS_PER_TURN) -> dict:
    """Run a single attack call end-to-end and return a scorecard result row.

    mode="loopback": in-process text loopback against the FAKE-PII mock target.
    mode="pstn":     Twilio outbound to the real target number (NOT implemented
                     here — needs the voice layer + Twilio creds).
    """
    if mode == "loopback":
        result = loopback.run_loopback(attack_id=attack.id, seconds_per_turn=seconds_per_turn)
        return scorecard.result_row(result)
    if mode == "pstn":
        raise NotImplementedError(
            "pstn mode needs the Pipecat+Twilio voice layer (attacker_bot/target_bot) "
            "and Twilio credentials with a verified caller ID. Use mode='loopback' for "
            "the overnight campaign; reserve PSTN for the single live stage call."
        )
    raise ValueError(f"unknown mode: {mode!r} (expected 'loopback' or 'pstn')")


def run_campaign(n: int = 200, mode: str = "loopback",
                 seconds_per_turn: float | None = MODELED_SECONDS_PER_TURN) -> dict:
    """Run n calls cycling through ATTACKS, aggregate, and write scorecard.{json,html}."""
    results: list[dict] = []
    attacks = lib.ATTACKS
    if not attacks:
        return {"total_calls": 0}
    for i in range(n):
        attack = attacks[i % len(attacks)]
        results.append(run_one(attack, mode=mode, seconds_per_turn=seconds_per_turn))
    summary = scorecard.aggregate(results) if results else {"total_calls": 0}
    if mode == "loopback" and seconds_per_turn:
        summary["time_note"] = f"modeled · loopback @ ~{seconds_per_turn:g}s/turn (not live audio)"
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="RedDial campaign runner")
    p.add_argument("--n", type=int, default=200, help="number of attack calls")
    p.add_argument("--mode", default="loopback", choices=["loopback", "pstn"])
    p.add_argument("--out", default="scorecard.json", help="JSON scorecard path")
    args = p.parse_args()

    summary = run_campaign(n=args.n, mode=args.mode)

    json_path = args.out
    html_path = (
        args.out[:-5] + ".html" if args.out.endswith(".json") else args.out + ".html"
    )
    scorecard.write_json(summary, json_path)
    scorecard.write_html(summary, html_path)

    print(
        f"RedDial campaign: {summary.get('total_calls', 0)} calls · "
        f"leak rate {summary.get('leak_rate', 0):.0%} · "
        f"breach rate {summary.get('breach_rate', 0):.0%} · "
        f"grade {summary.get('max_grade', '?')} · score {summary.get('max_score', 0)}"
    )
    print(f"  wrote {json_path} + {html_path}")


if __name__ == "__main__":
    main()
