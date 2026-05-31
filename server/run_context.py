"""RedDial — run context: correlation IDs, structured logging, persistence.

Phase 3 (ops): the audit found no run/call correlation, two logging stacks, and
no per-call persistence (a transcript was never saved despite the PLAN claim).
This module gives every campaign a ``run_id`` and every call a ``call_id``, a
single structured-logging setup, and a helper to persist each call's full record
(transcript + verdict) to ``transcripts/<run_id>/``.

Pure stdlib. ``uuid4`` is used for ids (fine in Python; only workflow scripts ban
randomness). Persistence is best-effort and never raises into the caller.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(level: str | int | None = None) -> None:
    """Configure root logging once, with a consistent structured-ish format.

    Level from the arg or REDDIAL_LOG_LEVEL (default INFO). Idempotent.
    """
    lvl = level or os.environ.get("REDDIAL_LOG_LEVEL", "INFO")
    if isinstance(lvl, str):
        lvl = getattr(logging, lvl.upper(), logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=lvl, format=_LOG_FORMAT)
    else:
        root.setLevel(lvl)


def new_run_id() -> str:
    """A short, sortable-ish run id: <epoch>-<rand4> (epoch first so runs sort)."""
    return f"{int(time.time())}-{uuid.uuid4().hex[:4]}"


@dataclass
class RunContext:
    """Identifies one campaign run and mints per-call correlation ids."""

    run_id: str
    mode: str = "loopback"
    persist_dir: str | None = None  # base dir for transcripts; None => no persistence

    @classmethod
    def create(cls, mode: str = "loopback", persist: bool = False,
               base_dir: str = "transcripts", run_id: str | None = None) -> RunContext:
        rid = run_id or new_run_id()
        pdir = None
        if persist:
            pdir = str(Path(base_dir) / rid)
            try:
                Path(pdir).mkdir(parents=True, exist_ok=True)
            except OSError:
                pdir = None
        return cls(run_id=rid, mode=mode, persist_dir=pdir)

    def call_id(self, index: int, attack_id: str = "") -> str:
        suffix = f"-{attack_id}" if attack_id else ""
        return f"{self.run_id}-{index:04d}{suffix}"

    def persist_call(self, index: int, attack_id: str, record) -> str | None:
        """Write one call's full record (CallResult dataclass or dict) to disk.

        Returns the path written, or None if persistence is off / failed.
        """
        if not self.persist_dir:
            return None
        try:
            if is_dataclass(record) and not isinstance(record, type):
                payload = asdict(record)
            elif isinstance(record, dict):
                payload = dict(record)  # copy: never mutate the caller's dict below
            else:
                payload = {"repr": repr(record)}
            payload.setdefault("call_id", self.call_id(index, attack_id))
            payload.setdefault("run_id", self.run_id)
            path = Path(self.persist_dir) / f"{index:04d}_{attack_id or 'call'}.json"
            path.write_text(json.dumps(payload, indent=2, default=str))
            return str(path)
        except (OSError, TypeError, ValueError):
            # Best-effort persistence (per module docstring): a serialization
            # failure (e.g. a non-serializable / cyclic record) or write error
            # must never raise into the caller and abort a campaign call.
            return None
