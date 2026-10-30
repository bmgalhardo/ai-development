"""Each provider's commands, log parsing, failure kinds and reset times."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import legion
from legion.providers import registry
from legion.settings import Settings

PROMPT = "Implement the issue."


def settings(**values):
    """Settings from these values alone, ignoring the environment and `.env`."""
    clean = {key: value for key, value in os.environ.items() if not key.upper().startswith("LEGION_")}
    with patch.dict(os.environ, clean, clear=True):
        return Settings(_env_file=None, **values)


def provider(name, **values):
    return registry.provider(name, settings(**values))


class CommandTests(unittest.TestCase):
    def test_claude_commands_per_role(self):
        claude = provider("claude", claude={"implement": {"model": "opus"}})
        base = ["claude", "-p", "--permission-mode", "auto", "--output-format", "json",
                "--add-dir", "/work/project", "--max-budget-usd", "15"]
        self.assertEqual(claude.command("implement", PROMPT, Path("/work/project")),
                         base + ["--model", "opus", "--effort", "medium", PROMPT])
        self.assertEqual(claude.command("review", PROMPT, Path("/work/project")),
                         base + ["--disallowedTools=Edit,Write,NotebookEdit", "--effort", "medium", PROMPT])
        self.assertEqual(claude.command("fix", PROMPT, Path("/work/project")),
                         base + ["--model", "opus", "--effort", "medium", PROMPT])

    def test_codex_commands_per_role(self):
        codex = provider("codex", codex={"review": {"model": "gpt-review", "effort": "high"}})
        base = ["codex", "exec", "-c", 'approval_policy="never"', "--color", "never", "--json"]
        effort = ["-c", 'model_reasoning_effort="medium"']
        self.assertEqual(codex.command("implement", PROMPT, Path("/p")),
                         base + ["--sandbox", "danger-full-access"] + effort + [PROMPT])
        self.assertEqual(codex.command("review", PROMPT, Path("/p")),
                         base + ["--sandbox", "read-only", "--model", "gpt-review",
                                 "-c", 'model_reasoning_effort="high"', PROMPT])

    def test_codex_in_a_container_reviews_with_full_access_and_skips_the_repo_check(self):
        codex = provider("codex", container=True)
        command = codex.command("review", PROMPT, Path("/p"))
        self.assertIn("danger-full-access", command)
        self.assertNotIn("read-only", command)
        self.assertIn("--skip-git-repo-check", command)

    def test_the_budget_goes_to_claude_only(self):
        self.assertIn("2.5", provider("claude", budget_usd=2.5).command("implement", PROMPT, Path("/p")))
        self.assertNotIn("--max-budget-usd", provider("codex").command("implement", PROMPT, Path("/p")))


class ClaudeOnlyTests(unittest.TestCase):
    def test_deleting_the_codex_file_leaves_a_working_claude_registry(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "legion"
            shutil.copytree(Path(legion.__file__).parent, package, ignore=shutil.ignore_patterns("__pycache__"))
            (package / "providers/codex.py").unlink()
            script = (
                "import os\n"
                "from pathlib import Path\n"
                "from legion.providers import registry\n"
                "from legion.settings import Settings, SettingsError\n"
                "print(registry.names())\n"
                "os.environ['LEGION_PREFERENCE'] = 'claude'\n"
                "settings = Settings.load()\n"
                "print(settings.preference)\n"
                "print(registry.provider('claude', settings).command('review', 'p', Path('/p'))[0])\n"
                "os.environ['LEGION_PREFERENCE'] = 'claude,codex'\n"
                "try:\n"
                "    Settings.load()\n"
                "except SettingsError as error:\n"
                "    print('rejected' if 'unknown provider codex' in str(error) else error)\n"
            )
            environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("LEGION_")}
            environment |= {"PYTHONPATH": temp, "LEGION_ROOT": temp}
            output = subprocess.run([sys.executable, "-c", script], cwd=temp, env=environment,
                                    capture_output=True, text=True, check=True).stdout
        self.assertEqual(output.splitlines(), ["('claude',)", "['claude']", "claude", "rejected"])


class LogTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.log = Path(temp.name) / "output.log"

    def parse(self, name, *lines):
        self.log.write_text("\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines) + "\n")
        return provider(name).parse_log(self.log)

    def test_claude_expired_login_is_authentication(self):
        result = self.parse("claude", {"type": "result", "is_error": True, "terminal_reason": "api_error",
                                       "result": "Failed to authenticate: OAuth session expired "
                                                 "and could not be refreshed"})
        self.assertEqual(provider("claude").classify(result.messages), "authentication")
        self.assertEqual(result.report, "")

    def test_claude_structured_api_error_is_quota_without_limit_text(self):
        result = self.parse("claude", {"type": "result", "is_error": True, "api_error": "usage_limit_reached",
                                       "result": "Request could not complete"})
        self.assertEqual(provider("claude").classify(result.messages), "quota")

    def test_claude_result_gives_the_report_and_usage(self):
        result = self.parse("claude", "a diagnostic line",
                            {"type": "result", "result": "## Spec\nNo findings.", "usage": {"input_tokens": 100},
                             "total_cost_usd": 0.5, "num_turns": 3})
        self.assertEqual(result.report, "## Spec\nNo findings.")
        self.assertEqual(result.usage, [{"usage": {"input_tokens": 100}, "total_cost_usd": 0.5, "num_turns": 3}])
        self.assertIn("a diagnostic line", result.messages)

    def test_codex_limit_event_is_quota_with_a_reset_time(self):
        text = "You’ve hit your usage limit. Try again at 1:53 PM."
        codex = provider("codex")
        result = self.parse("codex", "Reading additional input from stdin...", {"type": "error", "message": text},
                            {"type": "turn.failed", "error": {"message": text}})
        self.assertEqual(codex.classify(result.messages), "quota")
        self.assertGreater(codex.reset_at(result.messages, 60), time.time())

    def test_codex_last_agent_message_is_the_report(self):
        result = self.parse("codex", {"type": "item.completed", "item": {"type": "agent_message", "text": "first"}},
                            {"type": "item.completed", "item": {"type": "agent_message", "text": " last "}},
                            {"type": "turn.completed", "usage": {"input_tokens": 25, "output_tokens": 5}})
        self.assertEqual(result.report, "last")
        self.assertEqual(result.usage, [{"input_tokens": 25, "output_tokens": 5}])

    def test_tool_output_does_not_count_as_quota(self):
        result = self.parse("codex", {"type": "item.completed", "item": {
            "type": "command_execution", "aggregated_output": "usage limit reached 429"}})
        self.assertEqual(provider("codex").classify(result.messages), "failure")


class FailureTests(unittest.TestCase):
    def test_limit_messages_are_quota(self):
        for name in registry.names():
            for message in ("You've hit your limit", "You've hit your usage limit",
                            "You've hit your session limit · resets 4am (Europe/Lisbon)",
                            "You have reached your weekly limit",
                            "You’ve hit your usage limit. Upgrade to Pro or try again at 4:52 AM."):
                with self.subTest(provider=name, message=message):
                    self.assertEqual(provider(name).classify(message), "quota")

    def test_other_messages_are_failures(self):
        self.assertEqual(provider("claude").classify("Implementation check failed"), "failure")


class ResetTests(unittest.TestCase):
    def test_claude_zoned_reset_and_next_day(self):
        claude = provider("claude")
        now = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)
        self.assertEqual(datetime.fromtimestamp(claude.reset_at("resets 4pm (America/Los_Angeles)", 60, now),
                                                timezone.utc),
                         datetime(2026, 10, 22, 23, 0, 30, tzinfo=timezone.utc))
        self.assertEqual(datetime.fromtimestamp(claude.reset_at("resets 9pm (UTC)", 60, now), timezone.utc),
                         datetime(2026, 10, 23, 21, 0, 30, tzinfo=timezone.utc))

    def test_time_only_reset_uses_local_time(self):
        now = datetime(2026, 10, 25, 3, 6, tzinfo=timezone.utc)
        for name in registry.names():
            with self.subTest(provider=name):
                reset = provider(name).reset_at("try again at 4:52 AM.", 60, now)
                self.assertEqual(datetime.fromtimestamp(reset, timezone.utc),
                                 datetime(2026, 10, 25, 4, 52, 30, tzinfo=timezone.utc))
                reset = provider(name).reset_at("try again at 2:00 AM.", 60, now)
                self.assertEqual(datetime.fromtimestamp(reset, timezone.utc),
                                 datetime(2026, 10, 26, 2, 0, 30, tzinfo=timezone.utc))

    def test_every_provider_reads_every_reset_format(self):
        now = datetime(2026, 10, 25, 3, 6, tzinfo=timezone.utc)
        for name in registry.names():
            for message, expected in (("Try again at Oct 31st, 2026 4:52 PM.", datetime(2026, 10, 31, 16, 52, 30)),
                                      ("resets 9pm (UTC)", datetime(2026, 10, 25, 21, 0, 30))):
                with self.subTest(provider=name, message=message):
                    reset = provider(name).reset_at(message, 60, now)
                    self.assertEqual(datetime.fromtimestamp(reset, timezone.utc),
                                     expected.replace(tzinfo=timezone.utc))

    def test_unknown_reset_and_malformed_time_use_fallback(self):
        now = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)
        for message in ("resets tomorrow", "resets 99pm (UTC)", "resets 9pm (Unknown/Zone)"):
            with self.subTest(message=message):
                self.assertEqual(provider("claude").reset_at(message, 60, now), now.timestamp() + 60)


if __name__ == "__main__":
    unittest.main()
