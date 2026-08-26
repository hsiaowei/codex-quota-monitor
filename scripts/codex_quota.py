#!/usr/bin/env python3
"""Read live Codex quota windows through the local Codex app-server."""

from __future__ import annotations

import argparse
import json
import os
import selectors
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


CLIENT_VERSION = "0.7.3"
DEFAULT_TIMEOUT_SECONDS = 20.0
CACHE_VERSION = 1
DAILY_QUOTA_CACHE_VERSION = 1
LOCAL_TOKEN_CACHE_VERSION = 1


class QuotaError(RuntimeError):
    """A user-facing quota retrieval error."""


@dataclass(frozen=True)
class Window:
    limit_id: str
    limit_name: str | None
    kind: str
    used_percent: float
    duration_minutes: int
    resets_at: int

    @property
    def remaining_percent(self) -> float:
        return max(0.0, min(100.0, 100.0 - self.used_percent))


def _send(proc: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    if proc.stdin is None:
        raise QuotaError("Codex app-server 标准输入不可用。")
    proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    proc.stdin.flush()


def _read_responses(
    proc: subprocess.Popen[str], wanted_ids: set[int], deadline: float
) -> dict[int, dict[str, Any]]:
    if proc.stdout is None:
        raise QuotaError("Codex app-server 标准输出不可用。")

    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    responses: dict[int, dict[str, Any]] = {}
    try:
        while wanted_ids - responses.keys():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                missing = ", ".join(str(item) for item in sorted(wanted_ids - responses.keys()))
                raise QuotaError(f"等待 Codex 额度接口超时（缺少响应 {missing}）。")
            events = selector.select(remaining)
            if not events:
                continue
            line = proc.stdout.readline()
            if not line:
                code = proc.poll()
                raise QuotaError(f"Codex app-server 意外退出（退出码 {code}）。")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            response_id = message.get("id")
            if response_id in wanted_ids:
                responses[response_id] = message
    finally:
        selector.close()
    return responses


def _result(response: dict[str, Any], label: str) -> dict[str, Any]:
    if "error" in response:
        error = response["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise QuotaError(f"{label}失败：{message}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise QuotaError(f"{label}返回了无法识别的数据。")
    return result


def fetch_live_data(timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    codex = shutil.which("codex")
    if not codex:
        for candidate in ("/usr/local/bin/codex", "/opt/homebrew/bin/codex"):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                codex = candidate
                break
    if not codex:
        raise QuotaError("找不到 codex 命令，请先安装或更新 Codex CLI。")

    proc = subprocess.Popen(
        [codex, "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=os.environ.copy(),
    )
    deadline = time.monotonic() + timeout_seconds
    try:
        _send(
            proc,
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": "codex_quota_monitor",
                        "title": "Codex Quota Monitor",
                        "version": CLIENT_VERSION,
                    }
                },
            },
        )
        initialized = _read_responses(proc, {0}, deadline)
        _result(initialized[0], "初始化 Codex app-server")
        _send(proc, {"method": "initialized", "params": {}})
        _send(
            proc,
            {
                "method": "account/read",
                "id": 1,
                "params": {"refreshToken": False},
            },
        )
        _send(proc, {"method": "account/rateLimits/read", "id": 2})
        _send(proc, {"method": "account/usage/read", "id": 3})
        responses = _read_responses(proc, {1, 2, 3}, deadline)
        usage_response = responses[3]
        usage_result = usage_response.get("result")
        return {
            "account": _result(responses[1], "读取 Codex 账号"),
            "limits": _result(responses[2], "读取 Codex 额度"),
            "usage": usage_result if isinstance(usage_result, dict) else None,
            "usageError": usage_response.get("error") if usage_result is None else None,
            "fetchedAt": int(time.time()),
        }
    except BrokenPipeError as exc:
        raise QuotaError("无法与 Codex app-server 通信。") from exc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _codex_bucket(limits_result: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    by_id = limits_result.get("rateLimitsByLimitId")
    if isinstance(by_id, dict) and by_id:
        exact = by_id.get("codex")
        if isinstance(exact, dict):
            return "codex", exact
        for fallback_id, bucket in by_id.items():
            if not isinstance(bucket, dict):
                continue
            limit_id = str(bucket.get("limitId") or fallback_id)
            if limit_id.casefold() == "codex":
                return limit_id, bucket

    single = limits_result.get("rateLimits")
    if isinstance(single, dict):
        limit_id = single.get("limitId")
        if limit_id is None or str(limit_id).casefold() == "codex":
            return "codex", single

    if isinstance(limits_result.get("primary"), dict) or isinstance(
        limits_result.get("secondary"), dict
    ):
        limit_id = limits_result.get("limitId")
        if limit_id is not None and str(limit_id).casefold() == "codex":
            return "codex", limits_result

    return None


def extract_windows(limits_result: dict[str, Any]) -> list[Window]:
    selected = _codex_bucket(limits_result)
    if selected is None:
        return []
    fallback_id, bucket = selected

    windows: list[Window] = []
    limit_id = str(bucket.get("limitId") or fallback_id)
    limit_name = bucket.get("limitName")
    for kind in ("primary", "secondary"):
        window = bucket.get(kind)
        if not isinstance(window, dict):
            continue
        used = _number(window.get("usedPercent"))
        duration = _number(window.get("windowDurationMins"))
        resets_at = _number(window.get("resetsAt"))
        if used is None or duration is None or resets_at is None:
            continue
        windows.append(
            Window(
                limit_id=limit_id,
                limit_name=str(limit_name) if limit_name else None,
                kind=kind,
                used_percent=max(0.0, min(100.0, used)),
                duration_minutes=max(0, int(duration)),
                resets_at=int(resets_at),
            )
        )
    return sorted(windows, key=lambda item: (item.duration_minutes, item.kind))


def _mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return "未提供"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked = local[:1] + "*"
    else:
        masked = local[:2] + "*" * min(5, len(local) - 2)
    return f"{masked}@{domain}"


def _format_percent(value: float) -> str:
    rounded = round(value, 1)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.1f}"


def _bar(remaining_percent: float, width: int = 20) -> str:
    filled = round(width * remaining_percent / 100.0)
    return "█" * filled + "░" * (width - filled)


def _window_label(minutes: int) -> str:
    if minutes == 300:
        return "5 小时额度"
    if minutes == 10_080:
        return "周额度"
    if minutes % 10_080 == 0 and minutes:
        return f"{minutes // 10_080} 周窗口"
    if minutes % 1_440 == 0 and minutes:
        return f"{minutes // 1_440} 天窗口"
    if minutes % 60 == 0 and minutes:
        return f"{minutes // 60} 小时窗口"
    return f"{minutes} 分钟窗口"


def _local_datetime(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp).astimezone()


def extract_official_daily_tokens(usage_result: Any) -> dict[date, int]:
    if not isinstance(usage_result, dict):
        return {}
    buckets = usage_result.get("dailyUsageBuckets")
    if not isinstance(buckets, list):
        return {}
    result: dict[date, int] = {}
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        try:
            bucket_day = date.fromisoformat(str(bucket.get("startDate")))
        except (TypeError, ValueError):
            continue
        tokens = bucket.get("tokens")
        if isinstance(tokens, bool) or not isinstance(tokens, (int, float)):
            continue
        result[bucket_day] = max(0, int(tokens))
    return result


def official_usage_cache_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return codex_home / "codex-quota-monitor" / "official-usage-cache.json"


def daily_weekly_quota_cache_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return codex_home / "codex-quota-monitor" / "daily-weekly-quota-cache.json"


def local_token_cache_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return codex_home / "codex-quota-monitor" / "daily-local-token-cache.json"


def _load_daily_weekly_quota_cache(cache_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("version") != DAILY_QUOTA_CACHE_VERSION:
        return {}
    return payload


def record_daily_weekly_quota_usage(
    current_used_percent: float,
    *,
    now: datetime | None = None,
    cache_path: Path | None = None,
) -> dict[str, Any]:
    """Accumulate positive official weekly used-percent changes for the local day."""
    local_now = (now or datetime.now().astimezone()).astimezone()
    observed_at = int(local_now.timestamp())
    today = local_now.date().isoformat()
    current = max(0.0, min(100.0, float(current_used_percent)))
    target = cache_path or daily_weekly_quota_cache_path()
    previous = _load_daily_weekly_quota_cache(target)

    same_day = previous.get("day") == today
    raw_accumulated = previous.get("accumulatedIncreasePercent") if same_day else None
    raw_last = previous.get("lastUsedPercent") if same_day else None
    raw_started = previous.get("trackingStartedAt") if same_day else None
    accumulated = (
        max(0.0, float(raw_accumulated))
        if isinstance(raw_accumulated, (int, float)) and not isinstance(raw_accumulated, bool)
        else 0.0
    )
    last = (
        max(0.0, min(100.0, float(raw_last)))
        if isinstance(raw_last, (int, float)) and not isinstance(raw_last, bool)
        else None
    )
    started_at = (
        int(raw_started)
        if isinstance(raw_started, (int, float)) and not isinstance(raw_started, bool)
        else observed_at
    )
    if last is not None and current > last:
        accumulated += current - last

    payload = {
        "version": DAILY_QUOTA_CACHE_VERSION,
        "day": today,
        "trackingStartedAt": started_at,
        "lastObservedAt": observed_at,
        "lastUsedPercent": current,
        "accumulatedIncreasePercent": accumulated,
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        pass
    return {
        "usedPercent": accumulated,
        "trackingStartedAt": started_at,
        "lastObservedAt": observed_at,
        "source": "official_weekly_used_percent_changes",
        "isEstimate": True,
    }


def build_today_weekly_quota_usage(
    limits_result: Any,
    *,
    now: datetime | None = None,
    cache_path: Path | None = None,
) -> dict[str, Any] | None:
    if not isinstance(limits_result, dict):
        return None
    weekly = next((window for window in extract_windows(limits_result) if window.duration_minutes == 10_080), None)
    if weekly is None:
        return None
    return record_daily_weekly_quota_usage(
        weekly.used_percent,
        now=now,
        cache_path=cache_path,
    )


def _load_official_usage_cache(cache_path: Path) -> tuple[dict[date, int], int | None]:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, None
    if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
        return {}, None
    raw_daily = payload.get("dailyUsageTokens")
    fetched_at = payload.get("fetchedAt")
    if not isinstance(raw_daily, dict) or isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)):
        return {}, None
    daily: dict[date, int] = {}
    for raw_day, raw_tokens in raw_daily.items():
        try:
            parsed_day = date.fromisoformat(str(raw_day))
        except ValueError:
            continue
        if isinstance(raw_tokens, bool) or not isinstance(raw_tokens, (int, float)):
            continue
        daily[parsed_day] = max(0, int(raw_tokens))
    return daily, int(fetched_at) if daily else None


def _save_official_usage_cache(cache_path: Path, daily: dict[date, int], fetched_at: int) -> None:
    payload = {
        "version": CACHE_VERSION,
        "fetchedAt": fetched_at,
        "dailyUsageTokens": {day.isoformat(): tokens for day, tokens in sorted(daily.items())},
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, cache_path)
    except OSError:
        # Cache failures must never prevent live quota data from being displayed.
        return


def resolve_official_daily_tokens(
    usage_result: Any,
    *,
    cache_path: Path | None = None,
    fetched_at: int | None = None,
) -> tuple[dict[date, int], bool, int | None]:
    live = extract_official_daily_tokens(usage_result)
    if live:
        cache_time = int(fetched_at or time.time())
        if cache_path is not None:
            _save_official_usage_cache(cache_path, live, cache_time)
        return live, False, None
    if cache_path is not None:
        cached, cache_time = _load_official_usage_cache(cache_path)
        if cached:
            return cached, True, cache_time
    return {}, False, None


def extract_today_tokens(usage_result: Any, day: str | None = None) -> int | None:
    """Compatibility helper for callers that need an exact official day bucket."""
    target = date.fromisoformat(day) if day else date.today()
    return extract_official_daily_tokens(usage_result).get(target)


def _parse_event_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone()


def _load_local_token_cache(cache_path: Path, target: date) -> tuple[dict[str, int], dict[str, int]]:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {}
    if (
        not isinstance(payload, dict)
        or payload.get("version") != LOCAL_TOKEN_CACHE_VERSION
        or payload.get("day") != target.isoformat()
    ):
        return {}, {}
    raw_sessions = payload.get("sessionTokens")
    if not isinstance(raw_sessions, dict):
        return {}, {}
    session_tokens = {
        str(session_id): max(0, int(tokens))
        for session_id, tokens in raw_sessions.items()
        if isinstance(session_id, str)
        and not isinstance(tokens, bool)
        and isinstance(tokens, (int, float))
    }
    raw_cumulative = payload.get("sessionCumulativeTokens")
    session_cumulative = {
        str(session_id): max(0, int(tokens))
        for session_id, tokens in raw_cumulative.items()
        if isinstance(session_id, str)
        and not isinstance(tokens, bool)
        and isinstance(tokens, (int, float))
    } if isinstance(raw_cumulative, dict) else {}
    return session_tokens, session_cumulative


def _save_local_token_cache(
    cache_path: Path,
    target: date,
    session_tokens: dict[str, int],
    session_cumulative: dict[str, int],
) -> None:
    payload = {
        "version": LOCAL_TOKEN_CACHE_VERSION,
        "day": target.isoformat(),
        "updatedAt": int(time.time()),
        "sessionTokens": dict(sorted(session_tokens.items())),
        "sessionCumulativeTokens": dict(sorted(session_cumulative.items())),
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, cache_path)
    except OSError:
        pass


def read_local_tokens_for_day(
    target: date,
    sessions_root: Path | None = None,
    *,
    archived_sessions_root: Path | None = None,
    cache_path: Path | None = None,
) -> int | None:
    """Sum local token events without losing completed sessions across a Codex restart."""
    if sessions_root is None:
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
        sessions_root = codex_home / "sessions"
        archived_sessions_root = codex_home / "archived_sessions"
        if cache_path is None:
            cache_path = local_token_cache_path()

    roots = [sessions_root]
    if archived_sessions_root is not None:
        roots.append(archived_sessions_root)
    roots = [root for index, root in enumerate(roots) if root not in roots[:index]]
    found_root = any(root.is_dir() for root in roots)
    if not found_root and cache_path is None:
        return None

    day_start = datetime.combine(target, datetime_time.min).astimezone()
    session_tokens: dict[str, int] = {}
    session_cumulative: dict[str, int] = {}
    seen_events: set[tuple[str, str, int]] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                if path.stat().st_mtime < day_start.timestamp():
                    continue
                session_id = path.name
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(record, dict) or record.get("type") != "event_msg":
                            continue
                        raw_timestamp = record.get("timestamp")
                        event_time = _parse_event_datetime(raw_timestamp)
                        if event_time is None or event_time.date() != target:
                            continue
                        payload = record.get("payload")
                        if not isinstance(payload, dict) or payload.get("type") != "token_count":
                            continue
                        info = payload.get("info")
                        last = info.get("last_token_usage") if isinstance(info, dict) else None
                        tokens = last.get("total_tokens") if isinstance(last, dict) else None
                        if isinstance(tokens, bool) or not isinstance(tokens, (int, float)):
                            continue
                        amount = max(0, int(tokens))
                        event_key = (session_id, str(raw_timestamp), amount)
                        if event_key in seen_events:
                            continue
                        seen_events.add(event_key)
                        session_tokens[session_id] = session_tokens.get(session_id, 0) + amount
                        cumulative = info.get("total_token_usage") if isinstance(info, dict) else None
                        cumulative_tokens = cumulative.get("total_tokens") if isinstance(cumulative, dict) else None
                        if (
                            not isinstance(cumulative_tokens, bool)
                            and isinstance(cumulative_tokens, (int, float))
                        ):
                            session_cumulative[session_id] = max(
                                session_cumulative.get(session_id, 0),
                                max(0, int(cumulative_tokens)),
                            )
            except OSError:
                continue

    if cache_path is not None:
        cached_tokens, cached_cumulative = _load_local_token_cache(cache_path, target)
        for session_id in cached_tokens.keys() | session_tokens.keys():
            previous_tokens = cached_tokens.get(session_id, 0)
            previous_cumulative = cached_cumulative.get(session_id)
            current_cumulative = session_cumulative.get(session_id)
            cumulative_growth = (
                max(0, current_cumulative - previous_cumulative)
                if current_cumulative is not None and previous_cumulative is not None
                else 0
            )
            session_tokens[session_id] = max(
                session_tokens.get(session_id, 0),
                previous_tokens + cumulative_growth,
            )
        for session_id, previous_cumulative in cached_cumulative.items():
            session_cumulative[session_id] = max(
                session_cumulative.get(session_id, 0),
                previous_cumulative,
            )
        _save_local_token_cache(cache_path, target, session_tokens, session_cumulative)

    if not found_root and not session_tokens:
        return None
    return sum(session_tokens.values())


def previous_reporting_day(today: date) -> tuple[date, bool]:
    target = today - timedelta(days=1)
    weekend_fallback = target.weekday() >= 5
    while target.weekday() >= 5:
        target -= timedelta(days=1)
    return target, weekend_fallback


def build_usage_stats(
    usage_result: Any,
    *,
    now: datetime | None = None,
    sessions_root: Path | None = None,
    cache_path: Path | None = None,
) -> dict[str, Any]:
    local_now = (now or datetime.now().astimezone()).astimezone()
    today = local_now.date()
    official, official_is_cached, official_cache_fetched_at = resolve_official_daily_tokens(
        usage_result,
        cache_path=cache_path,
        fetched_at=int(local_now.timestamp()),
    )
    today_local = read_local_tokens_for_day(today, sessions_root=sessions_root)
    comparison_day, weekend_fallback = previous_reporting_day(today)

    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    official_week = sum(tokens for day, tokens in official.items() if week_start <= day < today)
    official_month = sum(tokens for day, tokens in official.items() if month_start <= day < today)
    has_official = bool(official)
    week_tokens = official_week + today_local if has_official and today_local is not None else None
    month_tokens = official_month + today_local if has_official and today_local is not None else None

    return {
        "todayDate": today.isoformat(),
        "todayTokens": today_local,
        "todaySource": "local_session_events",
        "comparisonDate": comparison_day.isoformat(),
        "comparisonLabel": "上周五" if weekend_fallback else "昨日",
        "comparisonTokens": official.get(comparison_day),
        "comparisonSource": "official_daily_usage",
        "weekStartDate": week_start.isoformat(),
        "weekTokens": week_tokens,
        "weekOfficialTokens": official_week if has_official else None,
        "monthStartDate": month_start.isoformat(),
        "monthTokens": month_tokens,
        "monthOfficialTokens": official_month if has_official else None,
        "aggregateSource": "official_history_plus_local_today",
        "officialLatestDate": max(official).isoformat() if official else None,
        "officialIsCached": official_is_cached,
        "officialCacheFetchedAt": official_cache_fetched_at,
    }


def _format_tokens_wan(value: int) -> str:
    wan = (Decimal(value) / Decimal(10_000)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if value >= 100_000_000:
        yi = int(wan // Decimal(10_000))
        remainder_wan = wan - Decimal(yi * 10_000)
        if remainder_wan == 0:
            return f"{yi}亿"
        return f"{yi}亿{remainder_wan:.1f}万"
    return f"{wan:.1f}万"


def _countdown(timestamp: int, now: int) -> str:
    seconds = max(0, timestamp - now)
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes = seconds // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days}天")
    if hours or days:
        parts.append(f"{hours}小时")
    parts.append(f"{minutes}分")
    return " ".join(parts)


def _plan_and_credits(limits_result: dict[str, Any], windows: list[Window]) -> tuple[str, dict[str, Any] | None]:
    selected = _codex_bucket(limits_result)
    candidates = [selected[1]] if selected is not None else []

    plan = "未知"
    credits = None
    for bucket in candidates:
        if plan == "未知" and bucket.get("planType"):
            plan = str(bucket["planType"])
        if credits is None and isinstance(bucket.get("credits"), dict):
            credits = bucket["credits"]
    return plan, credits


def render_markdown(data: dict[str, Any], show_email: bool = False) -> str:
    account_result = data.get("account", {})
    account = account_result.get("account") if isinstance(account_result, dict) else None
    if not isinstance(account, dict):
        raise QuotaError("Codex 当前没有已登录的 ChatGPT 账号。")
    if account.get("type") not in {"chatgpt", "chatgptAuthTokens", "agentIdentity", "personalAccessToken"}:
        raise QuotaError("当前认证方式不提供 ChatGPT Codex 额度；请使用 ChatGPT 账号登录。")

    limits_result = data.get("limits", {})
    if not isinstance(limits_result, dict):
        raise QuotaError("Codex 额度数据格式无效。")
    windows = extract_windows(limits_result)
    if not windows:
        raise QuotaError("Codex 没有返回可显示的额度窗口。")

    email = account.get("email")
    account_label = str(email) if show_email and email else _mask_email(email)
    plan, credits = _plan_and_credits(limits_result, windows)
    if plan == "未知" and account.get("planType"):
        plan = str(account["planType"])

    fetched_at = int(data.get("fetchedAt") or time.time())
    stats = data.get("usageStats")
    if not isinstance(stats, dict):
        stats = build_usage_stats(data.get("usage"))
    today_tokens = stats.get("todayTokens")
    comparison_tokens = stats.get("comparisonTokens")
    week_official_tokens = stats.get("weekOfficialTokens")
    month_official_tokens = stats.get("monthOfficialTokens")
    comparison_label = stats.get("comparisonLabel") or "昨日"
    comparison_date = stats.get("comparisonDate") or "--"
    official_is_cached = stats.get("officialIsCached") is True
    cache_fetched_at = stats.get("officialCacheFetchedAt")
    cache_suffix = ""
    if official_is_cached and isinstance(cache_fetched_at, (int, float)):
        cache_time = _local_datetime(int(cache_fetched_at))
        cache_suffix = f" ⓘ（数据缓存时间{cache_time:%m-%d %H:%M:%S}）"
    official_marker = "🟡 " if official_is_cached else ""
    comparison_value = _format_tokens_wan(comparison_tokens) if isinstance(comparison_tokens, int) else "暂无数据"
    week_official_value = _format_tokens_wan(week_official_tokens) if isinstance(week_official_tokens, int) else "暂无数据"
    month_official_value = _format_tokens_wan(month_official_tokens) if isinstance(month_official_tokens, int) else "暂无数据"
    today_value = _format_tokens_wan(today_tokens) if isinstance(today_tokens, int) else "暂无数据"
    today_weekly_quota = data.get("todayWeeklyQuota")
    today_weekly_used = today_weekly_quota.get("usedPercent") if isinstance(today_weekly_quota, dict) else None
    weekly_consumption_suffix = (
        f"（今日消耗：约{_format_percent(float(today_weekly_used))}%）"
        if isinstance(today_weekly_used, (int, float)) and not isinstance(today_weekly_used, bool)
        else "（今日消耗：暂无数据）"
    )
    lines = [
        "## Codex 实际额度",
        "",
        f"账号：{account_label}　|　套餐：{plan}",
        f"今日 Tokens（本机实时）：**{_format_tokens_wan(today_tokens)}**" if isinstance(today_tokens, int) else "今日 Tokens（本机实时）：**暂无数据**",
        f"{comparison_label} Tokens（官方 · {comparison_date}）：**{official_marker}{comparison_value}**{cache_suffix}",
        f"本周 Tokens：**{official_marker}{week_official_value}（官方历史） + {today_value}（今日实时）**",
        f"本月 Tokens：**{official_marker}{month_official_value}（官方历史） + {today_value}（今日实时）**",
        "",
    ]

    for window in windows:
        label = _window_label(window.duration_minutes)
        if window.duration_minutes == 10_080:
            label += weekly_consumption_suffix
        remaining = window.remaining_percent
        reset = _local_datetime(window.resets_at)
        zone = reset.tzname() or "本地时间"
        bucket_label = window.limit_name or window.limit_id
        lines.extend(
            [
                f"### {label}",
                "",
                f"`{_bar(remaining)}`  **剩余 {_format_percent(remaining)}%**（已用 {_format_percent(window.used_percent)}%）",
                "",
                f"- 刷新时间：{reset:%Y-%m-%d %H:%M:%S} {zone}",
                f"- 刷新倒计时：{_countdown(window.resets_at, fetched_at)}",
                f"- 额度桶：{bucket_label}",
                "",
            ]
        )

    reset_info = limits_result.get("rateLimitResetCredits")
    if isinstance(reset_info, dict) and isinstance(reset_info.get("availableCount"), int):
        lines.append(f"可用额度重置券：**{reset_info['availableCount']} 次**（仅显示，不会自动使用）")

    if credits is not None:
        if credits.get("unlimited") is True:
            lines.append("额外 credits：无限")
        elif credits.get("hasCredits") is True or credits.get("balance") not in (None, ""):
            lines.append(f"额外 credits 余额：{credits.get('balance', '未知')}")

    fetched = _local_datetime(fetched_at)
    lines.extend(
        [
            "",
            f"数据获取时间：{fetched:%Y-%m-%d %H:%M:%S} {fetched.tzname() or '本地时间'}",
            "",
            "> 今日 Tokens 来自本机 Codex 会话的实时 token 事件；周额度标题中的“今日消耗”累计官方周额度百分比的上涨量，滚动释放造成的下降不扣减，因此标记为“约”。对比日来自官方每日活动桶。本周和本月为“官方历史 + 本机今日”，不包含其他设备尚未回传的当日数据。",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="显示真实 Codex 额度与刷新时间")
    parser.add_argument("--json", action="store_true", help="输出官方接口原始 JSON")
    parser.add_argument("--show-email", action="store_true", help="显示完整账号邮箱")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="等待 app-server 响应的秒数（默认 20）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = fetch_live_data(max(1.0, args.timeout))
        data["usageStats"] = build_usage_stats(data.get("usage"), cache_path=official_usage_cache_path())
        data["todayWeeklyQuota"] = build_today_weekly_quota_usage(
            data.get("limits"),
            cache_path=daily_weekly_quota_cache_path(),
        )
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(render_markdown(data, show_email=args.show_email))
        return 0
    except QuotaError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("错误：操作已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
