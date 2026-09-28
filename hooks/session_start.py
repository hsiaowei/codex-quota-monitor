#!/usr/bin/env python3
"""Start the native quota menu bar app for a local Codex session."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable


RunCommand = Callable[..., subprocess.CompletedProcess]


def resolve_plugin_root() -> Path:
    configured = os.environ.get("PLUGIN_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def menu_bar_is_running(run_command: RunCommand = subprocess.run) -> bool:
    try:
        result = run_command(
            ["/usr/bin/pgrep", "-x", "CodexQuotaMenu"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def start_menu_bar(
    plugin_root: Path | None = None,
    run_command: RunCommand = subprocess.run,
) -> int:
    root = plugin_root or resolve_plugin_root()
    launcher = root / "scripts" / "launch_menu_bar.py"
    if not launcher.is_file():
        return 0

    try:
        run_command(
            ["/usr/bin/python3", str(launcher)],
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        # Auto-start must never block or fail the Codex session itself.
        return 0
    return 0


def main() -> int:
    if sys.platform != "darwin" or menu_bar_is_running():
        return 0
    return start_menu_bar()


if __name__ == "__main__":
    raise SystemExit(main())
