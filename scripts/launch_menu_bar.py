#!/usr/bin/env python3
"""Build and launch the native Codex quota menu bar app."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
APP_BUNDLE = PLUGIN_ROOT / "dist" / "CodexQuotaMenu.app"
BUILD_SCRIPT = PLUGIN_ROOT / "scripts" / "build_menu_bar_app.sh"


def build_if_needed(rebuild: bool) -> None:
    executable = APP_BUNDLE / "Contents" / "MacOS" / "CodexQuotaMenu"
    if executable.exists() and not rebuild:
        return
    result = subprocess.run([str(BUILD_SCRIPT)], cwd=PLUGIN_ROOT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"菜单栏应用构建失败（退出码 {result.returncode}）。")


def launch(rebuild: bool) -> int:
    build_if_needed(rebuild)
    result = subprocess.run(["open", str(APP_BUNDLE)], check=False)
    if result.returncode != 0:
        print(f"无法打开 Codex 额度菜单栏（退出码 {result.returncode}）。", file=sys.stderr)
        return 2
    print("已打开 Codex 额度菜单栏。点击顶部的“C …%”可以展开或收起额度面板。")
    return 0


def stop() -> int:
    result = subprocess.run(["pkill", "-x", "CodexQuotaMenu"], check=False)
    if result.returncode == 0:
        print("已关闭 Codex 额度菜单栏。")
    else:
        print("Codex 额度菜单栏当前没有运行。")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动或关闭 Codex 额度菜单栏")
    parser.add_argument("--stop", action="store_true", help="关闭菜单栏应用")
    parser.add_argument("--rebuild", action="store_true", help="强制重新构建原生应用")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return stop() if args.stop else launch(args.rebuild)
    except (OSError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

