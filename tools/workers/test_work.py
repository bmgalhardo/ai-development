"""Exercise worker handoffs with real temporary Git repos and fake provider CLIs."""

from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tools.workers import next_issue, work
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
if scenario == 'auth':
    print(json.dumps({'type': 'error', 'message': 'authentication failed: not logged in'}))
    sys.exit(1)
if scenario == 'failure':
    print('Implementation check failed')
    sys.exit(1)
game = root / 'game'
if provider == 'claude' or scenario == 'both_quota':
    issue.write_text(issue.read_text().replace('Status:** open', 'Status:** in progress'))
    (game / 'code.txt').write_text('unfinished tracked work\\n')
    (game / 'new.txt').write_text('unfinished untracked work\\n')
    print(json.dumps({'type': 'result', 'is_error': True,
        'result': "You've hit your limit · resets 11pm (UTC)",
        'usage': {'input_tokens': 100, 'cache_read_input_tokens': 500}}))
    sys.exit(1)
assert (game / 'new.txt').read_text() == 'unfinished untracked work\\n'
assert (game / 'code.txt').read_text() == 'unfinished tracked work\\n'
issue.write_text(issue.read_text().replace('Status:** in progress', 'Status:** done'))
print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 25, 'output_tokens': 5}}))
'''


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.game = self.root / 'game'
        self.game.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.game)], check=True)
        (self.game / 'code.txt').write_text('original\n')
        git(self.game, 'add', 'code.txt')
        git(self.game, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
            'commit', '-qm', 'base')
        self.cycle = self.root / '.scratch/game/2026-10-22-test'
        (self.cycle / 'issues').mkdir(parents=True)
        self.issue = self.cycle / 'issues/01-feature.md'
        self.issue.write_text('**Status:** open\n**Blocked by:** None\n')
        self.directory = self.root / 'artifacts/work/game'
        self.directory.mkdir(parents=True)
        binaries = self.root / 'bin'
        binaries.mkdir()
        for provider in ('claude', 'codex'):
            executable = binaries / provider
            executable.write_text(FAKE_WORKER.replace('#!/usr/bin/env python3', f'#!{sys.executable}'))
            executable.chmod(0o755)
        self.stack.enter_context(patch.dict(os.environ, {
            'PATH': f"{binaries}:{os.environ['PATH']}", 'WORK_AGENT': 'claude',
            'WORK_FALLBACK_AGENT': 'codex', 'WORK_REVIEW_AGENT': 'none', 'WORK_MODEL': 'test-claude',
            'WORK_REVIEW_MODEL': 'test-review', 'WORK_WAIT': '60',
        }))
        self.stack.enter_context(patch.object(next_issue, 'WORKFLOW', self.root))
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.lock = self.stack.enter_context((self.directory / 'runner.lock').open('a'))

    def run_loop(self):
        return work.run(self.game, self.directory, self.lock.fileno())

    def records(self):
        return [json.loads(line) for line in (self.directory / 'attempts.jsonl').read_text().splitlines()]

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
        self.assertGreater(json.loads((self.directory / 'cooldowns.json').read_text())['claude'], 0)

    def test_persisted_cooldown_skips_provider_on_restart(self):
        (self.directory / 'cooldowns.json').write_text(json.dumps({'claude': 9999999999}))
        self.issue.write_text('**Status:** in progress\n')
        (self.game / 'code.txt').write_text('unfinished tracked work\n')
        (self.game / 'new.txt').write_text('unfinished untracked work\n')
        self.assertEqual(self.run_loop(), 0)
        self.assertEqual([r['provider'] for r in self.records()], ['codex'])

    def test_authentication_stops_without_retry_or_fallback(self):
        with patch.dict(os.environ, {'TEST_SCENARIO': 'auth'}):
            self.assertEqual(self.run_loop(), 1)
        self.assertEqual([r['outcome'] for r in self.records()], ['authentication'])

    def test_implementation_failure_stops_after_two_attempts(self):
        with patch.dict(os.environ, {'TEST_SCENARIO': 'failure'}):
            self.assertEqual(self.run_loop(), 1)
        self.assertEqual([r['outcome'] for r in self.records()], ['failure', 'failure'])
        self.assertFalse((self.directory / 'cooldowns.json').exists())

    def test_interrupt_snapshots_work(self):
        def interrupt(command, log, lock_fd):
            log.write_text('')
            (self.game / 'code.txt').write_text('interrupted edit\n')
            raise KeyboardInterrupt
        with patch.object(work, 'run_worker', interrupt):
            self.assertEqual(self.run_loop(), 130)
        self.assertEqual(self.records()[0]['outcome'], 'interrupted')
        self.assertEqual((self.game / 'code.txt').read_text(), 'interrupted edit\n')

    def test_dirty_unclaimed_repo_is_rejected(self):
        (self.game / 'code.txt').write_text('user work\n')
        with self.assertRaisesRegex(ValueError, 'uncommitted changes'):
            self.run_loop()
        self.assertFalse((self.root / 'calls.jsonl').exists())

    def test_second_runner_is_rejected(self):
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with patch.object(sys, 'argv', ['work.py', str(self.game)]):
            with self.assertRaisesRegex(SystemExit, 'already owns'):
                work.main()

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
            codex = work.worker_command('codex', self.game, 'issue.md')
            claude = work.worker_command('claude', self.game, 'issue.md')
            review = work.worker_command('codex', self.game, 'issue.md', 'review', axis='spec')
        self.assertIn('test-codex', codex)
        self.assertIn('codex-review', codex[-1])
        self.assertIn('codex-review', review)
        self.assertIn('override-claude', claude)

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


class ResultTests(unittest.TestCase):
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

    def test_unknown_reset_and_malformed_time_use_fallback(self):
        now = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)
        for message in ('resets tomorrow', 'resets 99pm (UTC)', 'resets 9pm (Unknown/Zone)'):
            self.assertEqual(retry_at(message, 60, now), now.timestamp() + 60)


if __name__ == '__main__':
    unittest.main()
