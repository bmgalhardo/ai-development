"""The commands, as a hand-run session sees them."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from overmind import cli
from overmind.runner import container


class CommandTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        subprocess.run(["git", "init", "-q", str(self.root / "project")], check=True)
        issues = self.root / ".scratch/project/2026-10-22-test/issues"
        issues.mkdir(parents=True)
        for name, status in (("01-first", "done"), ("02-second", "open"), ("03-build", "open")):
            (issues / f"{name}.md").write_text(f"**Status:** {status}\n**Blocked by:** 01\n")
        patcher = patch.dict(os.environ, {"OVERMIND_ROOT": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_command(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            cli.main(list(args))
        return output.getvalue()

    def test_next_prints_the_ready_issue_relative_to_the_root(self):
        self.assertEqual(self.run_command("next", "project"),
                         ".scratch/project/2026-10-22-test/issues/02-second.md\n")

    def test_next_prints_nothing_when_no_issue_is_ready(self):
        for name in ("02-second", "03-build"):
            path = self.root / f".scratch/project/2026-10-22-test/issues/{name}.md"
            path.write_text("**Status:** done\n")
        self.assertEqual(self.run_command("next", "project"), "")

    def test_status_lists_every_issue(self):
        self.assertEqual(self.run_command("status", "project"),
                         "01  done         01-first.md\n02  open         02-second.md\n"
                         "03  open         03-build.md (build)\n")

    def test_next_names_a_stuck_cycle_and_fails(self):
        path = self.root / ".scratch/project/2026-10-22-test/issues/02-second.md"
        path.write_text("**Status:** open\n**Blocked by:** 03\n")
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(cli.main(["next", "project"]), 1)
        self.assertIn("Stuck: 02 waits for 03; 03 waits for 02", error.getvalue())

    def test_a_tracker_error_exits_with_its_message(self):
        with self.assertRaisesRegex(SystemExit, "is not a git repo"):
            self.run_command("next", "missing")

    def test_a_hand_opened_shell_runs_through_the_wrapper(self):
        binaries = self.root / "bin"
        binaries.mkdir()
        docker = binaries / "docker"
        docker.write_text(f"#!{sys.executable}\n" + Path(__file__).with_name("fake_docker.py").read_text())
        docker.chmod(0o755)
        (self.root / ".logins").mkdir()
        (self.root / ".logins/.claude.login").write_text("setup-token\n")
        log = self.root / "docker.jsonl"
        environment = os.environ | {"PATH": f"{binaries}:{os.environ['PATH']}", "FAKE_DOCKER_LOG": str(log)}
        shell = subprocess.run([str(Path(container.__file__).with_name("run.sh")), "claude", "review",
                                str(self.root / "project"), "sh", "-c", "echo token $CLAUDE_CODE_OAUTH_TOKEN"],
                               env=environment, capture_output=True, text=True)
        self.assertEqual((shell.returncode, shell.stdout), (0, "token setup-token\n"), shell.stderr)
        run = json.loads(log.read_text().splitlines()[1])["args"]
        self.assertEqual(run[0], "run")
        self.assertIn(f"{self.root}/project:{self.root}/project:ro", run)

    def test_invalid_settings_exit_with_the_setting_named(self):
        with patch.dict(os.environ, {"OVERMIND_WAIT": "0"}):
            with self.assertRaisesRegex(SystemExit, "OVERMIND_WAIT"):
                self.run_command("status", "project")


if __name__ == "__main__":
    unittest.main()
