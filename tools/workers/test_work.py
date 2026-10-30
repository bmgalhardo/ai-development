"""Exercise worker handoffs with real temporary Git repos and fake provider CLIs."""

from contextlib import ExitStack
from datetime import datetime, timezone
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

from tools.workers import next_issue, work, work_attempt
from tools.workers.work_attempt import failure_kind, git, read_result, retry_at


FAKE_WORKER = '''#!/usr/bin/env python3
import json, os, pathlib, re, sys
provider = pathlib.Path(sys.argv[0]).name
root = pathlib.Path.cwd()
with (root / 'calls.jsonl').open('a') as out:
    out.write(json.dumps({'provider': provider, 'args': sys.argv[1:]}) + '\\n')
issue = root / re.search(r'(\\S+/issues/\\S+?\\.md)', sys.argv[-1])[1]
scenario = os.environ.get('TEST_SCENARIO', 'quota')
if scenario in ('review', 'review_quota'):
    prompt = sys.argv[-1]
    if 'axis only' in prompt:
        if scenario == 'review_quota' and provider == 'codex':
            print(json.dumps({'type': 'error', 'message': 'usage_limit_reached'}))
            sys.exit(1)
        report = f"## {re.search(r'the (\\w+) axis', prompt)[1]}\\nNo findings by {provider}."
        if provider == 'codex':
            print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': report}}))
        else:
            print(json.dumps({'type': 'result', 'result': report}))
    elif 'Fix session' in prompt:
        assert all((root / r).exists() for r in re.findall(r'(\\S+/reviews/\\S+?\\.md)', prompt))
        issue.write_text(issue.read_text().replace('Status:** in review', 'Status:** done'))
    else:
        issue.write_text(issue.read_text().replace('Status:** open', 'Status:** in review'))
    sys.exit(0)
project = root / 'project'
if scenario == 'hang':
    if provider == 'claude':
        issue.write_text(issue.read_text().replace('Status:** open', 'Status:** done'))
    import time; time.sleep(30)
if scenario == 'auth_both' or (scenario == 'auth' and provider == 'claude'):
    issue.write_text(issue.read_text().replace('Status:** open', 'Status:** in progress'))
    (project / 'code.txt').write_text('unfinished tracked work\\n')
    (project / 'new.txt').write_text('unfinished untracked work\\n')
    print(json.dumps({'type': 'result', 'is_error': True,
        'result': 'Failed to authenticate: OAuth session expired and could not be refreshed'}))
    sys.exit(1)
if scenario == 'failure':
    print('Implementation check failed')
    sys.exit(1)
if provider == 'claude' or scenario == 'both_quota':
    issue.write_text(issue.read_text().replace('Status:** open', 'Status:** in progress'))
    (project / 'code.txt').write_text('unfinished tracked work\\n')
    (project / 'new.txt').write_text('unfinished untracked work\\n')
    print(json.dumps({'type': 'result', 'is_error': True,
        'api_error': 'usage_limit_reached', 'api_error_status': 429,
        'result': "You've hit your session limit · resets 11pm (UTC)",
        'usage': {'input_tokens': 100, 'cache_read_input_tokens': 500}}))
    sys.exit(1)
assert (project / 'new.txt').read_text() == 'unfinished untracked work\\n'
assert (project / 'code.txt').read_text() == 'unfinished tracked work\\n'
issue.write_text(issue.read_text().replace('Status:** in progress', 'Status:** done'))
print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 25, 'output_tokens': 5}}))
'''


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.project = self.root / 'project'
        self.project.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        (self.project / 'code.txt').write_text('original\n')
        git(self.project, 'add', 'code.txt')
        git(self.project, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
            'commit', '-qm', 'base')
        self.cycle = self.root / '.scratch/project/2026-10-22-test'
        (self.cycle / 'issues').mkdir(parents=True)
        self.issue = self.cycle / 'issues/01-feature.md'
        self.issue.write_text('**Status:** open\n**Blocked by:** None\n')
        self.directory = self.root / '.scratch/project/runner'
        self.directory.mkdir(parents=True)
        self.cooldowns = self.root / '.scratch/runner/cooldowns.json'
        self.cooldowns.parent.mkdir()
        binaries = self.root / 'bin'
        binaries.mkdir()
        for provider in ('claude', 'codex'):
            executable = binaries / provider
            executable.write_text(FAKE_WORKER.replace('#!/usr/bin/env python3', f'#!{sys.executable}'))
            executable.chmod(0o755)
        self.stack.enter_context(patch.dict(os.environ, {
            'PATH': f"{binaries}:{os.environ['PATH']}", 'WORK_AGENT': 'claude',
            'WORK_FALLBACK_AGENT': 'codex', 'WORK_REVIEW_AGENT': 'none', 'WORK_MODEL': 'test-claude',
            'WORK_REVIEW_MODEL': 'test-review', 'WORK_WAIT': '60', 'WORK_DASHBOARD': '0',
            'PUBLISH_URL': 'https://publish.test',
        }))
        self.stack.enter_context(patch.object(next_issue, 'WORKFLOW', self.root))
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.lock = self.stack.enter_context((self.directory / 'runner.lock').open('a'))

    def run_loop(self):
        return work.run(self.project, self.directory, self.lock.fileno())

    def records(self):
        return [json.loads(line) for line in (self.cycle / 'work/attempts.jsonl').read_text().splitlines()]

    def test_quota_handoff_preserves_work_and_does_not_leak_model(self):
        self.assertEqual(self.run_loop(), 0)
        records = self.records()
        self.assertEqual([r['outcome'] for r in records], ['quota', 'done'])
        self.assertEqual([r['provider'] for r in records], ['claude', 'codex'])
        self.assertEqual(records[0]['usage'][0]['usage']['input_tokens'], 100)
        self.assertEqual(records[1]['usage'][0]['input_tokens'], 25)
        calls = [json.loads(line) for line in (self.root / 'calls.jsonl').read_text().splitlines()]
        self.assertIn('test-claude', calls[0]['args'])
        self.assertIn('test-review', calls[0]['args'][-1])
        self.assertNotIn('--model', calls[1]['args'])
        self.assertNotIn('test-review', calls[1]['args'][-1])
        recovery = Path(records[0]['recovery'])
        self.assertIn('unfinished tracked work', (recovery / 'changes.patch').read_text())
        with tarfile.open(recovery / 'untracked.tar') as archive:
            self.assertEqual(archive.extractfile('new.txt').read(), b'unfinished untracked work\n')
        self.assertGreater(json.loads(self.cooldowns.read_text())['claude'], 0)

    def test_a_done_build_is_published(self):
        with patch.object(work, 'publish_build', return_value=0) as published:
            self.assertEqual(self.run_loop(), 0)
        self.assertEqual(self.records()[-1]['outcome'], 'done')
        published.assert_called_once_with(self.project)

    def test_publishing_needs_a_publishing_doc_and_can_be_turned_off(self):
        with patch.object(work.subprocess, 'run') as ran:
            self.assertEqual(work.publish_build(self.project), 0)
            (self.project / '.agents/context').mkdir(parents=True)
            (self.project / '.agents/context/publishing.md').write_text('| docs | `site/` |\n')
            with patch.dict(os.environ, {'WORK_PUBLISH': '0'}):
                self.assertEqual(work.publish_build(self.project), 0)
            ran.assert_not_called()
            ran.return_value.returncode = 1
            self.assertEqual(work.publish_build(self.project), 1)
        self.assertEqual(ran.call_args.args[0][-2:], ['tools.publish.publish', str(self.project)])

    def test_persisted_cooldown_skips_provider_on_restart(self):
        self.cooldowns.write_text(json.dumps({'claude': 9999999999}))
        self.issue.write_text('**Status:** in progress\n')
        (self.project / 'code.txt').write_text('unfinished tracked work\n')
        (self.project / 'new.txt').write_text('unfinished untracked work\n')
        self.assertEqual(self.run_loop(), 0)
        self.assertEqual([r['provider'] for r in self.records()], ['codex'])

    def test_authentication_failure_hands_work_to_other_provider(self):
        with patch.dict(os.environ, {'TEST_SCENARIO': 'auth'}):
            self.assertEqual(self.run_loop(), 0)
        records = self.records()
        self.assertEqual([r['outcome'] for r in records], ['authentication', 'done'])
        self.assertEqual([r['provider'] for r in records], ['claude', 'codex'])
        self.assertFalse(self.cooldowns.exists())

    def test_authentication_stops_when_no_provider_is_signed_in(self):
        with patch.dict(os.environ, {'TEST_SCENARIO': 'auth_both'}):
            self.assertEqual(self.run_loop(), 1)
        records = self.records()
        self.assertEqual([r['outcome'] for r in records], ['authentication', 'authentication'])
        self.assertEqual([r['provider'] for r in records], ['claude', 'codex'])

    def test_implementation_failure_retries_with_other_provider_then_stops(self):
        with patch.dict(os.environ, {'TEST_SCENARIO': 'failure'}):
            self.assertEqual(self.run_loop(), 1)
        records = self.records()
        self.assertEqual([r['outcome'] for r in records], ['failure', 'failure'])
        self.assertEqual([r['provider'] for r in records], ['claude', 'codex'])
        self.assertFalse(self.cooldowns.exists())

    def test_finished_worker_that_never_exits_is_stopped_and_counted_done(self):
        with patch.dict(os.environ, {'TEST_SCENARIO': 'hang', 'WORK_TIMEOUT': '1'}):
            self.assertEqual(self.run_loop(), 0)
        record = self.records()[0]
        self.assertEqual((record['outcome'], record['exit_code']), ('done', work.TIMED_OUT))
        self.assertIn('Worker timed out after 1s', Path(record['log']).read_text())

    def test_unfinished_worker_that_times_out_is_a_timeout(self):
        self.issue.write_text('**Status:** in progress\n**Blocked by:** None\n')
        with patch.dict(os.environ, {'TEST_SCENARIO': 'hang', 'WORK_TIMEOUT': '1', 'WORK_FALLBACK_AGENT': 'none'}):
            self.assertEqual(self.run_loop(), 1)
        self.assertEqual([r['outcome'] for r in self.records()], ['timeout', 'timeout'])

    def test_interrupt_snapshots_work(self):
        def interrupt(command, log, lock_fd):
            log.write_text('')
            (self.project / 'code.txt').write_text('interrupted edit\n')
            raise KeyboardInterrupt
        with patch.object(work, 'run_worker', interrupt):
            self.assertEqual(self.run_loop(), 130)
        self.assertEqual(self.records()[0]['outcome'], 'interrupted')
        self.assertEqual((self.project / 'code.txt').read_text(), 'interrupted edit\n')

    def test_dirty_unclaimed_repo_is_rejected(self):
        (self.project / 'code.txt').write_text('user work\n')
        with self.assertRaisesRegex(ValueError, 'uncommitted changes'):
            self.run_loop()
        self.assertFalse((self.root / 'calls.jsonl').exists())

    def test_second_runner_is_rejected(self):
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with patch.object(sys, 'argv', ['work.py', str(self.project)]):
            with self.assertRaisesRegex(SystemExit, 'already owns'):
                work.main()

    def test_dashboard_stops_with_the_runner(self):
        uv = self.root / 'bin/uv'
        uv.write_text(f"#!{sys.executable}\nimport os, time\nopen('dashboard.pid', 'w').write(str(os.getpid()))\n"
                      "time.sleep(60)\n")
        uv.chmod(0o755)
        with socket.socket() as free:
            free.bind(('127.0.0.1', 0))
            port = free.getsockname()[1]

        def run(*_):
            while not (self.root / 'dashboard.pid').exists():
                time.sleep(0.05)
            return 0
        with patch.dict(os.environ, {'WORK_DASHBOARD': '1', 'WORK_DASHBOARD_PORT': str(port)}):
            with patch.object(sys, 'argv', ['work.py', str(self.project)]), patch.object(work, 'run', run):
                self.assertEqual(work.main(), 0)
        pid = int((self.root / 'dashboard.pid').read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_both_quotas_wait_only_after_trying_both_providers(self):
        with patch.dict(os.environ, {'TEST_SCENARIO': 'both_quota'}):
            with patch.object(work.time, 'sleep', side_effect=KeyboardInterrupt) as sleep:
                with self.assertRaises(KeyboardInterrupt):
                    self.run_loop()
        self.assertEqual([r['provider'] for r in self.records()], ['claude', 'codex'])
        self.assertTrue(all(r['outcome'] == 'quota' for r in self.records()))
        self.assertLessEqual(sleep.call_args.args[0], 60)

    def test_fallback_can_be_disabled(self):
        with patch.dict(os.environ, {'WORK_FALLBACK_AGENT': 'none'}):
            with patch.object(work.time, 'sleep', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    self.run_loop()
        self.assertEqual([r['provider'] for r in self.records()], ['claude'])

    def test_provider_specific_models_override_generic_settings(self):
        with patch.dict(os.environ, {'WORK_CODEX_MODEL': 'test-codex',
                                     'WORK_CLAUDE_MODEL': 'override-claude',
                                     'WORK_CODEX_REVIEW_MODEL': 'codex-review'}):
            codex = work.worker_command('codex', self.project, 'issue.md')
            claude = work.worker_command('claude', self.project, 'issue.md')
            review = work.worker_command('codex', self.project, 'issue.md', 'review', axis='spec')
        self.assertIn('test-codex', codex)
        self.assertIn('codex-review', codex[-1])
        self.assertIn('codex-review', review)
        self.assertIn('override-claude', claude)

    def test_container_runs_each_session_with_its_provider_and_mounts(self):
        with patch.dict(os.environ, {'WORK_CONTAINER': '1'}):
            implement = work.worker_command('claude', self.project, 'issue.md')
            fix = work.worker_command('codex', self.project, 'issue.md', 'fix', reviews=('r.md',))
            review = work.worker_command('codex', self.project, 'issue.md', 'review', axis='spec')
        run = str(work.next_issue.WORKFLOW / 'tools/container/run.sh')
        self.assertEqual(implement[:5], [run, 'claude', 'implement', str(self.project), 'claude'])
        self.assertEqual(fix[:5], [run, 'codex', 'implement', str(self.project), 'codex'])
        self.assertEqual(review[:4], [run, 'codex', 'review', str(self.project)])
        self.assertIn('danger-full-access', review)
        self.assertNotIn('read-only', review)
        self.assertIn('--skip-git-repo-check', fix)

    def test_without_container_codex_reviews_in_its_read_only_sandbox(self):
        review = work.worker_command('codex', self.project, 'issue.md', 'review', axis='spec')
        self.assertEqual(review[0], 'codex')
        self.assertIn('read-only', review)

    def test_stopping_a_container_session_removes_its_container(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        with patch.dict(os.environ, {'WORK_CONTAINER': '1'}), \
                patch.object(work, 'remove_containers') as remove:
            work.stop(child)
        remove.assert_called_once_with(f'work.pid={child.pid}')

    def test_interrupt_stops_real_worker_before_returning(self):
        log = self.directory / 'sleeping.log'
        def interrupt_when_started():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if log.exists() and log.read_text().strip():
                    os.kill(os.getpid(), signal.SIGINT)
                    return
                time.sleep(0.01)
        interrupter = threading.Thread(target=interrupt_when_started)
        interrupter.start()
        command = [sys.executable, '-c',
                   'import os,time; print(os.getpid(), flush=True); time.sleep(30)']
        try:
            with self.assertRaises(KeyboardInterrupt):
                work.run_worker(command, log, self.lock.fileno())
        finally:
            interrupter.join(timeout=6)
        worker_pid = int(log.read_text().strip())
        with self.assertRaises(ProcessLookupError):
            os.kill(worker_pid, 0)

    def calls(self):
        return [json.loads(line) for line in (self.root / 'calls.jsonl').read_text().splitlines()]

    def add_build_issue(self):
        build = self.cycle / 'issues/02-build.md'
        build.write_text('**Status:** open\n**Blocked by:** 01\n')
        return build

    def test_reviewers_then_fixer_each_in_their_own_session(self):
        self.add_build_issue()
        with patch.dict(os.environ, {'TEST_SCENARIO': 'review', 'WORK_REVIEW_AGENT': 'codex',
                                     'WORK_CODEX_REVIEW_MODEL': 'codex-review'}):
            self.assertEqual(self.run_loop(), 0)
        records = self.records()
        self.assertEqual([(r['role'], r['axis'], r['provider'], r['outcome']) for r in records[:4]],
                         [('implement', None, 'claude', 'in review'),
                          ('review', 'standards', 'codex', 'reviewed'),
                          ('review', 'spec', 'codex', 'reviewed'),
                          ('fix', None, 'claude', 'done')])
        calls = self.calls()
        self.assertIn('Review handoff', calls[0]['args'][-1])
        reviewer = next(c for c in calls if 'axis only' in c['args'][-1])
        self.assertIn('read-only', reviewer['args'])
        self.assertIn('codex-review', reviewer['args'])
        spec = (self.cycle / 'reviews/01-spec.md').read_text()
        self.assertIn('No findings by codex', spec)
        self.assertIn('Reviewer: codex (codex-review)', spec)
        # The build issue is never handed off: its implementer reviews it.
        self.assertEqual(records[4]['role'], 'implement')
        self.assertNotIn('Review handoff', calls[4]['args'][-1])

    def test_saved_review_is_not_repeated(self):
        self.issue.write_text('**Status:** in review\n**Blocked by:** None\n')
        (self.cycle / 'reviews').mkdir()
        (self.cycle / 'reviews/01-standards.md').write_text('## Standards\nsaved\n')
        with patch.dict(os.environ, {'TEST_SCENARIO': 'review', 'WORK_REVIEW_AGENT': 'codex'}):
            self.assertEqual(self.run_loop(), 0)
        self.assertEqual([(r['role'], r['axis']) for r in self.records()],
                         [('review', 'spec'), ('fix', None)])
        self.assertEqual((self.cycle / 'reviews/01-standards.md').read_text(), '## Standards\nsaved\n')

    def test_reviewer_out_of_quota_is_replaced_by_implementer(self):
        with patch.dict(os.environ, {'TEST_SCENARIO': 'review_quota', 'WORK_REVIEW_AGENT': 'codex'}):
            self.assertEqual(self.run_loop(), 0)
        self.assertEqual([(r['role'], r['provider'], r['outcome']) for r in self.records()],
                         [('implement', 'claude', 'in review'), ('review', 'codex', 'quota'),
                          ('review', 'codex', 'quota'), ('review', 'claude', 'reviewed'),
                          ('review', 'claude', 'reviewed'), ('fix', 'claude', 'done')])

    def test_no_reviewer_keeps_review_in_implementer_session(self):
        self.assertEqual(self.run_loop(), 0)
        self.assertEqual([r['role'] for r in self.records()], ['implement', 'implement'])
        self.assertFalse(any('Review handoff' in c['args'][-1] for c in self.calls()))

    def test_defaults_implement_with_claude_and_review_with_codex(self):
        with patch.dict(os.environ):
            for name in ('WORK_AGENT', 'WORK_FALLBACK_AGENT', 'WORK_REVIEW_AGENT'):
                del os.environ[name]
            self.assertEqual(work.providers(), (['claude', 'codex'], ['codex', 'claude']))

    def test_empty_cycle_does_not_launch_worker(self):
        self.issue.unlink()
        self.assertEqual(self.run_loop(), 0)
        self.assertFalse((self.root / 'calls.jsonl').exists())


class HostGitTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        self.ran = self.project.parent / f'{self.project.name}-ran'
        self.addCleanup(lambda: self.ran.unlink(missing_ok=True))

    def test_a_clean_repo_runs_git(self):
        self.assertEqual(work_attempt.git(self.project, 'status', '--porcelain'), b'')

    def test_a_planted_fsmonitor_is_refused_without_running_it(self):
        subprocess.run(['git', '-C', str(self.project), 'config', 'core.fsmonitor', f'touch {self.ran}'], check=True)
        with self.assertRaises(SystemExit):
            work_attempt.git(self.project, 'status', '--porcelain')
        self.assertFalse(self.ran.exists())

    def test_an_installed_hook_is_refused(self):
        hook = self.project / '.git/hooks/post-checkout'
        hook.write_text(f'#!/bin/sh\ntouch {self.ran}\n')
        hook.chmod(0o755)
        with self.assertRaises(SystemExit) as stopped:
            work_attempt.git(self.project, 'status', '--porcelain')
        self.assertIn('hook post-checkout', str(stopped.exception))

    def test_diff_skips_external_diff_drivers(self):
        (self.project / 'a.txt').write_text('one\n')
        subprocess.run(['git', '-C', str(self.project), 'add', 'a.txt'], check=True)
        with patch.dict(os.environ, {'GIT_EXTERNAL_DIFF': f'touch {self.ran}'}):
            work_attempt.git(self.project, 'diff', '--binary', '--cached')
        self.assertFalse(self.ran.exists())


class ResultTests(unittest.TestCase):
    def test_claude_limit_messages_trigger_quota(self):
        for message in ("You've hit your limit", "You've hit your usage limit",
                        "You've hit your session limit · resets 4am (Europe/Lisbon)",
                        "You have reached your weekly limit",
                        "You’ve hit your usage limit. Upgrade to Pro or try again at 4:52 AM."):
            with self.subTest(message=message):
                self.assertEqual(failure_kind(message), 'quota')

    def test_claude_expired_login_triggers_authentication(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'output.log'
            log.write_text(json.dumps({'type': 'result', 'is_error': True, 'terminal_reason': 'api_error',
                                       'result': 'Failed to authenticate: OAuth session expired '
                                                 'and could not be refreshed'}))
            message, _ = read_result(log)
            self.assertEqual(failure_kind(message), 'authentication')

    def test_claude_structured_api_error_triggers_quota_without_limit_text(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'output.log'
            log.write_text(json.dumps({'type': 'result', 'is_error': True,
                                       'api_error': 'usage_limit_reached',
                                       'result': 'Request could not complete'}))
            message, _ = read_result(log)
            self.assertEqual(failure_kind(message), 'quota')

    def test_codex_limit_event_triggers_quota(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'output.log'
            text = 'You’ve hit your usage limit. Try again at 1:53 PM.'
            log.write_text('Reading additional input from stdin...\n'
                           + json.dumps({'type': 'error', 'message': text}) + '\n'
                           + json.dumps({'type': 'turn.failed', 'error': {'message': text}}) + '\n')
            message, _ = read_result(log)
            self.assertEqual(failure_kind(message), 'quota')
            self.assertGreater(retry_at(message, 60), time.time())

    def test_tool_output_does_not_trigger_quota_wait(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'output.log'
            log.write_text(json.dumps({'type': 'item.completed', 'item': {
                'type': 'command_execution', 'aggregated_output': 'usage limit reached 429'}}))
            message, _ = read_result(log)
            self.assertEqual(failure_kind(message), 'failure')

    def test_timezone_and_next_day_reset(self):
        now = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)
        reset = retry_at('resets 4pm (America/Los_Angeles)', 60, now)
        self.assertEqual(datetime.fromtimestamp(reset, timezone.utc),
                         datetime(2026, 10, 22, 23, 0, 30, tzinfo=timezone.utc))
        reset = retry_at('resets 9pm (UTC)', 60, now)
        self.assertEqual(datetime.fromtimestamp(reset, timezone.utc),
                         datetime(2026, 10, 23, 21, 0, 30, tzinfo=timezone.utc))

    def test_codex_time_only_reset_uses_local_time(self):
        now = datetime(2026, 10, 25, 3, 6, tzinfo=timezone.utc)
        reset = retry_at('try again at 4:52 AM.', 60, now)
        self.assertEqual(datetime.fromtimestamp(reset, timezone.utc),
                         datetime(2026, 10, 25, 4, 52, 30, tzinfo=timezone.utc))
        reset = retry_at('try again at 2:00 AM.', 60, now)
        self.assertEqual(datetime.fromtimestamp(reset, timezone.utc),
                         datetime(2026, 10, 26, 2, 0, 30, tzinfo=timezone.utc))

    def test_unknown_reset_and_malformed_time_use_fallback(self):
        now = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)
        for message in ('resets tomorrow', 'resets 99pm (UTC)', 'resets 9pm (Unknown/Zone)'):
            self.assertEqual(retry_at(message, 60, now), now.timestamp() + 60)


if __name__ == '__main__':
    unittest.main()
