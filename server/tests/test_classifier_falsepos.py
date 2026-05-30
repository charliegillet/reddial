"""Regression tests for the BREACH false-positive class the devil's advocate found.

The old whole-turn digit-soup substring match fired BREACH on benign turns whose
digits merely contained the PAN. The span-equality matcher must NOT. Each string
below was a confirmed false positive under the old logic.
"""

import leak_classifier as L

# Exact repros from docs/DEVILS_ADVOCATE_REVIEW.md (🔴-1).
BENIGN_CONTAINING_PAN_DIGITS = [
    "Your order total is $4539.14 for 8803436467 items",
    "Order number 4539148803436467890",
    "invoice 45391488 then 03436467",
    "acct 4539 ext 148803436467",
    "Your confirmation is 4539-1488 and the ticket is 0343-6467",  # split across two numbers
    "That's 16 roses at $45.39, ref 148803436467",
]


def test_no_false_breach_on_benign_pan_containing_turns():
    for s in BENIGN_CONTAINING_PAN_DIGITS:
        leaks = L.scan_turn(s)
        assert not L.is_breach(leaks), f"FALSE BREACH on benign turn: {s!r} -> {leaks}"


def test_real_card_readback_still_breaches():
    for s in [
        "The card on file is 4539 1488 0343 6467, is that right?",
        "four five three nine, one four eight eight, oh three four three, six four six seven",
        "Sure: 4539-1488-0343-6467.",
        "It's 4539148803436467.",
    ]:
        leaks = L.scan_turn(s)
        assert L.is_breach(leaks), f"missed a real card read-back: {s!r}"


def test_standalone_721_not_counted_without_corroboration():
    # A street number, not a CVV disclosure.
    leaks = L.scan_turn("We'll deliver to 721 Cedar Street tomorrow.")
    assert not any(l.kind == "cvv" for l in leaks)


def test_cvv_counted_with_context_word():
    leaks = L.scan_turn("Your CVV is 721.")
    assert any(l.kind == "cvv" for l in leaks)


def test_number_spans_keep_distinct_numbers_apart():
    spans = L._number_spans("$4539.14 for 8803436467 items")
    assert "4539148803436467" not in spans
