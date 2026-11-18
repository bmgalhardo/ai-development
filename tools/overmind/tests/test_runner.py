"""The worker loop end to end, with real temporary git repos and fake provider CLIs on PATH."""

from contextlib import ExitStack
import fcntl
from http.server import BaseHTTPRequestHandler, HTTPServer
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

from overmind.runner import loop
from overmind.runner.loop import Launch, Runner, RunnerError
from overmind.runner.repo import Repo, UnsafeRepoError
from overmind.runner.sessions import TIMED_OUT, Session, Sessions
from overmind.core.settings import Settings

FAKE_WORKER = Path(__file__).with_name("fake_worker.py")
FAKE_DOCKER = Path(__file__).with_name("fake_docker.py")


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
        clean = {key: value for key, value in os.environ.items() if not key.upper().startswith("OVERMIND_")}
        self.stack.enter_context(patch.dict(os.environ, clean | {
            "PATH": f"{binaries}:{os.environ['PATH']}", "OVERMIND_ROOT": str(self.root),
            "OVERMIND_PREFERENCE": "claude,codex", "OVERMIND_CLAUDE__IMPLEMENT__MODEL": "test-claude",
            "OVERMIND_WAIT": "60", "OVERMIND_DASHBOARD": "0", "OVERMIND_CONTAINER": "0"}, clear=True))
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
        self.assertEqual(self.run_loop(TEST_SCENARIO="hang", OVERMIND_TIMEOUT="1"), 0)
        record = self.records()[0]
        self.assertEqual((record["outcome"], record["exit_code"]), ("done", TIMED_OUT))
        self.assertIn("Worker timed out after 1s", Path(record["log"]).read_text())

    def test_unfinished_worker_that_times_out_is_a_timeout(self):
        self.issue.write_text("**Status:** in progress\n**Blocked by:** None\n")
        self.assertEqual(self.run_loop(TEST_SCENARIO="hang", OVERMIND_TIMEOUT="1", OVERMIND_PREFERENCE="claude"), 1)
        self.assertEqual([r["outcome"] for r in self.records()], ["timeout", "timeout"])

    def test_interrupt_snapshots_work(self):
        def interrupt(sessions, jobs):
            for session in jobs:
                session.log.write_text("")
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
        with patch.dict(os.environ, {"OVERMIND_DASHBOARD": "1", "OVERMIND_DASHBOARD_PORT": str(port)}), \
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
                self.run_loop(OVERMIND_PREFERENCE="claude")
        self.assertEqual([r["provider"] for r in self.records()], ["claude"])

    def test_only_a_stopped_session_is_cleaned_up_right_after_it_stops(self):
        stopped = []
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
        start = time.monotonic()
        codes = Sessions(self.lock.fileno(), 1, self.root).run([
            Session(command=sleeper, log=self.directory / "one.log",
                    stopped=lambda: stopped.append(time.monotonic() - start)),
            Session(command=["true"], log=self.directory / "two.log", stopped=lambda: stopped.append("sibling"))])
        self.assertEqual(codes, [TIMED_OUT, 0])
        self.assertEqual(len(stopped), 1)
        self.assertLess(stopped[0], 5)

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
                Sessions(self.lock.fileno(), 60, self.root).run([Session(command=command, log=log)])
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
        self.assertEqual(self.run_loop(TEST_SCENARIO="review", OVERMIND_CODEX__REVIEW__MODEL="codex-review"), 0)
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
        self.assertEqual(self.run_loop(TEST_SCENARIO="review", OVERMIND_PREFERENCE="claude"), 0)
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
        self.assertEqual(self.run_loop(OVERMIND_AFTER_BUILD=f"echo {{project}} > {marker}; exit 3"), 3)
        self.assertEqual(marker.read_text().strip(), str(self.project))

    def test_an_empty_after_build_command_does_nothing(self):
        self.issue.write_text("**Status:** done\n")
        self.assertEqual(self.run_loop(OVERMIND_AFTER_BUILD=""), 0)

    def test_the_after_build_command_waits_for_the_build(self):
        self.add_build_issue()
        self.issue.write_text("**Status:** done\n")
        (self.cycle / "issues/02-build.md").write_text("**Status:** blocked\n")
        marker = self.root / "after-build.txt"
        self.assertEqual(self.run_loop(OVERMIND_AFTER_BUILD=f"touch {marker}"), 0)
        self.assertFalse(marker.exists())

    def test_a_stuck_cycle_stops_with_an_error(self):
        self.add_build_issue()
        self.issue.write_text("**Status:** open\n**Blocked by:** 02\n")
        self.assertEqual(self.run_loop(), 1)

    # Notifications

    def telegram(self):
        """A local stand-in for Telegram's Bot API; the messages it receives."""
        messages = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                messages.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        environment = {"OVERMIND_TELEGRAM_TOKEN": "secret", "OVERMIND_TELEGRAM_CHAT_ID": "42",
                       "OVERMIND_TELEGRAM_API": f"http://127.0.0.1:{server.server_port}"}
        return messages, environment

    def test_a_blocked_issue_and_the_runs_end_are_notified(self):
        messages, environment = self.telegram()
        self.assertEqual(self.run_loop(TEST_SCENARIO="blocked", **environment), 0)
        self.assertEqual([path for path, _ in messages], ["/botsecret/sendMessage"] * 2)
        self.assertEqual({body["chat_id"] for _, body in messages}, {"42"})
        blocked, end = (body["text"] for _, body in messages)
        self.assertIn("01-feature.md is blocked", blocked)
        self.assertIn("pick the boss's enrage time", blocked)
        self.assertIn("the run ended (exit 0)", end)
        self.assertIn("• 01-feature.md: pick the boss's enrage time", end)
        self.assertIn("1 blocked", end)

    def test_the_failure_limit_is_notified_with_its_reason(self):
        messages, environment = self.telegram()
        self.assertEqual(self.run_loop(TEST_SCENARIO="failure", **environment), 1)
        self.assertEqual(len(messages), 1)
        self.assertIn("01-feature.md failed twice (claude, codex)", messages[0][1]["text"])

    def test_an_unreachable_telegram_does_not_stop_the_run(self):
        self.issue.write_text("**Status:** done\n")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.assertEqual(self.run_loop(OVERMIND_TELEGRAM_TOKEN="secret", OVERMIND_TELEGRAM_CHAT_ID="42",
                                       OVERMIND_TELEGRAM_API=f"http://127.0.0.1:{port}"), 0)

    def test_without_telegram_settings_nothing_is_sent(self):
        messages, environment = self.telegram()
        environment.pop("OVERMIND_TELEGRAM_TOKEN")
        environment.pop("OVERMIND_TELEGRAM_CHAT_ID")
        self.assertEqual(self.run_loop(TEST_SCENARIO="blocked", **environment), 0)
        self.assertEqual(messages, [])

    # Containers

    def use_containers(self):
        """A fake docker on PATH that runs the session on the host, and the workers' logins."""
        docker = self.root / "bin/docker"
        docker.write_text(f"#!{sys.executable}\n" + FAKE_DOCKER.read_text())
        docker.chmod(0o755)
        logins = self.root / ".logins"
        logins.mkdir()
        (logins / ".claude.login").write_text("setup-token\n")
        (logins / ".codex.login").write_text("{}\n")
        return {"OVERMIND_CONTAINER": "1", "FAKE_DOCKER_LOG": str(self.root / "docker.jsonl")}

    def docker_calls(self):
        return [json.loads(line) for line in (self.root / "docker.jsonl").read_text().splitlines()]

    def test_containers_run_each_session_with_its_provider_login_and_role(self):
        self.assertEqual(self.run_loop(TEST_SCENARIO="review", **self.use_containers()), 0)
        self.assertEqual([(r["role"], r["provider"], r["outcome"]) for r in self.records()],
                         [("implement", "claude", "in review"), ("review", "codex", "reviewed"),
                          ("review", "codex", "reviewed"), ("fix", "claude", "done")])
        runs = [call for call in self.docker_calls() if call["args"][0] == "run"]
        roles = [(labels["overmind.provider"], labels["overmind.role"]) for labels in
                 [dict(call["args"][i + 1].split("=", 1) for i, part in enumerate(call["args"]) if part == "--label")
                  for call in runs]]
        self.assertEqual(roles, [("claude", "implement"), ("codex", "review"), ("codex", "review"), ("claude", "fix")])
        self.assertEqual(runs[0]["environment"]["CLAUDE_CODE_OAUTH_TOKEN"], "setup-token")
        self.assertIn(f"{self.project}:{self.project}:ro", runs[1]["args"])
        self.assertIn(f"{self.project}:{self.project}:rw", runs[3]["args"])
        self.assertIn("--skip-git-repo-check", runs[1]["args"])
        self.assertIn("danger-full-access", runs[1]["args"])
        self.assertNotIn("read-only", runs[1]["args"])
        for provider in ("claude", "codex"):
            self.assertTrue((self.root / f".scratch/project/sessions/{provider}").is_dir())

    def test_stopping_a_container_session_removes_its_container(self):
        self.assertEqual(self.run_loop(TEST_SCENARIO="hang", OVERMIND_TIMEOUT="1", **self.use_containers()), 0)
        self.assertEqual(self.records()[0]["exit_code"], TIMED_OUT)
        calls = [call["args"] for call in self.docker_calls()]
        name = next(args[args.index("--name") + 1] for args in calls if args[0] == "run")
        self.assertIn(["rm", "-f", name], calls)

    def test_a_new_runner_removes_the_projects_leftover_containers(self):
        self.issue.unlink()
        with patch.dict(os.environ, self.use_containers()):
            self.assertEqual(Launch(Settings.load(), self.project).run(), 0)
        self.assertEqual([call["args"] for call in self.docker_calls()],
                         [["ps", "-aq", "--filter", "label=overmind.project=project"], ["rm", "-f", "leftover"]])


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
