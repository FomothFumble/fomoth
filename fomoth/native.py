"""Bridge to the C++ regret core in `core/`, with a pure-Python fallback.

The heavy pass of the report, valuing every sell against the peak that came after it,
is the fumble/regret computation. It ships as a small C++ binary (built from `core/`);
this module serialises the inputs, runs the binary and parses its JSON. When the binary
is not built, callers fall back to the pure-Python implementation in `fomoth/regret.py`,
so the package works with or without a compiler.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BIN_NAMES = ("fumble", "fumble.exe")


def find_binary() -> str | None:
    """Locate the compiled `fumble` CLI, or None if it has not been built."""
    override = os.environ.get("FOMOTH_FUMBLE_BIN")
    candidates = [Path(override)] if override else []
    for base in (_ROOT / "build" / "core", _ROOT / "build", _ROOT / "core" / "build"):
        candidates += [base / name for name in _BIN_NAMES]
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return shutil.which("fumble")


def available() -> bool:
    """Whether the native core is built and runnable."""
    return find_binary() is not None


def regret_native(tokens, timeout: float = 60.0) -> dict | None:
    """Run the C++ core over the given tokens.

    `tokens` is an iterable of mappings, each with:
        mint:   str
        series: sequence of (ts_seconds, high, close), sorted ascending by ts
        sells:  sequence of (ts_seconds, tokens_sold)

    Returns the parsed report dict, or None if the binary is unavailable.
    """
    binary = find_binary()
    if not binary:
        return None

    tokens = list(tokens)
    lines = [str(len(tokens))]
    for tok in tokens:
        series = list(tok.get("series") or [])
        sells = list(tok.get("sells") or [])
        lines.append(f"{tok['mint']} {len(series)} {len(sells)}")
        for ts, high, close in series:
            lines.append(f"{int(ts)} {float(high):.10g} {float(close):.10g}")
        for ts, amount in sells:
            lines.append(f"{int(ts)} {float(amount):.10g}")
    payload = "\n".join(lines) + "\n"

    proc = subprocess.run(
        [binary], input=payload, capture_output=True, text=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise RuntimeError(f"fumble core failed ({proc.returncode}): {proc.stderr.strip()}")
    return json.loads(proc.stdout)
