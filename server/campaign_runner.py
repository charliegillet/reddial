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
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import attack_library as lib
import cekura_integration
import loopback
import run_context
import scorecard

logger = logging.getLogger("reddial.campaign")

# Modeled per-turn call duration for loopback timing (text loopback has no real
# call audio). ~9s/turn is a realistic phone-call exchange; the scorecard labels
# the resulting time-to-leak as "modeled" so it is never presented as live audio.
MODELED_SECONDS_PER_TURN = 9.0


def _maybe_post_cekura(result, call_id: str | None = None) -> None:
    """Ship one call's result to Cekura observability for evaluation.

    This is the wiring that makes the eval loop real: without it the Cekura
    integration is dead code (it returns 201 in isolation but nothing flows
    during an actual campaign). It is a graceful no-op when no CEKURA_API_KEY
    is set, and it must NEVER break a call — Cekura is an optional eval sink,
    so any error here is swallowed (logged at warning).

    Args:
        result:  loopback.CallResult (or dict) — the full call record including
                 transcript; must be passed before scorecard.result_row() strips it.
        call_id: structured RunContext correlation id (run_id-NNNN-attack_id);
                 threaded through to Cekura so call logs are cross-referenceable.
    """
    try:
        cekura_integration.post_observability(result, call_id=call_id)
    except Exception as e:  # noqa: BLE001 — eval ingestion must not abort a call
        logger.warning("cekura post skipped: %s: %s", type(e).__name__, e)


def _with_retries(fn, attempts: int, base_delay: float = 0.5, sleep=time.sleep):
    """Call fn() with up to ``attempts`` tries and exponential backoff.

    Retries matter for the live/PSTN path (transient network/model errors); for
    deterministic loopback ``attempts=1`` makes this a passthrough. Re-raises the
    last exception if all attempts fail.
    """
    last = None
    for i in range(max(1, attempts)):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — retry policy owns the decision
            last = e
            if i + 1 < attempts:
                logger.warning("attempt %d/%d failed: %s — retrying", i + 1, attempts, e)
                sleep(base_delay * (2 ** i))
    raise last


def run_one(attack: lib.Attack, mode: str = "loopback",
            seconds_per_turn: float | None = MODELED_SECONDS_PER_TURN,
            ctx: run_context.RunContext | None = None, index: int = 0,
            retries: int = 1) -> dict:
    """Run a single attack call end-to-end and return a scorecard result row.

    mode="loopback": in-process text loopback against the FAKE-PII mock target.
    mode="pstn":     Twilio outbound to the real target number (NOT implemented
                     here — needs the voice layer + Twilio creds).
    If ``ctx`` has persistence enabled, the full CallResult (incl. transcript) is
    written to disk for this call.
    """
    if mode == "loopback":
        result = _with_retries(
            lambda: loopback.run_loopback(attack_id=attack.id, seconds_per_turn=seconds_per_turn),
            attempts=retries,
        )
        if ctx is not None:
            ctx.persist_call(index, attack.id, result)
        # Pass the structured RunContext call_id so Cekura logs are
        # cross-referenceable with our own transcripts/<run_id>/ records.
        cid = ctx.call_id(index, attack.id) if ctx is not None else None
        _maybe_post_cekura(result, call_id=cid)
        return scorecard.result_row(result)
    if mode == "pstn":
        raise NotImplementedError(
            "pstn mode needs the Pipecat+Twilio voice layer (attacker_bot/target_bot) "
            "and Twilio credentials with a verified caller ID. Use mode='loopback' for "
            "the overnight campaign; reserve PSTN for the single live stage call."
        )
    raise ValueError(f"unknown mode: {mode!r} (expected 'loopback' or 'pstn')")


def _safe_call(i: int, attack, mode, seconds_per_turn, ctx, retries) -> tuple[dict, bool]:
    """Run one call with per-call isolation. Returns (row, failed)."""
    try:
        return run_one(attack, mode=mode, seconds_per_turn=seconds_per_turn,
                       ctx=ctx, index=i, retries=retries), False
    except Exception as e:  # noqa: BLE001 — one bad call must not abort the batch
        logger.error("call %d (%s) failed: %s: %s", i, attack.id, type(e).__name__, e)
        return ({"attack_id": attack.id, "leaked": False, "breach": False,
                 "fields": [], "score": 0, "grade": "A", "error": str(e)}, True)


def run_campaign(n: int = 200, mode: str = "loopback",
                 seconds_per_turn: float | None = MODELED_SECONDS_PER_TURN,
                 concurrency: int = 1, persist: bool = False, retries: int = 1,
                 budget: int | None = None, run_id: str | None = None) -> dict:
    """Run n calls cycling through ATTACKS, aggregate, and return the summary.

    Args:
        concurrency: >1 runs calls in a thread pool (bounded). 1 = sequential.
        persist: write each call's transcript under transcripts/<run_id>/.
        retries: per-call retry attempts (live path); 1 = no retry.
        budget: hard cap on number of calls (cost control); clamps n.
    """
    attacks = lib.ATTACKS
    if not attacks:
        return {"total_calls": 0}
    if budget is not None and budget >= 0:
        n = min(n, budget)
    ctx = run_context.RunContext.create(mode=mode, persist=persist, run_id=run_id)
    logger.info("campaign run_id=%s n=%d mode=%s concurrency=%d", ctx.run_id, n, mode, concurrency)

    indexed = [(i, attacks[i % len(attacks)]) for i in range(n)]
    results: list[dict] = []
    failed = 0

    if concurrency and concurrency > 1:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for row, bad in pool.map(
                lambda ia: _safe_call(ia[0], ia[1], mode, seconds_per_turn, ctx, retries),
                indexed,
            ):
                results.append(row)
                failed += int(bad)
    else:
        for i, attack in indexed:
            row, bad = _safe_call(i, attack, mode, seconds_per_turn, ctx, retries)
            results.append(row)
            failed += int(bad)

    summary = scorecard.aggregate(results) if results else {"total_calls": 0}
    summary["failed_calls"] = failed
    summary["run_id"] = ctx.run_id
    if ctx.persist_dir:
        summary["transcripts_dir"] = ctx.persist_dir
    if mode == "loopback" and seconds_per_turn:
        summary["time_note"] = f"modeled · loopback @ ~{seconds_per_turn:g}s/turn (not live audio)"
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="RedDial campaign runner")
    p.add_argument("--n", type=int, default=200, help="number of attack calls")
    p.add_argument("--mode", default="loopback", choices=["loopback", "pstn"])
    p.add_argument("--out", default="scorecard.json", help="JSON scorecard path")
    p.add_argument("--concurrency", type=int, default=1, help="parallel calls (>1 = thread pool)")
    p.add_argument("--persist", action="store_true", help="save per-call transcripts")
    p.add_argument("--retries", type=int, default=1, help="per-call retry attempts (live path)")
    p.add_argument("--budget", type=int, default=None, help="hard cap on calls (cost control)")
    args = p.parse_args()

    run_context.setup_logging()
    summary = run_campaign(n=args.n, mode=args.mode, concurrency=args.concurrency,
                           persist=args.persist, retries=args.retries, budget=args.budget)

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
        f"grade {summary.get('max_grade', '?')} · score {summary.get('max_score', 0)} · "
        f"failed {summary.get('failed_calls', 0)}"
    )
    print(f"  wrote {json_path} + {html_path}")


if __name__ == "__main__":
    main()
