"""Settings from the environment and `.env`, with defaults and validation."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from legion.settings import Settings, SettingsError


class SettingsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        clean = {key: value for key, value in os.environ.items() if not key.upper().startswith("WORK_")}
        patcher = patch.dict(os.environ, clean | {"WORK_ROOT": str(self.root)}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def load(self, env_file="", **environment):
        (self.root / ".env").write_text(env_file)
        with patch.dict(os.environ, environment):
            return Settings.load()

    def test_the_env_file_is_the_workflow_roots(self):
        settings = self.load("WORK_WAIT=60\n")
        self.assertEqual((settings.root, settings.wait), (self.root, 60))

    def test_defaults(self):
        settings = self.load()
        self.assertEqual((settings.wait, settings.timeout, settings.budget_usd), (1800, 14400, 15))
        self.assertFalse(settings.container)
        self.assertTrue(settings.dashboard)
        self.assertEqual((settings.dashboard_host, settings.dashboard_port), ("127.0.0.1", 8765))
        self.assertEqual(settings.after_build, "")
        self.assertEqual(settings.logins_folder, settings.root / ".logins")

    def test_the_environment_wins_over_the_env_file(self):
        settings = self.load("WORK_WAIT=60\nWORK_TIMEOUT=90\n", WORK_WAIT="30")
        self.assertEqual((settings.wait, settings.timeout), (30, 90))

    def test_unknown_work_keys_in_the_env_file_are_ignored(self):
        settings = self.load("WORK_AGENT=claude\nWORK_PUBLISH=0\nPUBLISH_URL=https://publish.test\n")
        self.assertEqual(settings.wait, 1800)

    def test_preference_is_a_comma_list_of_known_providers(self):
        self.assertEqual(self.load(WORK_PREFERENCE="codex, claude").preference, ["codex", "claude"])
        self.assertEqual(self.load(WORK_PREFERENCE="claude").preference, ["claude"])

    def test_an_unset_preference_is_every_installed_provider_claude_first(self):
        with patch("legion.providers.shutil.which", side_effect=lambda name: f"/bin/{name}"):
            self.assertEqual(self.load().preference, ["claude", "codex"])
        with patch("legion.providers.shutil.which", side_effect=lambda name: "/bin/codex" if name == "codex" else None):
            self.assertEqual(self.load().preference, ["codex"])

    def test_invalid_values_fail_with_the_setting_named(self):
        for name, value, message in (("WORK_PREFERENCE", "claude,gemini", "unknown provider gemini"),
                                     ("WORK_PREFERENCE", "claude,claude", "claude more than once"),
                                     ("WORK_WAIT", "0", "greater than 0"),
                                     ("WORK_DASHBOARD_PORT", "port", "integer")):
            with self.subTest(name=name, value=value):
                with self.assertRaisesRegex(SettingsError, f"{name}: .*{message}"):
                    self.load(**{name: value})

    def test_unknown_nested_keys_in_the_env_file_are_ignored(self):
        settings = self.load("WORK_CODEX__REWIEW__MODEL=gpt\nWORK_CLAUDE__IMPLEMENT__MODLE=opus\n")
        self.assertIsNone(settings.roles("claude").role("implement").model)

    def test_an_unparsable_nested_value_is_an_error(self):
        with self.assertRaisesRegex(SettingsError, "Invalid settings"):
            self.load(WORK_CLAUDE__IMPLEMENT="not json")

    def test_model_and_effort_per_provider_and_role(self):
        settings = self.load("WORK_CODEX__REVIEW__EFFORT=high\n", WORK_CLAUDE__IMPLEMENT__MODEL="opus",
                             WORK_CLAUDE__REVIEW__MODEL="sonnet")
        claude, codex = settings.roles("claude"), settings.roles("codex")
        self.assertEqual((claude.role("implement").model, claude.role("implement").effort), ("opus", "medium"))
        self.assertEqual((claude.role("review").model, claude.role("review").effort), ("sonnet", "medium"))
        self.assertEqual((codex.role("review").model, codex.role("review").effort), (None, "high"))
        self.assertEqual(codex.role("implement").model, None)

    def test_fix_falls_back_to_implement_for_each_unset_field(self):
        settings = self.load(WORK_CLAUDE__IMPLEMENT__MODEL="opus", WORK_CLAUDE__IMPLEMENT__EFFORT="high",
                             WORK_CLAUDE__FIX__MODEL="sonnet")
        fix = settings.roles("claude").role("fix")
        self.assertEqual((fix.model, fix.effort), ("sonnet", "high"))
        self.assertEqual(settings.roles("codex").role("fix").effort, "medium")

    def test_effort_is_one_of_the_providers_own_values(self):
        self.assertEqual(self.load(WORK_CLAUDE__IMPLEMENT__EFFORT="max").roles("claude").role("implement").effort,
                         "max")
        with self.assertRaisesRegex(SettingsError, "WORK_CODEX__REVIEW__EFFORT: max is not one of"):
            self.load(WORK_CODEX__REVIEW__EFFORT="max")

    def test_container_switch_accepts_one_and_zero(self):
        self.assertTrue(self.load(WORK_CONTAINER="1").container)
        self.assertFalse(self.load(WORK_DASHBOARD="0").dashboard)


if __name__ == "__main__":
    unittest.main()
