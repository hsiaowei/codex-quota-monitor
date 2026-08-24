#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).with_name("codex_quota.py")
SPEC = importlib.util.spec_from_file_location("codex_quota", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)



FIXTURE = {
    "account": {
        "account": {
            "type": "chatgpt",
            "email": "example.user@example.com",
            "planType": "plus",
        },
        "requiresOpenaiAuth": True,
    },
    "limits": {
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": 94,
                "windowDurationMins": 10080,
                "resetsAt": 1786324692,
            },
            "planType": "plus",
            "credits": {"hasCredits": False, "unlimited": False, "balance": "0"},
        },
        "rateLimitsByLimitId": {
            "codex": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 94,
                    "windowDurationMins": 10080,
                    "resetsAt": 1786324692,
                },
                "planType": "plus",
            }
        },
        "rateLimitResetCredits": {"availableCount": 1, "credits": []},
    },
    "usage": {
        "summary": {"lifetimeTokens": 1234567},
        "dailyUsageBuckets": [
            {"startDate": "2026-08-09", "tokens": 1200},
            {"startDate": "2026-08-10", "tokens": 45678},
        ],
    },
    "todayWeeklyQuota": {
        "usedPercent": 5,
        "trackingStartedAt": 1786147200,
        "lastObservedAt": 1786147200,
        "isEstimate": True,
    },
    "fetchedAt": 1786147200,
}


