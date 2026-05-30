"""RedDial — attacker policy state machine.

Nemotron generates the spoken line; this orchestrator picks the STRATEGY STATE
based on the target's posture. RECON -> PRETEXT -> INJECT -> ESCALATE -> EXFIL
-> CONFIRM -> DONE. See PLAN.md → "System architecture".

For the on-stage call: run temperature 0 + fixed turns for determinism.
"""

import attack_library as lib

STATES = ["RECON", "PRETEXT", "INJECT", "ESCALATE", "EXFIL", "CONFIRM", "DONE"]


class AttackerPolicy:
    def __init__(self, nemotron=None, max_attempts: int = 3):
        self.nemotron = nemotron
        self.state = "RECON"
        self.attempts = 0
        self.max_attempts = max_attempts

    def classify_posture(self, target_said: str) -> str:
        """compliant | deflecting | refusing | confused | verifying_identity.
        TODO: cheap Nemotron-Nano classification on the target's last turn."""
        t = (target_said or "").lower()
        if any(k in t for k in ("can't share", "not able", "won't", "policy", "cannot")):
            return "refusing"
        if any(k in t for k in ("verify", "who is this", "confirm your")):
            return "verifying_identity"
        if any(k in t for k in ("sure", "okay", "the number is", "it's")):
            return "compliant"
        return "deflecting"

    def next_move(self, target_said: str, leaked: bool = False) -> lib.Attack:
        if leaked:
            self.state = "CONFIRM"
        posture = self.classify_posture(target_said)

        if self.state == "RECON":
            if posture == "verifying_identity":
                self.state = "PRETEXT"
            return lib.pick("pretext", posture)
        if self.state == "PRETEXT":
            if posture in ("compliant", "confused"):
                self.state = "INJECT"
            return lib.pick("pretext", posture)
        if self.state == "INJECT":
            if posture == "compliant":
                self.state = "ESCALATE"
            elif posture == "refusing":
                return lib.pick("confusion", posture)
            return lib.pick("injection", posture)
        if self.state == "ESCALATE":
            self.state = "EXFIL"
            return lib.pick("escalation", posture)
        if self.state == "EXFIL":
            self.attempts += 1
            if posture == "compliant":
                self.state = "CONFIRM"
            elif self.attempts > self.max_attempts:
                self.state = "DONE"
            return lib.pick("minimization", posture)
        # CONFIRM / DONE
        self.state = "DONE"
        return lib.pick("authority", posture)
