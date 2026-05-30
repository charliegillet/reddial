"""RedDial — overnight campaign runner.

Drives N attack calls against the target bot, captures transcripts + breach
audio clips, scores each, writes the scorecard. Run this OVERNIGHT (200 calls x
1-3 min = 5-10 hrs) in-process/loopback for volume; reserve PSTN for the one
live stage call. See PLAN.md → "Pre-built vs day-of".

Usage:
    python campaign_runner.py --n 200 --mode loopback --out scorecard.json
"""

import attack_library as lib
import scorecard


def run_one(attack: "lib.Attack", mode: str = "loopback") -> dict:
    """Run a single attack call end-to-end and return a result row.

    TODO (PLAN.md §System architecture):
      - mode='loopback': pipe attacker_bot <-> target_bot pipelines in-process
      - mode='pstn': Twilio outbound to the target number
      - run attacker_policy until DONE; scan each target turn with leak_classifier
      - capture audio clip on first breach
    """
    raise NotImplementedError("run_one: wire attacker_bot/target_bot + leak_classifier")


def run_campaign(n: int = 200, mode: str = "loopback") -> dict:
    results = []
    attacks = lib.ATTACKS
    for i in range(n):
        attack = attacks[i % len(attacks)]
        try:
            results.append(run_one(attack, mode=mode))
        except NotImplementedError:
            break
    summary = scorecard.aggregate(results) if results else {"total_calls": 0}
    return summary


if __name__ == "__main__":
    print("campaign_runner stub — implement run_one() per PLAN.md §System architecture")