class QuotaTests(unittest.TestCase):
    def test_extracts_weekly_window(self):
        windows = MODULE.extract_windows(FIXTURE["limits"])
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].duration_minutes, 10080)
        self.assertEqual(windows[0].remaining_percent, 6)

    def test_markdown_uses_real_percent_and_masks_email(self):
        output = MODULE.render_markdown(FIXTURE)
        self.assertIn("周额度", output)
        self.assertIn("剩余 6%", output)
        self.assertIn("ex*****@example.com", output)
        self.assertNotIn("example.user@example.com", output)
        self.assertIn("可用额度重置券：**1 次**", output)
        self.assertIn("今日周额度消耗：**约 5%**", output)

    def test_daily_weekly_quota_accumulates_only_positive_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = pathlib.Path(temp_dir) / "daily-quota.json"
            first = datetime(2026, 8, 19, 8, tzinfo=timezone.utc)
            result = MODULE.record_daily_weekly_quota_usage(20, now=first, cache_path=cache)
            self.assertEqual(result["usedPercent"], 0)

            result = MODULE.record_daily_weekly_quota_usage(
                23, now=first.replace(hour=9), cache_path=cache
            )
            self.assertEqual(result["usedPercent"], 3)

            result = MODULE.record_daily_weekly_quota_usage(
                21, now=first.replace(hour=10), cache_path=cache
            )
            self.assertEqual(result["usedPercent"], 3)

            result = MODULE.record_daily_weekly_quota_usage(
                25, now=first.replace(hour=11), cache_path=cache
            )
            self.assertEqual(result["usedPercent"], 7)

    def test_daily_weekly_quota_resets_on_next_local_day(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = pathlib.Path(temp_dir) / "daily-quota.json"
            first = datetime(2026, 8, 19, 8, tzinfo=timezone.utc).astimezone()
            MODULE.record_daily_weekly_quota_usage(20, now=first, cache_path=cache)
            MODULE.record_daily_weekly_quota_usage(24, now=first.replace(hour=17), cache_path=cache)
            next_day = first.replace(day=20, hour=8)
            result = MODULE.record_daily_weekly_quota_usage(26, now=next_day, cache_path=cache)
            self.assertEqual(result["usedPercent"], 0)
            self.assertEqual(result["trackingStartedAt"], int(next_day.timestamp()))

    def test_build_today_weekly_quota_requires_exact_week_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = pathlib.Path(temp_dir) / "daily-quota.json"
            result = MODULE.build_today_weekly_quota_usage(FIXTURE["limits"], cache_path=cache)
            self.assertIsNotNone(result)
            limits = deepcopy(FIXTURE["limits"])
            limits["rateLimits"]["primary"]["windowDurationMins"] = 300
            limits["rateLimitsByLimitId"]["codex"]["primary"]["windowDurationMins"] = 300
            self.assertIsNone(MODULE.build_today_weekly_quota_usage(limits, cache_path=cache))

    def test_extracts_official_tokens_from_exact_date_bucket(self):
        tokens = MODULE.extract_today_tokens(FIXTURE["usage"], day="2026-08-10")
        self.assertEqual(tokens, 45678)

    def test_missing_usage_is_unknown_not_zero(self):
        self.assertIsNone(MODULE.extract_today_tokens(None, day="2026-08-10"))

    def test_missing_day_in_available_buckets_is_unknown(self):
        tokens = MODULE.extract_today_tokens(FIXTURE["usage"], day="2026-08-11")
        self.assertIsNone(tokens)

    def test_local_token_events_are_summed_by_event_day(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions = pathlib.Path(temp_dir)
            log = sessions / "rollout.jsonl"
            records = [
                {
                    "timestamp": "2026-08-10T02:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "token_count", "info": {"last_token_usage": {"total_tokens": 25000}}},
                },
                {
                    "timestamp": "2026-08-10T03:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "token_count", "info": {"last_token_usage": {"total_tokens": 20474}}},
                },
            ]
            log.write_text("\n".join(__import__("json").dumps(item) for item in records) + "\n", encoding="utf-8")
            tokens = MODULE.read_local_tokens_for_day(datetime(2026, 8, 10, tzinfo=timezone.utc).astimezone().date(), sessions)
            self.assertEqual(tokens, 45474)

    def test_default_scan_includes_archived_sessions_and_deduplicates_moved_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = pathlib.Path(temp_dir)
            sessions = codex_home / "sessions"
            archived = codex_home / "archived_sessions"
            sessions.mkdir()
            archived.mkdir()
            shared = '{"timestamp":"2026-08-10T02:00:00Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":25000}}}}\n'
            (sessions / "rollout-shared.jsonl").write_text(shared, encoding="utf-8")
            (archived / "rollout-shared.jsonl").write_text(shared, encoding="utf-8")
            (archived / "rollout-archived.jsonl").write_text(
                '{"timestamp":"2026-08-10T03:00:00Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":20474}}}}\n',
                encoding="utf-8",
            )
            target = datetime(2026, 8, 10, tzinfo=timezone.utc).astimezone().date()
            with patch.dict("os.environ", {"CODEX_HOME": str(codex_home)}):
                tokens = MODULE.read_local_tokens_for_day(target)
            self.assertEqual(tokens, 45474)

    def test_local_token_cache_survives_session_disappearing_after_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            sessions = root / "sessions"
            sessions.mkdir()
            cache = root / "daily-local-token-cache.json"
            log = sessions / "rollout-before-restart.jsonl"
            log.write_text(
                '{"timestamp":"2026-08-10T02:00:00Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":50000}}}}\n',
                encoding="utf-8",
            )
            target = datetime(2026, 8, 10, tzinfo=timezone.utc).astimezone().date()
            before = MODULE.read_local_tokens_for_day(target, sessions, cache_path=cache)
            log.unlink()
            after = MODULE.read_local_tokens_for_day(target, sessions, cache_path=cache)
            self.assertEqual(before, 50000)
            self.assertEqual(after, 50000)

    def test_local_token_cache_adds_cumulative_growth_after_log_truncation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            sessions = root / "sessions"
            sessions.mkdir()
            cache = root / "daily-local-token-cache.json"
            log = sessions / "rollout-resumed.jsonl"
            log.write_text(
                '{"timestamp":"2026-08-10T02:00:00Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":50000},"total_token_usage":{"total_tokens":100000}}}}\n',
                encoding="utf-8",
            )
            target = datetime(2026, 8, 10, tzinfo=timezone.utc).astimezone().date()
            self.assertEqual(MODULE.read_local_tokens_for_day(target, sessions, cache_path=cache), 50000)
            log.write_text(
                '{"timestamp":"2026-08-10T03:00:00Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":20000},"total_token_usage":{"total_tokens":120000}}}}\n',
                encoding="utf-8",
            )
            self.assertEqual(MODULE.read_local_tokens_for_day(target, sessions, cache_path=cache), 70000)

    def test_weekend_comparison_falls_back_to_friday(self):
        target, fallback = MODULE.previous_reporting_day(datetime(2026, 8, 10).date())
        self.assertEqual(target.isoformat(), "2026-08-07")
        self.assertTrue(fallback)

    def test_usage_stats_mix_official_history_with_local_today(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions = pathlib.Path(temp_dir)
            log = sessions / "rollout.jsonl"
            log.write_text(
                '{"timestamp":"2026-08-10T02:00:00Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":50000}}}}\n',
                encoding="utf-8",
            )
            stats = MODULE.build_usage_stats(
                FIXTURE["usage"],
                now=datetime(2026, 8, 10, 10, tzinfo=timezone.utc).astimezone(),
                sessions_root=sessions,
            )
            self.assertEqual(stats["comparisonDate"], "2026-08-07")
            self.assertIsNone(stats["comparisonTokens"])
            self.assertEqual(stats["weekTokens"], 50000)
            self.assertEqual(stats["monthTokens"], 51200)

    def test_wan_format_rounds_half_up_to_one_decimal(self):
        self.assertEqual(MODULE._format_tokens_wan(455474), "45.5万")
        self.assertEqual(MODULE._format_tokens_wan(10500), "1.1万")

    def test_token_format_switches_to_yi_and_wan_at_one_hundred_million(self):
        self.assertEqual(MODULE._format_tokens_wan(99_999_499), "9999.9万")
        self.assertEqual(MODULE._format_tokens_wan(100_000_000), "1亿")
        self.assertEqual(MODULE._format_tokens_wan(123_456_000), "1亿2345.6万")
        self.assertEqual(MODULE._format_tokens_wan(199_999_999), "2亿")
        self.assertEqual(MODULE._format_tokens_wan(200_352_000), "2亿35.2万")
        self.assertEqual(MODULE._format_tokens_wan(1_234_567_000), "12亿3456.7万")

    def test_live_official_usage_is_cached_and_reused_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            cache = root / "official.json"
            sessions = root / "sessions"
            sessions.mkdir()
            now = datetime(2026, 8, 10, 10, tzinfo=timezone.utc).astimezone()
            live_usage = {
                "dailyUsageBuckets": [
                    {"startDate": "2026-08-07", "tokens": 120000},
                    {"startDate": "2026-08-09", "tokens": 30000},
                ]
            }
            fresh = MODULE.build_usage_stats(live_usage, now=now, sessions_root=sessions, cache_path=cache)
            self.assertTrue(cache.is_file())
            self.assertFalse(fresh["officialIsCached"])
            self.assertIsNone(fresh["officialCacheFetchedAt"])

            cached = MODULE.build_usage_stats(None, now=now, sessions_root=sessions, cache_path=cache)
            self.assertTrue(cached["officialIsCached"])
            self.assertEqual(cached["officialCacheFetchedAt"], int(now.timestamp()))
            self.assertEqual(cached["comparisonTokens"], 120000)
            self.assertEqual(cached["monthOfficialTokens"], 150000)

    def test_first_run_without_official_cache_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            sessions = root / "sessions"
            sessions.mkdir()
            stats = MODULE.build_usage_stats(
                None,
                now=datetime(2026, 8, 10, 10, tzinfo=timezone.utc).astimezone(),
                sessions_root=sessions,
                cache_path=root / "missing-cache.json",
            )
            self.assertIsNone(stats["comparisonTokens"])
            self.assertIsNone(stats["weekOfficialTokens"])
            self.assertIsNone(stats["monthOfficialTokens"])
            self.assertFalse(stats["officialIsCached"])

    def test_live_recovery_clears_cached_state_and_replaces_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            cache = root / "official.json"
            sessions = root / "sessions"
            sessions.mkdir()
            first_now = datetime(2026, 8, 10, 9, tzinfo=timezone.utc).astimezone()
            second_now = datetime(2026, 8, 10, 10, tzinfo=timezone.utc).astimezone()
            MODULE.build_usage_stats(
                {"dailyUsageBuckets": [{"startDate": "2026-08-07", "tokens": 100000}]},
                now=first_now,
                sessions_root=sessions,
                cache_path=cache,
            )
            recovered = MODULE.build_usage_stats(
                {"dailyUsageBuckets": [{"startDate": "2026-08-07", "tokens": 200000}]},
                now=second_now,
                sessions_root=sessions,
                cache_path=cache,
            )
            self.assertFalse(recovered["officialIsCached"])
            self.assertEqual(recovered["comparisonTokens"], 200000)
            cached, fetched_at = MODULE._load_official_usage_cache(cache)
            self.assertEqual(cached[datetime(2026, 8, 7).date()], 200000)
            self.assertEqual(fetched_at, int(second_now.timestamp()))

    def test_week_and_month_show_official_and_today_separately(self):
        data = deepcopy(FIXTURE)
        data["usageStats"] = {
            "todayTokens": 501000,
            "comparisonDate": "2026-08-07",
            "comparisonLabel": "上周五",
            "comparisonTokens": 100000,
            "weekOfficialTokens": 1501000,
            "monthOfficialTokens": 3501000,
        }
        output = MODULE.render_markdown(data)
        self.assertIn("本周 Tokens：**150.1万（官方历史） + 50.1万（今日实时）**", output)
        self.assertIn("本月 Tokens：**350.1万（官方历史） + 50.1万（今日实时）**", output)

    def test_cached_markdown_marks_only_official_values_and_shows_cache_time_once(self):
        data = deepcopy(FIXTURE)
        data["usageStats"] = {
            "todayTokens": 501000,
            "comparisonDate": "2026-08-07",
            "comparisonLabel": "上周五",
            "comparisonTokens": 100000,
            "weekOfficialTokens": 1501000,
            "monthOfficialTokens": 3501000,
            "officialIsCached": True,
            "officialCacheFetchedAt": 1786328431,
        }
        output = MODULE.render_markdown(data)
        self.assertIn("ⓘ（数据缓存时间", output)
        self.assertEqual(output.count("数据缓存时间"), 1)
        self.assertIn("**🟡 150.1万（官方历史） + 50.1万（今日实时）**", output)
        self.assertIn("今日 Tokens（本机实时）：**50.1万**", output)

    def test_no_cache_markdown_shows_unknown_official_values(self):
        data = deepcopy(FIXTURE)
        data["usageStats"] = {
            "todayTokens": 501000,
            "comparisonDate": "2026-08-07",
            "comparisonLabel": "上周五",
            "comparisonTokens": None,
            "weekOfficialTokens": None,
            "monthOfficialTokens": None,
            "officialIsCached": False,
        }
        output = MODULE.render_markdown(data)
        self.assertIn("上周五 Tokens（官方 · 2026-08-07）：**暂无数据**", output)
        self.assertIn("本周 Tokens：**暂无数据（官方历史） + 50.1万（今日实时）**", output)
        self.assertNotIn("数据缓存时间", output)

    def test_show_email(self):
        output = MODULE.render_markdown(FIXTURE, show_email=True)
        self.assertIn("example.user@example.com", output)

if __name__ == "__main__":
    unittest.main()
