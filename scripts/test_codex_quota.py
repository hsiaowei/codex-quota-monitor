#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone


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

    def test_show_email(self):
        output = MODULE.render_markdown(FIXTURE, show_email=True)
        self.assertIn("example.user@example.com", output)

if __name__ == "__main__":
    unittest.main()
