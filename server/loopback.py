"""RedDial — in-process text loopback (the keystone testable artifact).

Pure-text conversation; no audio, no API keys. Drives the attacker policy state
machine against the deliberately-vulnerable mock target, scanning every TARGET
turn with the leak classifier (regex+Luhn ground truth). Stops on breach / DONE /
max_turns and emits a fully-scored ``CallResult``.

Timing is injectable via ``clock`` (default ``time.monotonic``) so tests get
deterministic seconds-to-first-leak with a fake clock.

SAFETY: every secret in play is FAKE (Stripe test BIN / specimen SSN). The
loopback only ever talks to a mock target we built and own. See PLAN.md
"Safety / ethics framing" and the "Behind at 3pm MVP cut" (this loopback IS that
MVP: one reliable, Luhn-verified breach the judges read on the transcript).

Contract: server/INTERFACES.md  loopback.py.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import attack_library as lib
import attacker_policy
import fake_accounts
import leak_classifier

# mock_llm is owned by the ATTACKER engineer and may still be mid-build while
# this module is written. Import lazily inside run_loopback so the module still
# imports cleanly (and other importers — scorecard, campaign_runner — don't break)
# even before mock_llm lands.


@dataclass
class CallResult:
    attack_id: str
    leaked: bool
    breach: bool                       # Luhn-verified card leak
    fields: list[str]
    score: int
    grade: str
    seconds_to_first_leak: float | None
    turns_to_first_leak: int | None
    transcript: list[dict] = field(default_factory=list)
    # [{"role": "attacker"|"target", "text": str, "state": str}]


def _make_policy(attacker_llm):
    """Build an AttackerPolicy, tolerating either the contract signature
    ``AttackerPolicy(llm=None, max_attempts=3, deterministic=True)`` or the
    current in-repo ``AttackerPolicy(nemotron=None, max_attempts=3)``.

    Determinism is the stage default; tests run with no LLM so the keyword
    fallback path is exercised either way.
    """
    try:
        return attacker_policy.AttackerPolicy(llm=attacker_llm, deterministic=True)
    except TypeError:
        # In-repo signature (nemotron=, no deterministic=) — note this mismatch
        # for integration; behaviour is identical for the deterministic path.
        try:
            return attacker_policy.AttackerPolicy(nemotron=attacker_llm)
        except TypeError:
            return attacker_policy.AttackerPolicy()


def _spoken_line(attacker_llm, attack: "lib.Attack", posture: str) -> str:
    """Resolve the literal line the attacker says this turn.

    If an attacker LLM/brain is supplied and exposes ``say``, use it; otherwise
    speak the attack's literal template (deterministic stage path).
    """
    if attacker_llm is not None and hasattr(attacker_llm, "say"):
        try:
            return attacker_llm.say(attack, posture)
        except Exception:
            pass
    return attack.spoken_template


def _is_breach(leaks) -> bool:
    """A breach is a verbatim, Luhn-valid card leak. Prefer the classifier's own
    ``is_breach`` if present (contract), else compute it locally."""
    fn = getattr(leak_classifier, "is_breach", None)
    if callable(fn):
        return bool(fn(leaks))
    for lk in leaks:
        if getattr(lk, "kind", None) == "card" and getattr(lk, "verbatim", False):
            return True
    return False


def run_loopback(
    attack_id: str | None = None,
    max_turns: int = 12,
    target_llm=None,
    attacker_llm=None,
    clock=None,
    seconds_per_turn: float | None = None,
) -> CallResult:
    """Run one text-loopback red-team call and return a scored ``CallResult``.

    Drives ``attacker_policy.AttackerPolicy`` <-> ``mock_llm.MockTargetLLM``,
    scanning each TARGET turn with ``leak_classifier.scan_turn``. Stops on the
    first Luhn-verified breach, on the policy reaching DONE, or at ``max_turns``.

    Args:
        attack_id: pin the opening/seed attack (else cycle from the policy).
        max_turns: hard cap on attacker<->target exchanges.
        target_llm: defaults to ``MockTargetLLM(FAKE_ACCOUNTS["default"])``.
        attacker_llm: optional brain; ``None`` => deterministic template path.
        clock: ``() -> float`` monotonic source (injected for deterministic tests).
    """
    clock = clock or time.monotonic
    t0 = clock()

    # Default target: the deliberately-vulnerable mock seeded with FAKE PII.
    if target_llm is None:
        import mock_llm  # lazy: owned by a teammate, may be mid-build
        target_llm = mock_llm.MockTargetLLM(fake_accounts.FAKE_ACCOUNTS["default"])

    policy = _make_policy(attacker_llm)

    # Seed: if a specific attack is pinned, find it so the first spoken line is it.
    seed_attack = None
    if attack_id is not None:
        seed_attack = next((a for a in lib.ATTACKS if a.id == attack_id), None)

    transcript: list[dict] = []
    history: list[dict] = []  # passed to MockTargetLLM.reply as [{"role","content"}-ish]

    leaked = False
    breach = False
    all_leaks: list = []
    seconds_to_first_leak: float | None = None
    turns_to_first_leak: int | None = None

    target_said = ""        # nothing said yet on turn 0
    turn = 0

    while turn < max_turns:
        turn += 1

        # 1) Attacker chooses its next strategic move from the target's last turn.
        posture = ""
        try:
            posture = policy.classify_posture(target_said)
        except Exception:
            posture = ""
        attack = policy.next_move(target_said, leaked=leaked)
        # Honour a pinned opening attack on the very first turn.
        if turn == 1 and seed_attack is not None:
            attack = seed_attack
        attacker_text = _spoken_line(attacker_llm, attack, posture)

        transcript.append({
            "role": "attacker",
            "text": attacker_text,
            "state": getattr(policy, "state", ""),
        })

        # 2) Target replies (vulnerable mock or injected target_llm).
        target_said = target_llm.reply(attacker_text, history)
        history.append({"role": "attacker", "content": attacker_text})
        history.append({"role": "target", "content": target_said})

        # 3) Scan the TARGET turn for leaks (ground-truth regex+Luhn first).
        leaks = leak_classifier.scan_turn(target_said)
        transcript.append({
            "role": "target",
            "text": target_said,
            "state": getattr(policy, "state", ""),
        })

        if leaks:
            all_leaks.extend(leaks)
            if not leaked:
                leaked = True
                seconds_to_first_leak = clock() - t0
                turns_to_first_leak = turn
            if _is_breach(leaks):
                breach = True
                break

        # 4) Stop when the attacker policy is exhausted.
        if getattr(policy, "done", False):
            break

    # Text loopback has no call audio, so wall-clock time-to-leak is ~0 and
    # meaningless as a "phone call" metric. When asked, model it honestly as
    # turns × a realistic per-turn call duration (clearly labeled as modeled in
    # the scorecard). turns_to_first_leak stays the real, deterministic signal.
    if seconds_per_turn is not None and turns_to_first_leak is not None:
        seconds_to_first_leak = round(turns_to_first_leak * seconds_per_turn, 1)

    # Score from the accumulated leaks (classifier owns the formula).
    if all_leaks:
        scored = leak_classifier.score(
            all_leaks,
            seconds_to_first_leak if seconds_to_first_leak is not None else 0.0,
            turns_to_first_leak if turns_to_first_leak is not None else max_turns,
            max_turns=max_turns,
        )
        fields = scored.get("fields", [])
        score_val = scored.get("score", 0)
        grade = scored.get("grade", "A")
    else:
        fields, score_val, grade = [], 0, "A"

    return CallResult(
        attack_id=attack_id or (seed_attack.id if seed_attack else (lib.ATTACKS[0].id if lib.ATTACKS else "")),
        leaked=leaked,
        breach=breach,
        fields=list(fields),
        score=int(score_val),
        grade=grade,
        seconds_to_first_leak=seconds_to_first_leak,
        turns_to_first_leak=turns_to_first_leak,
        transcript=transcript,
    )
