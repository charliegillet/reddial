"""GAP H1: scripts/setup-secrets.sh must never echo a raw secret VALUE.

This is a lightweight static-source guard (no shell execution, fully hermetic).
The script reads secret values into a shell variable and pushes them to Pipecat
Cloud / GitHub Actions. The contract is: key NAMES may be printed, but secret
VALUES must never reach stdout. We assert no line pipes a value-bearing variable
($val, $REDDIAL_SECRET_VALUE) into echo/printf, and that `set -x` (which would
trace expanded values) is not enabled.
"""

import os
import re

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "setup-secrets.sh",
)


def _lines():
    with open(_SCRIPT, encoding="utf-8") as f:
        return f.read().splitlines()


def test_setup_secrets_script_exists():
    assert os.path.isfile(_SCRIPT), f"missing: {_SCRIPT}"


def test_no_echo_of_secret_value_variable_to_console():
    # `echo` always writes to the console/stdout, so an `echo` that interpolates
    # a value-bearing variable would leak the secret. Key NAMES (${key}) are fine;
    # VALUES (${val}, ${REDDIAL_SECRET_VALUE}) are not.
    value_vars = re.compile(r"\$\{?(val|REDDIAL_SECRET_VALUE)\b")
    echo_stmt = re.compile(r"^\s*echo\b")
    offenders = []
    for i, line in enumerate(_lines(), start=1):
        if echo_stmt.search(line) and value_vars.search(line):
            offenders.append((i, line.strip()))
    assert not offenders, f"secret VALUE may be echoed to console: {offenders}"


def test_printf_of_value_is_only_the_captured_return_idiom():
    # The script uses exactly one `printf '%s' "${val}"` — inside get_env_value()
    # to RETURN the value via command substitution ($(...)) into a variable, NOT
    # to print it to the console. Pin that this remains the ONLY value-printf and
    # that its line sits inside the get_env_value function body (return idiom),
    # so a future change that prints ${val} to the console elsewhere is caught.
    lines = _lines()
    value_printf = re.compile(r"^\s*printf\b.*\$\{?(val|REDDIAL_SECRET_VALUE)\b")
    hits = [i for i, line in enumerate(lines, start=1) if value_printf.search(line)]
    assert len(hits) <= 1, (
        f"expected at most the single get_env_value() return printf, got {hits}"
    )
    if hits:
        # Confirm the one allowed printf lives inside get_env_value (the function
        # whose documented purpose is reading a value WITHOUT printing it).
        ln = hits[0]
        body = "\n".join(lines[max(0, ln - 20):ln])
        assert "get_env_value()" in body, (
            "value-printf is not inside the get_env_value return idiom"
        )


def test_no_set_x_tracing_that_would_expand_secret_values():
    # `set -x` traces every command with variables expanded -> would leak values.
    for i, line in enumerate(_lines(), start=1):
        stripped = line.strip()
        assert stripped not in ("set -x", "set -o xtrace"), (
            f"line {i}: shell tracing would expand secret values to stderr"
        )
