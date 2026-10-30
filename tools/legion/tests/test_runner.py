"""The worker loop end to end, with real temporary git repos and fake provider CLIs on PATH."""

from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from legion.runner import loop
from legion.runner.loop import Launch, Runner, RunnerError
from legion.runner.repo import Repo, UnsafeRepoError
from legion.runner.sessions import TIMED_OUT, Sessions
from legion.settings import Settings

FAKE_WORKER = Path(__file__).with_name("fake_worker.py")


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.project = self.root / "project"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        (self.project / "code.txt").write_text("original\n")
        Repo(self.project).git("add", "code.txt")
        Repo(self.project).git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base")
        self.cycle = self.root / ".scratch/project/2026-10-22-test"
        (self.cycle / "issues").mkdir(parents=True)
        self.issue = self.cycle / "issues/01-feature.md"
        self.issue.write_text("**Status:** open\n**Blocked by:** None\n")
        self.directory = self.root / ".scratch/project/runner"
        self.directory.mkdir(parents=True)
        self.cooldowns = self.root / ".scratch/runner/cooldowns.json"
        binaries = self.root / "bin"
        binaries.mkdir()
        for provider in ("claude", "codex"):
            executable = binaries / provider
            executable.write_text(f"#!{sys.executable}\n" + FAKE_WORKER.read_text())
            executable.chmod(0o755)
        clean = {key: value for key, value in os.environ.items() if not key.upper().startswith("WORK_")}
        self.stack.enter_context(patch.dict(os.environ, clean | {
            "PATH": f"{binaries}:{os.environ['PATH']}", "WORK_ROOT": str(self.root),
            "WORK_PREFERENCE": "claude,codex", "WORK_CLAUDE__IMPLEMENT__MODEL": "test-claude",
            "WORK_WAIT": "60", "WORK_DASHBOARD": "0"}, clear=True))
        self.lock = self.stack.enter_context((self.directory / "runner.lock").open("a"))

    def run_loop(self, **environment):
        with patch.dict(os.environ, environment):
            return Runner(Settings.load(), self.project, self.lock.fileno()).run()

    def records(self):
        return [json.loads(line) for line in (self.cycle / "work/attempts.jsonl").read_text().splitlines()]

    def calls(self):
        return [json.loads(line) for line in (self.root / "calls.jsonl").read_text().splitlines()]

    def add_build_issue(self):
        build = self.cycle / "issues/02-build.md"
        build.write_text("**Status:** open\n**Blocked by:** 01\n")
        return build

    # Today's scenarios

    def test_quota_handoff_preserves_work_and_keeps_models_per_provider(self):
        self.assertEqual(self.run_loop(), 0)
        records = self.records()
        self.assertEqual([r["outcome"] for r in records], ["quota", "done"])
        self.assertEqual([r["provider"] for r in records], ["claude", "codex"])
        self.assertEqual(records[0]["usage"][0]["usage"]["input_tokens"], 100)
        self.assertEqual(records[1]["usage"][0]["input_tokens"], 25)
        self.assertEqual((records[0]["model"], records[0]["effort"]), ("test-claude", "medium"))
        calls = self.calls()
        self.assertIn("test-claude", calls[0]["args"])
        self.assertNotIn("--model", calls[1]["args"])
        recovery = Path(records[0]["recovery"])
        self.assertIn("unfinished tracked work", (recovery / "changes.patch").read_text())
        with tarfile.open(recovery / "untracked.tar") as archive:
            self.assertEqual(archive.extractfile("new.txt").read(), b"unfinished untracked work\n")
        self.assertGreater(json.loads(self.cooldowns.read_text())["claude"], 0)

    def test_the_record_keeps_todays_fields_and_adds_effort(self):
        self.run_loop()
        records = self.records()
        self.assertEqual([r["outcome"] for r in records], ["quota", "done"])
        for record in records:
            self.assertEqual(list(record),
                             ["attempt", "issue", "role", "axis", "provider", "model", "effort", "review_model",
                              "started_at", "log", "exit_code", "outcome", "duration_seconds", "usage", "recovery"])
        self.assertIsNone(records[1]["recovery"])

    def test_persisted_cooldown_skips_provider_on_restart(self):
        self.cooldowns.parent.mkdir(parents=True)
        self.cooldowns.write_text(json.dumps({"claude": 9999999999}))
        self.issue.write_text("**Status:** in progress\n")
        (self.project / "code.txt").write_text("unfinished tracked work\n")
        (self.project / "new.txt").write_text("unfinished untracked work\n")
        self.assertEqual(self.run_loop(), 0)
        self.assertEqual([r["provider"] for r in self.records()], ["codex"])

    def test_authentication_failure_hands_work_to_other_provider(self):
        self.assertEqual(self.run_loop(TEST_SCENARIO="auth"), 0)
        records = self.records()
        self.assertEqual([r["outcome"] for r in records], ["authentication", "done"])
        self.assertEqual([r["provider"] for r in records], ["claude", "codex"])
        self.assertFalse(self.cooldowns.exists())

    def test_authentication_stops_when_no_provider_is_signed_in(self):
        self.assertEqual(self.run_loop(TEST_SCENARIO="auth_both"), 1)
        records = self.records()
        self.assertEqual([r["outcome"] for r in records], ["authentication", "authentication"])
        self.assertEqual([r["provider"] for r in records], ["claude", "codex"])

    def test_implementation_failure_retries_with_other_provider_then_stops(self):
        self.assertEqual(self.run_loop(TEST_SCENARIO="failure"), 1)
        records = self.records()
        self.assertEqual([r["outcome"] for r in records], ["failure", "failure"])
        self.assertEqual([r["provider"] for r in records], ["claude", "codex"])
        self.assertFalse(self.cooldowns.exists())

    def test_finished_worker_that_never_exits_is_stopped_and_counted_done(self):
        self.assertEqual(self.run_loop(TEST_SCENARIO="hang", WORK_TIMEOUT="1"), 0)
        record = self.records()[0]
        self.assertEqual((record["outcome"], record["exit_code"]), ("done", TIMED_OUT))
        self.assertIn("Worker timed out after 1s", Path(record["log"]).read_text())

    def test_unfinished_worker_that_times_out_is_a_timeout(self):
        self.issue.write_text("**Status:** in progress\n**Blocked by:** None\n")
        self.assertEqual(self.run_loop(TEST_SCENARIO="hang", WORK_TIMEOUT="1", WORK_PREFERENCE="claude"), 1)
        self.assertEqual([r["outcome"] for r in self.records()], ["timeout", "timeout"])

    def test_interrupt_snapshots_work(self):
        def interrupt(sessions, jobs):
            for _, log in jobs:
                log.write_text("")
            (self.project / "code.txt").write_text("interrupted edit\n")
            raise KeyboardInterrupt
        with patch.object(Sessions, "run", interrupt):
            self.assertEqual(self.run_loop(), 130)
        record = self.records()[0]
        self.assertEqual(record["outcome"], "interrupted")
        self.assertTrue(Path(record["recovery"]).is_dir())
        self.assertEqual((self.project / "code.txt").read_text(), "interrupted edit\n")

    def test_dirty_unclaimed_repo_is_rejected(self):
        (self.project / "code.txt").write_text("user work\n")
        with self.assertRaisesRegex(RunnerError, "uncommitted changes"):
            self.run_loop()
        self.assertFalse((self.root / "calls.jsonl").exists())

    def test_second_runner_is_rejected(self):
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with self.assertRaisesRegex(RunnerError, "already owns"):
            Launch(Settings.load(), self.project).run()

    def test_dashboard_stops_with_the_runner(self):
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            port = free.getsockname()[1]
        pid_file = self.root / "dashboard.pid"
        board = [sys.executable, "-c", f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); "
                                       "time.sleep(60)"]

        def run(_):
            while not pid_file.exists():
                time.sleep(0.05)
            return 0
        with patch.dict(os.environ, {"WORK_DASHBOARD": "1", "WORK_DASHBOARD_PORT": str(port)}), \
                patch.object(loop.Dashboard, "command", lambda _: board), patch.object(Runner, "run", run):
            self.assertEqual(Launch(Settings.load(), self.project).run(), 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)

    def test_both_quotas_wait_only_after_trying_both_providers(self):
        with patch.object(loop.time, "sleep", side_effect=KeyboardInterrupt) as sleep:
            with self.assertRaises(KeyboardInterrupt):
                self.run_loop(TEST_SCENARIO="both_quota")
        self.assertEqual([r["provider"] for r in self.records()], ["claude", "codex"])
        self.assertTrue(all(r["outcome"] == "quota" for r in self.records()))
        self.assertLessEqual(sleep.call_args.args[0], 60)

    def test_a_single_provider_waits_for_its_own_reset(self):
        with patch.object(loop.time, "sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_loop(WORK_PREFERENCE="claude")
        self.assertEqual([r["provider"] for r in self.records()], ["claude"])

    def test_interrupt_stops_real_worker_before_returning(self):
        log = self.directory / "sleeping.log"

        def interrupt_when_started():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if log.exists() and log.read_text().strip():
                    os.kill(os.getpid(), signal.SIGINT)
                    return
                time.sleep(0.01)
        interrupter = threading.Thread(target=interrupt_when_started)
        interrupter.start()
        command = [sys.executable, "-c", "import os,time; print(os.getpid(), flush=True); time.sleep(30)"]
        try:
            with self.assertRaises(KeyboardInterrupt):
                Sessions(self.lock.fileno(), 60, self.root).run([(command, log)])
        finally:
            interrupter.join(timeout=6)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(log.read_text().strip()), 0)

    def test_saved_review_is_not_repeated(self):
        self.issue.write_text("**Status:** in review\n**Blocked by:** None\n")
        (self.cycle / "reviews").mkdir()
        (self.cycle / "reviews/01-standards.md").write_text("## Standards\nsaved\n")
        self.assertEqual(self.run_loop(TEST_SCENARIO="review"), 0)
        self.assertEqual([(r["role"], r["axis"]) for r in self.records()], [("review", "spec"), ("fix", None)])
        self.assertEqual((self.cycle / "reviews/01-standards.md").read_text(), "## Standards\nsaved\n")

    def test_reviewer_out_of_quota_is_replaced_by_the_implementer(self):
        self.assertEqual(self.run_loop(TEST_SCENARIO="review_quota"), 0)
        self.assertEqual([(r["role"], r["provider"], r["outcome"]) for r in self.records()],
                         [("implement", "claude", "in review"), ("review", "codex", "quota"),
                          ("review", "codex", "quota"), ("review", "claude", "reviewed"),
                          ("review", "claude", "reviewed"), ("fix", "claude", "done")])

    def test_empty_cycle_does_not_launch_worker(self):
        self.issue.unlink()
        self.assertEqual(self.run_loop(), 0)
        self.assertFalse((self.root / "calls.jsonl").exists())

    # New scenarios

    def test_every_issue_including_the_build_gets_reviewers_and_a_fixer(self):
        self.add_build_issue()
        self.assertEqual(self.run_loop(TEST_SCENARIO="review", WORK_CODEX__REVIEW__MODEL="codex-review"), 0)
        steps = [(r["issue"][-13:], r["role"], r["axis"], r["provider"], r["outcome"]) for r in self.records()]
        for issue in ("01-feature.md", "/02-build.md"):
            self.assertEqual([step[1:] for step in steps if step[0].endswith(issue)],
                             [("implement", None, "claude", "in review"), ("review", "standards", "codex", "reviewed"),
                              ("review", "spec", "codex", "reviewed"), ("fix", None, "claude", "done")])
        implement = [c for c in self.calls() if "follow it to implement" in c["args"][-1]]
        self.assertTrue(all("Review handoff" in c["args"][-1] for c in implement))
        self.assertFalse(any("subagents" in c["args"][-1] for c in self.calls()))
        reviewer = next(c for c in self.calls() if "axis only" in c["args"][-1])
        self.assertIn("read-only", reviewer["args"])
        self.assertIn("codex-review", reviewer["args"])
        spec = (self.cycle / "reviews/01-spec.md").read_text()
        self.assertIn("No findings by codex", spec)
        self.assertIn("Reviewer: codex (codex-review)", spec)

    def test_one_provider_does_everything(self):
        self.assertEqual(self.run_loop(TEST_SCENARIO="review", WORK_PREFERENCE="claude"), 0)
        self.assertEqual([(r["role"], r["provider"]) for r in self.records()],
                         [("implement", "claude"), ("review", "claude"), ("review", "claude"), ("fix", "claude")])

    def test_after_codex_implemented_claude_reviews(self):
        self.issue.write_text("**Status:** in review\n**Blocked by:** None\n")
        (self.cycle / "work").mkdir()
        (self.cycle / "work/attempts.jsonl").write_text(json.dumps(
            {"issue": str(self.issue.relative_to(self.root)), "role": "implement", "provider": "codex"}) + "\n")
        self.assertEqual(self.run_loop(TEST_SCENARIO="review"), 0)
        self.assertEqual([(r["role"], r["provider"]) for r in self.records()[1:]],
                         [("review", "claude"), ("review", "claude"), ("fix", "claude")])

    def test_claude_cooling_down_makes_codex_implement_and_review(self):
        self.cooldowns.parent.mkdir(parents=True)
        self.cooldowns.write_text(json.dumps({"claude": 9999999999}))
        self.assertEqual(self.run_loop(TEST_SCENARIO="review"), 0)
        self.assertEqual([(r["role"], r["provider"]) for r in self.records()],
                         [("implement", "codex"), ("review", "codex"), ("review", "codex"), ("fix", "codex")])

    def test_the_after_build_command_runs_with_the_project(self):
        self.issue.write_text("**Status:** done\n")
        marker = self.root / "after-build.txt"
        self.assertEqual(self.run_loop(WORK_AFTER_BUILD=f"echo {{project}} > {marker}; exit 3"), 3)
        self.assertEqual(marker.read_text().strip(), str(self.project))

    def test_an_empty_after_build_command_does_nothing(self):
        self.issue.write_text("**Status:** done\n")
        self.assertEqual(self.run_loop(WORK_AFTER_BUILD=""), 0)

    def test_the_after_build_command_waits_for_the_build(self):
        self.add_build_issue()
        self.issue.write_text("**Status:** done\n")
        (self.cycle / "issues/02-build.md").write_text("**Status:** blocked\n")
        marker = self.root / "after-build.txt"
        self.assertEqual(self.run_loop(WORK_AFTER_BUILD=f"touch {marker}"), 0)
        self.assertFalse(marker.exists())


class RepoTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        self.repo = Repo(self.project)
        self.ran = self.project.parent / f"{self.project.name}-ran"
        self.addCleanup(lambda: self.ran.unlink(missing_ok=True))

    def test_a_clean_repo_runs_git(self):
        self.assertEqual(self.repo.git("status", "--porcelain"), b"")

    def test_a_planted_fsmonitor_is_refused_without_running_it(self):
        subprocess.run(["git", "-C", str(self.project), "config", "core.fsmonitor", f"touch {self.ran}"], check=True)
        with self.assertRaises(UnsafeRepoError):
            self.repo.git("status", "--porcelain")
        self.assertFalse(self.ran.exists())

    def test_an_installed_hook_is_refused(self):
        hook = self.project / ".git/hooks/post-checkout"
        hook.write_text(f"#!/bin/sh\ntouch {self.ran}\n")
        hook.chmod(0o755)
        with self.assertRaisesRegex(UnsafeRepoError, "hook post-checkout"):
            self.repo.git("status", "--porcelain")

    def test_diff_skips_external_diff_drivers(self):
        (self.project / "a.txt").write_text("one\n")
        subprocess.run(["git", "-C", str(self.project), "add", "a.txt"], check=True)
        with patch.dict(os.environ, {"GIT_EXTERNAL_DIFF": f"touch {self.ran}"}):
            self.repo.git("diff", "--binary", "--cached")
        self.assertFalse(self.ran.exists())


if __name__ == "__main__":
    unittest.main()
