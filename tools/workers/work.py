#!/usr/bin/env python3
"""Sequential implementation runner with model selection and provider cooldowns."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from uuid import uuid4

from . import next_issue
from .work_attempt import failure_kind, git, read_result, retry_at, snapshot


def say(message):
    print(f"{datetime.now():%H:%M} {message}", flush=True)


def interrupt(*_):
    raise KeyboardInterrupt


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def model_for(provider, role="MODEL"):
    # WORK_MODEL applies only to the preferred provider; aliases aren't portable.
    default = os.environ.get(f"WORK_{role}", "") if provider == os.environ.get("WORK_AGENT", "codex") else ""
    return os.environ.get(f"WORK_{provider.upper()}_{role}", default)


def worker_command(provider, game, issue):
    review_model = model_for(provider, "REVIEW_MODEL")
    instruction = (
        f"Read .agents/skills/implement/SKILL.md and follow it to implement {issue}. "
        "Work on this issue only, without asking the user questions. "
        "Preserve existing commits and unfinished changes when resuming. "
        "Record completed steps and remaining work in the issue's Progress section."
    )
    if review_model:
        instruction += f" Use {review_model} for both code-review subagents; report if that model cannot be selected."
    if provider == "codex":
        command = ["codex", "exec", "--sandbox", "danger-full-access", "-c",
                   'approval_policy="never"', "--color", "never", "--json"]
    else:
        command = ["claude", "-p", "--add-dir", str(game), "--permission-mode", "auto",
                   "--max-budget-usd", os.environ.get("WORK_BUDGET_USD", "15"),
                   "--output-format", "json"]
    model = model_for(provider)
    if model:
        command.extend(["--model", model])
    return command + [instruction]


def run_worker(command, log, lock_fd):
    with log.open("w") as output:
        # Child holds the lock too, so a killed runner cannot leave an unowned worker.
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output,
                                 stderr=subprocess.STDOUT, start_new_session=True,
                                 pass_fds=(lock_fd,))
        try:
            return child.wait()
        except KeyboardInterrupt:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            # Also stop any grandchildren that survived their parent's exit.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if child.poll() is None:
                child.wait()
            raise


def providers():
    preferred = os.environ.get("WORK_AGENT", "codex")
    fallback = os.environ.get("WORK_FALLBACK_AGENT", "claude" if preferred == "codex" else "codex")
    if preferred not in ("codex", "claude") or fallback not in ("codex", "claude", "none"):
        raise ValueError("WORK_AGENT must be codex or claude; WORK_FALLBACK_AGENT must be codex, claude or none")
    if not shutil.which(preferred):
        raise ValueError(f"{preferred} is not installed or not on PATH")
    selected = [preferred]
    if fallback != "none" and fallback != preferred:
        if shutil.which(fallback):
            selected.append(fallback)
        else:
            say(f"{fallback} unavailable; running without fallback")
    return selected


def run(game, directory, lock_fd):
    available = providers()
    wait = int(os.environ.get("WORK_WAIT", "1800"))
    if wait < 1:
        raise ValueError("WORK_WAIT must be positive")
    cycle = next_issue.latest_cycle(game)
    issues = next_issue.read_issues(cycle)
    if git(game, "status", "--porcelain").strip() and not any(i["status"] == "in progress" for i in issues.values()):
        raise ValueError(f"{game} has uncommitted changes and no issue is in progress: commit or stash them first")
    state_file = directory / "cooldowns.json"
    cooldowns = json.loads(state_file.read_text()) if state_file.exists() else {}
    failures = {}
    while True:
        issues = next_issue.read_issues(cycle)
        issue = next_issue.next_issue(issues)
        if issue is None:
            say("No issue is ready.")
            for item in issues.values():
                print(f"{item['status']:12s} {item['path'].name}")
            return 0
        provider = next((p for p in available if cooldowns.get(p, 0) <= time.time()), None)
        if provider is None:
            delay = max(1, min(cooldowns[p] for p in available) - time.time())
            say(f"All configured providers cooling down; next reset in {int(delay)}s (Ctrl-C stops safely)")
            while delay > 0:
                time.sleep(min(delay, 60))
                delay = min(cooldowns[p] for p in available) - time.time()
            continue
        path = issue["path"]
        attempt = f"{path.stem}-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        log = directory / f"{attempt}.log"
        started = time.time()
        record = {"attempt": attempt, "issue": str(path.relative_to(next_issue.WORKFLOW)),
                  "provider": provider, "model": model_for(provider) or "CLI default",
                  "review_model": model_for(provider, "REVIEW_MODEL") or "inherited",
                  "started_at": datetime.now(timezone.utc).isoformat(), "log": str(log)}
        save_json(directory / "current.json", record)
        say(f"{path.name} using {provider} ({record['model']}); log: {log}")
        interrupted = False
        code = None
        try:
            code = run_worker(worker_command(provider, game, record["issue"]), log, lock_fd)
        except KeyboardInterrupt:
            interrupted = True
        except OSError as error:
            with log.open("a") as output:
                output.write(f"Worker launch failed: {error}\n")
            code = 127
        message, usage = read_result(log)
        status = next_issue.read_issues(cycle)[path.name[:2]]["status"]
        outcome = "interrupted" if interrupted else status if status in ("done", "blocked") else failure_kind(message)
        recovery = None
        if outcome not in ("done", "blocked"):
            recovery = directory / f"{attempt}-recovery"
            snapshot(game, path, recovery)
            say(f"Unfinished work preserved; recovery snapshot: {recovery}")
        record.update(exit_code=code, outcome=outcome, duration_seconds=round(time.time() - started, 2),
                      usage=usage, recovery=str(recovery) if recovery else None)
        save_json(directory / "current.json", record)
        with (directory / "attempts.jsonl").open("a") as output:
            output.write(json.dumps(record) + "\n")
        if interrupted:
            return 130
        if outcome in ("done", "blocked"):
            continue
        if outcome == "quota":
            cooldowns[provider] = retry_at(message, wait)
            save_json(state_file, cooldowns)
            say(f"{provider} quota exhausted; cooling down until {datetime.fromtimestamp(cooldowns[provider]).astimezone().isoformat()}")
            continue
        if outcome == "authentication":
            say(f"Stopping: {provider} authentication needs attention. See {log}")
            return 1
        failures[path] = failures.get(path, 0) + 1
        say(f"Worker stopped (exit {code}); {path.name} {status} ({failures[path]}/2)")
        if failures[path] >= 2:
            return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", help="game repo, relative to this workflow repo")
    args = parser.parse_args()
    os.chdir(next_issue.WORKFLOW)
    game = next_issue.game_root(args.game)
    directory = next_issue.WORKFLOW / "artifacts" / "work" / game.name
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "runner.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit(f"A worker loop already owns {game}. Stop it before starting another.")
        signal.signal(signal.SIGTERM, interrupt)
        try:
            return run(game, directory, lock.fileno())
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
