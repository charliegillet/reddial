"""Lock the deterministic attacker FSM progression and label alignment.

The transcript label (policy.state after next_move) must match the category of
the line spoken that turn — no off-by-one — and consecutive lines must differ
(a repeated identical line is what makes a demo "look scripted").
"""

import attacker_policy


def test_state_progression_is_deterministic_and_forward():
    p = attacker_policy.AttackerPolicy()
    assert p.state == "RECON"
    seen_states = []
    seen_lines = []
    target = ""  # silent target -> deflecting posture each turn
    for _ in range(6):
        atk = p.next_move(target)
        seen_states.append(p.state)
        seen_lines.append(atk.spoken_template)
    # Forward march through the pipeline, one phase per turn.
    assert seen_states[:5] == ["PRETEXT", "INJECT", "ESCALATE", "EXFIL", "EXFIL"]


def test_label_matches_spoken_category():
    """The phase we are in == the category of the line we speak (no off-by-one)."""
    p = attacker_policy.AttackerPolicy()
    expected = {
        "PRETEXT": "pretext",
        "INJECT": "injection",
        "ESCALATE": "escalation",
        "EXFIL": "confusion",
    }
    for _ in range(4):
        atk = p.next_move("")
        assert atk.category == expected[p.state], (p.state, atk.category)


def test_no_repeated_consecutive_line():
    p = attacker_policy.AttackerPolicy()
    lines = [p.next_move("").spoken_template for _ in range(5)]
    for a, b in zip(lines, lines[1:]):
        assert a != b, f"attacker repeated a line: {a!r}"


def test_leak_short_circuits_to_confirm_then_done():
    p = attacker_policy.AttackerPolicy()
    p.next_move("")           # -> PRETEXT
    p.next_move("", leaked=True)
    assert p.state == "CONFIRM"
    p.next_move("", leaked=True)
    assert p.state == "DONE"
    assert p.done


def test_two_runs_identical_in_deterministic_mode():
    def run():
        p = attacker_policy.AttackerPolicy()
        return [p.next_move("").id for _ in range(5)]
    assert run() == run()
