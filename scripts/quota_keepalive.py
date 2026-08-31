#!/usr/bin/env python3
"""Anchor unused Codex quota windows with one minimal non-interactive request."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


RETRY_COOLDOWN_SECONDS = 15 * 60
DEFAULT_STATE_PATH = (
    Path.home() / ".codex" / "codex-quota-monitor" / "quota-keepalive.json"
)
KEEPALIVE_PROMPT = "不要调用任何工具，只回复 OK。"


@dataclass(frozen=True)
class QuotaWindow:
    name: str
    remaining: float
    resets_at: float | None


def find_codex() -> str | None:
    configured = os.environ.get("CODEX_QUOTA_CODEX_PATH")
    candidates = [
        configured,
        shutil.which("codex"),
        "/usr/local/bin/codex",
        "/opt/homebrew/bin/codex",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def build_exec_command(codex: str) -> list[str]:
    return [
        codex,
        "exec",
        "--json",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--color",
        "never",
        "-C",
        tempfile.gettempdir(),
        KEEPALIVE_PROMPT,
    ]


def thread_id_from_jsonl(output: str) -> str | None:
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(event, dict) or event.get("type") != "thread.started":
            continue
        thread_id = event.get("thread_id") or event.get("threadId")
        if isinstance(thread_id, str) and thread_id:
            return thread_id
    return None


def consume_tokens(codex: str | None = None) -> bool:
    executable = codex or find_codex()
    if not executable:
        return False
    try:
        result = subprocess.run(
            build_exec_command(executable),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False

    thread_id = thread_id_from_jsonl(result.stdout)
    if thread_id:
        try:
            subprocess.run(
                [executable, "archive", thread_id],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    return True


def load_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def eligible_windows(windows: Sequence[QuotaWindow]) -> list[QuotaWindow]:
    return [window for window in windows if window.remaining >= 99.9995]


def run_once(
    windows: Sequence[QuotaWindow],
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    now: float | None = None,
    consumer: Callable[[], bool] = consume_tokens,
) -> str:
    current_time = time.time() if now is None else now
    full_windows = eligible_windows(windows)
    if not full_windows:
        return "not-needed"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = load_state(state_path)
        window_states = state.get("windows")
        if not isinstance(window_states, dict):
            window_states = {}
        eligible = []
        for window in full_windows:
            window_state = window_states.get(window.name)
            suppress_until = (
                window_state.get("suppressUntil")
                if isinstance(window_state, dict)
                else None
            )
            if not isinstance(suppress_until, (int, float)) or current_time >= suppress_until:
                eligible.append(window)
        if not eligible:
            return "cooldown"
        for window in eligible:
            window_states[window.name] = {
                "lastAttemptAt": current_time,
                "suppressUntil": current_time + RETRY_COOLDOWN_SECONDS,
            }
        state["version"] = 1
        state["windows"] = window_states
        state["lastAttemptAt"] = current_time
        state["lastReasons"] = [window.name for window in eligible]
        save_state(state_path, state)

    succeeded = consumer()
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = load_state(state_path)
        window_states = state.get("windows")
        if not isinstance(window_states, dict):
            window_states = {}
        state["version"] = 1
        state["lastAttemptAt"] = current_time
        state["lastReasons"] = [window.name for window in eligible]
        for window in eligible:
            window_state = window_states.get(window.name)
            if not isinstance(window_state, dict):
                window_state = {}
            window_state["lastAttemptAt"] = current_time
            if succeeded:
                window_state["lastSuccessAt"] = current_time
                window_state["suppressUntil"] = max(
                    current_time + RETRY_COOLDOWN_SECONDS,
                    window.resets_at
                    if isinstance(window.resets_at, (int, float))
                    and window.resets_at > current_time
                    else 0,
                )
                window_state.pop("lastFailureAt", None)
            else:
                window_state["lastFailureAt"] = current_time
                window_state["suppressUntil"] = (
                    current_time + RETRY_COOLDOWN_SECONDS
                )
            window_states[window.name] = window_state
        state["windows"] = window_states
        if succeeded:
            state["lastSuccessAt"] = current_time
            state.pop("lastFailureAt", None)
        else:
            state["lastFailureAt"] = current_time
        save_state(state_path, state)
    return "triggered" if succeeded else "failed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="维持 Codex 空额度窗口的固定重置时间")
    parser.add_argument("--weekly-remaining", type=float)
    parser.add_argument("--weekly-resets-at", type=float)
    parser.add_argument("--five-hour-remaining", type=float)
    parser.add_argument("--five-hour-resets-at", type=float)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.environ.get("CODEX_QUOTA_KEEPALIVE", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return 0

    windows = []
    if args.weekly_remaining is not None:
        windows.append(
            QuotaWindow("weekly", args.weekly_remaining, args.weekly_resets_at)
        )
    if args.five_hour_remaining is not None:
        windows.append(
            QuotaWindow("five-hour", args.five_hour_remaining, args.five_hour_resets_at)
        )
    result = run_once(windows, state_path=args.state_path)
    print(result)
    return 0 if result != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
