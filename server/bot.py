#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""RedDial — deploy entrypoint / ROLE DISPATCHER.

The Pipecat base image always runs ``bot.py`` (``async def bot(runner_args)`` +
``main()``). This module is a thin shim that selects WHICH implementation to run
based on the ``REDDIAL_ROLE`` env var, so a deploy runs the right RedDial bot
instead of the harmless flower-shop starter.

  REDDIAL_ROLE=target   (DEFAULT) → the deliberately-vulnerable target_bot
  REDDIAL_ROLE=attacker            → the autonomous attacker_bot
  REDDIAL_ROLE=flower              → the original Field & Flower starter
                                     (bot-nemotron.py), kept reachable

Background: ``bot.py`` was previously byte-identical to ``bot-nemotron.py`` (the
vanilla flower-shop starter), so every deploy ran the harmless starter — never
RedDial's target or attacker. This dispatcher fixes that while preserving the
exact entrypoint the base image calls.
"""

import importlib
import importlib.util  # module scope: avoids shadowing `importlib` as a function-local
import os

from loguru import logger

# RedDial defaults to the TARGET role: a deploy of this image is meant to stand
# up the vulnerable agent the attacker dials into.
DEFAULT_ROLE = "target"

_ROLE_MODULES = {
    "target": "target_bot",
    "attacker": "attacker_bot",
    # The original starter lives in bot-nemotron.py. Its module name is not a
    # valid Python identifier (hyphen), so it is loaded by file path below.
    "flower": "bot-nemotron",
}


def _resolve_role() -> str:
    role = os.environ.get("REDDIAL_ROLE", DEFAULT_ROLE).strip().lower()
    if role not in _ROLE_MODULES:
        logger.warning(
            f"Unknown REDDIAL_ROLE={role!r}; valid: {sorted(_ROLE_MODULES)}. "
            f"Falling back to default role {DEFAULT_ROLE!r}."
        )
        role = DEFAULT_ROLE
    return role


def _load_role_module(role: str):
    """Import the module implementing the selected role.

    Imported lazily (inside the call) so this shim itself stays import-clean and
    the heavy pipecat-dependent modules are only pulled when actually dispatched.
    """
    module_name = _ROLE_MODULES[role]
    if role == "flower":
        # bot-nemotron.py is not importable by name (hyphen) — load by path.
        # NB: importlib.util is imported at MODULE scope above; importing it here
        # would rebind `importlib` to a function-local and make the
        # importlib.import_module() call below raise UnboundLocalError for the
        # target/attacker roles.
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot-nemotron.py")
        spec = importlib.util.spec_from_file_location("bot_nemotron", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(module_name)


async def bot(runner_args):
    """Pipecat entry point the base image calls — delegates to the role module."""
    role = _resolve_role()
    logger.info(f"RedDial dispatcher: REDDIAL_ROLE={role!r} → {_ROLE_MODULES[role]}")
    module = _load_role_module(role)
    return await module.bot(runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
