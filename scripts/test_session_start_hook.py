import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK_PATH = ROOT / "hooks" / "session_start.py"
HOOK_CONFIG_PATH = ROOT / "hooks" / "hooks.json"
SPEC = importlib.util.spec_from_file_location("quota_session_start", HOOK_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SessionStartHookTests(unittest.TestCase):
    def test_hook_runs_asynchronously_for_startup_and_resume(self):
        config = json.loads(HOOK_CONFIG_PATH.read_text(encoding="utf-8"))
        group = config["hooks"]["SessionStart"][0]
        handler = group["hooks"][0]
        self.assertEqual(group["matcher"], "^(startup|resume)$")
        self.assertEqual(handler["type"], "command")
        self.assertTrue(handler["async"])
        self.assertIn("${PLUGIN_ROOT}/hooks/session_start.py", handler["command"])

    def test_non_macos_session_does_not_try_to_launch(self):
        with (
            mock.patch.object(MODULE.sys, "platform", "linux"),
            mock.patch.object(MODULE, "menu_bar_is_running") as running,
            mock.patch.object(MODULE, "start_menu_bar") as start,
        ):
            self.assertEqual(MODULE.main(), 0)
        running.assert_not_called()
        start.assert_not_called()

    def test_running_menu_bar_is_not_started_again(self):
        with (
            mock.patch.object(MODULE.sys, "platform", "darwin"),
            mock.patch.object(MODULE, "menu_bar_is_running", return_value=True),
            mock.patch.object(MODULE, "start_menu_bar") as start,
        ):
            self.assertEqual(MODULE.main(), 0)
        start.assert_not_called()

    def test_start_menu_bar_uses_launcher_from_plugin_root(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0)

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            launcher = root / "scripts" / "launch_menu_bar.py"
            launcher.parent.mkdir()
            launcher.touch()
            self.assertEqual(MODULE.start_menu_bar(root, fake_run), 0)

        self.assertEqual(calls[0][0], ["/usr/bin/python3", str(launcher)])
        self.assertEqual(calls[0][1]["cwd"], root)
        self.assertFalse(calls[0][1]["check"])

    def test_missing_launcher_is_a_safe_noop(self):
        run = mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(MODULE.start_menu_bar(pathlib.Path(directory), run), 0)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
