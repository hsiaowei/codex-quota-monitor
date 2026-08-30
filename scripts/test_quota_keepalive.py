#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).with_name("quota_keepalive.py")
SPEC = importlib.util.spec_from_file_location("quota_keepalive", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class QuotaKeepaliveTests(unittest.TestCase):
    def state_path(self, directory: str) -> pathlib.Path:
        return pathlib.Path(directory) / "quota-keepalive.json"

    def test_does_not_consume_below_one_hundred_percent_remaining(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            result = MODULE.run_once(
                [MODULE.QuotaWindow("weekly", 99, 9000)],
                state_path=self.state_path(directory),
                now=1000,
                consumer=lambda: calls.append(True) or True,
            )
            self.assertEqual(result, "not-needed")
            self.assertEqual(calls, [])

    def test_weekly_one_hundred_consumes_once_until_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.state_path(directory)
            calls = []
            window = MODULE.QuotaWindow("weekly", 100, 8000)
            first = MODULE.run_once(
                [window], state_path=path, now=1000, consumer=lambda: calls.append(True) or True
            )
            second = MODULE.run_once(
                [window], state_path=path, now=1300, consumer=lambda: calls.append(True) or True
            )
            self.assertEqual(first, "triggered")
            self.assertEqual(second, "cooldown")
            self.assertEqual(len(calls), 1)
            state = json.loads(path.read_text())
            self.assertEqual(state["windows"]["weekly"]["suppressUntil"], 8000)

    def test_two_full_windows_share_one_request_and_keep_separate_resets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.state_path(directory)
            calls = []
            result = MODULE.run_once(
                [
                    MODULE.QuotaWindow("weekly", 100, 9000),
                    MODULE.QuotaWindow("five-hour", 100, 4000),
                ],
                state_path=path,
                now=1000,
                consumer=lambda: calls.append(True) or True,
            )
            state = json.loads(path.read_text())
            self.assertEqual(result, "triggered")
            self.assertEqual(len(calls), 1)
            self.assertEqual(state["lastReasons"], ["weekly", "five-hour"])
            self.assertEqual(state["windows"]["weekly"]["suppressUntil"], 9000)
            self.assertEqual(state["windows"]["five-hour"]["suppressUntil"], 4000)

    def test_weekly_cooldown_does_not_block_new_five_hour_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.state_path(directory)
            calls = []
            both = [
                MODULE.QuotaWindow("weekly", 100, 9000),
                MODULE.QuotaWindow("five-hour", 100, 4000),
            ]
            MODULE.run_once(
                both,
                state_path=path,
                now=1000,
                consumer=lambda: calls.append(True) or True,
            )
            result = MODULE.run_once(
                [
                    MODULE.QuotaWindow("weekly", 99, 9000),
                    MODULE.QuotaWindow("five-hour", 100, 7000),
                ],
                state_path=path,
                now=4100,
                consumer=lambda: calls.append(True) or True,
            )
            self.assertEqual(result, "triggered")
            self.assertEqual(len(calls), 2)
            state = json.loads(path.read_text())
            self.assertEqual(state["windows"]["weekly"]["suppressUntil"], 9000)
            self.assertEqual(state["windows"]["five-hour"]["suppressUntil"], 7000)

    def test_failed_request_retries_after_fifteen_minutes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.state_path(directory)
            window = MODULE.QuotaWindow("five-hour", 100, 9000)
            self.assertEqual(
                MODULE.run_once(
                    [window], state_path=path, now=1000, consumer=lambda: False
                ),
                "failed",
            )
            self.assertEqual(
                MODULE.run_once(
                    [window], state_path=path, now=1500, consumer=lambda: True
                ),
                "cooldown",
            )
            self.assertEqual(
                MODULE.run_once(
                    [window], state_path=path, now=1900, consumer=lambda: True
                ),
                "triggered",
            )

    def test_exec_is_read_only_persistent_and_archived(self):
        started = json.dumps(
            {"type": "thread.started", "thread_id": "12345678-1234-1234-1234-123456789abc"}
        )
        responses = [
            subprocess.CompletedProcess([], 0, stdout=started + "\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        ]
        with patch.object(MODULE.subprocess, "run", side_effect=responses) as run:
            self.assertTrue(MODULE.consume_tokens("/usr/local/bin/codex"))
        exec_command = run.call_args_list[0].args[0]
        archive_command = run.call_args_list[1].args[0]
        self.assertIn("--json", exec_command)
        self.assertIn("read-only", exec_command)
        self.assertIn("--skip-git-repo-check", exec_command)
        self.assertIn("--ignore-user-config", exec_command)
        self.assertNotIn("--ephemeral", exec_command)
        self.assertEqual(
            archive_command,
            [
                "/usr/local/bin/codex",
                "archive",
                "12345678-1234-1234-1234-123456789abc",
            ],
        )


if __name__ == "__main__":
    unittest.main()
