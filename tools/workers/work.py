#!/usr/bin/env python3
"""Sequential implement, review and fix runner with model selection and provider cooldowns."""

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
from .work_attempt import failure_kind, final_message, git, read_result, retry_at, snapshot

AXES = ("standards", "spec")


def say(message):
    print(f"{datetime.now():%H:%M} {message}", flush=True)


def interrupt(*_):
    raise KeyboardInterrupt


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def other(provider):
    return "codex" if provider == "claude" else "claude"


def model_for(provider, role="MODEL"):
    # The generic setting applies only to its role's preferred provider; aliases aren't portable.
    preferred = os.environ.get("WORK_AGENT", "claude")
    if role == "REVIEW_MODEL":
        reviewer = os.environ.get("WORK_REVIEW_AGENT", other(preferred))
        preferred = preferred if reviewer == "none" else reviewer
    default = os.environ.get(f"WORK_{role}", "") if provider == preferred else ""
    return os.environ.get(f"WORK_{provider.upper()}_{role}", default)


def review_file(cycle, issue, axis):
    return cycle / "reviews" / f"{issue.name[:2]}-{axis}.md"


def worker_command(provider, game, issue, role="implement", handoff=False, axis=None, reviews=()):
    skill = ".agents/skills/implement/SKILL.md"
    if role == "review":
        instruction = (
            f"Read .agents/skills/code-review/SKILL.md and review {issue} on the {axis} axis only, "
            "against the issue's Base:, without asking the user questions. "
            f"Do not edit any file. End with the {axis} report as your final message."
        )
        model = model_for(provider, "REVIEW_MODEL")
    elif role == "fix":
        instruction = (
            f"Read {skill} and follow its Fix session for {issue}, "
            f"with the saved reviews {' and '.join(map(str, reviews))}. "
            "Work on this issue only, without asking the user questions. "
            "Record completed steps and remaining work in the issue's Progress section."
        )
        model = model_for(provider)
    else:
        instruction = (
            f"Read {skill} and follow it to implement {issue}. "
            "Work on this issue only, without asking the user questions. "
            "Preserve existing commits and unfinished changes when resuming. "
            "Record completed steps and remaining work in the issue's Progress section."
        )
        review_model = model_for(provider, "REVIEW_MODEL")
        if handoff:
            instruction += " Separate review sessions follow: stop at the skill's Review handoff after step 9."
        elif review_model:
            instruction += f" Use {review_model} for both code-review subagents; report if that model cannot be selected."
        model = model_for(provider)
    if provider == "codex":
        sandbox = "read-only" if role == "review" else "danger-full-access"
        command = ["codex", "exec", "--sandbox", sandbox, "-c",
                   'approval_policy="never"', "--color", "never", "--json"]
    else:
        command = ["claude", "-p", "--add-dir", str(game), "--permission-mode", "auto",
                   "--max-budget-usd", os.environ.get("WORK_BUDGET_USD", "15"),
                   "--output-format", "json"]
        if role == "review":
            command.append("--disallowedTools=Edit,Write,NotebookEdit")
    if model:
        command.extend(["--model", model])
    return command + [instruction]


def stop(child):
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


def run_workers(jobs, lock_fd):
    """Run (command, log) jobs at once; return their exit codes."""
    outputs, children = [], []
    try:
        for command, log in jobs:
            outputs.append(log.open("w"))
            # Children hold the lock too, so a killed runner cannot leave an unowned worker.
            children.append(subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=outputs[-1],
                                             stderr=subprocess.STDOUT, start_new_session=True,
                                             pass_fds=(lock_fd,)))
        return [child.wait() for child in children]
    except KeyboardInterrupt:
        for child in children:
            stop(child)
        raise
    finally:
        for output in outputs:
            output.close()


def run_worker(command, log, lock_fd):
    return run_workers([(command, log)], lock_fd)[0]


def providers():
    """Provider order per role: implementers, then reviewers (empty when the implementer reviews)."""
    preferred = os.environ.get("WORK_AGENT", "claude")
    fallback = os.environ.get("WORK_FALLBACK_AGENT", other(preferred))
    reviewer = os.environ.get("WORK_REVIEW_AGENT", other(preferred))
    if preferred not in ("codex", "claude") or fallback not in ("codex", "claude", "none") \
            or reviewer not in ("codex", "claude", "none"):
        raise ValueError("WORK_AGENT must be codex or claude; "
                         "WORK_FALLBACK_AGENT and WORK_REVIEW_AGENT must be codex, claude or none")
    if not shutil.which(preferred):
        raise ValueError(f"{preferred} is not installed or not on PATH")
    implementers = [preferred]
    if fallback != "none" and fallback != preferred:
        if shutil.which(fallback):
            implementers.append(fallback)
        else:
            say(f"{fallback} unavailable; running without fallback")
    if reviewer == "none":
        return implementers, []
    if not shutil.which(reviewer):
        say(f"{reviewer} unavailable; implementers review their own issues")
        return implementers, []
    # A reviewer out of quota is replaced by any available implementer, never waited for.
    return implementers, [reviewer] + [p for p in implementers if p != reviewer]


def new_attempt(directory, path, role, provider, axis=None):
    attempt = f"{path.stem}-{axis or role}-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
    log = directory / f"{attempt}.log"
    model = model_for(provider, "REVIEW_MODEL" if role == "review" else "MODEL")
    record = {"attempt": attempt, "issue": str(path.relative_to(next_issue.WORKFLOW)),
              "role": role, "axis": axis, "provider": provider, "model": model or "CLI default",
              "review_model": model_for(provider, "REVIEW_MODEL") or "inherited",
              "started_at": datetime.now(timezone.utc).isoformat(), "log": str(log)}
    return record, log


def run(game, directory, lock_fd):
    implementers, reviewers = providers()
    wait = int(os.environ.get("WORK_WAIT", "1800"))
    if wait < 1:
        raise ValueError("WORK_WAIT must be positive")
    cycle = next_issue.latest_cycle(game)
    issues = next_issue.read_issues(cycle)
    if git(game, "status", "--porcelain").strip() and not any(i["status"] in ("in progress", "in review") for i in issues.values()):
        raise ValueError(f"{game} has uncommitted changes and no issue is in progress or in review: commit or stash them first")
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
        path = issue["path"]
        reviews = [review_file(cycle, path, axis) for axis in AXES]
        missing = [axis for axis, review in zip(AXES, reviews) if not review.exists()]
        if issue["status"] != "in review":
            role = "implement"
        else:
            role = "review" if missing else "fix"
        available = (reviewers or implementers) if role == "review" else implementers
        provider = next((p for p in available if cooldowns.get(p, 0) <= time.time()), None)
        if provider is None:
            delay = max(1, min(cooldowns[p] for p in available) - time.time())
            say(f"All configured providers cooling down; next reset in {int(delay)}s (Ctrl-C stops safely)")
            while delay > 0:
                time.sleep(min(delay, 60))
                delay = min(cooldowns[p] for p in available) - time.time()
            continue
        if role == "review":
            attempts = [new_attempt(directory, path, role, provider, axis) for axis in missing]
            jobs = [(worker_command(provider, game, record["issue"], role, axis=record["axis"]), log)
                    for record, log in attempts]
        else:
            attempts = [new_attempt(directory, path, role, provider)]
            handoff = bool(reviewers) and issue is not next_issue.build_issue(issues)
            jobs = [(worker_command(provider, game, attempts[0][0]["issue"], role, handoff,
                                    reviews=[r.relative_to(next_issue.WORKFLOW) for r in reviews]),
                     attempts[0][1])]
        save_json(directory / "current.json", [record for record, _ in attempts])
        for record, log in attempts:
            say(f"{path.name}: {record['axis'] or role} using {provider} ({record['model']}); log: {log}")
        started = time.time()
        interrupted = False
        try:
            if role == "review":
                codes = run_workers(jobs, lock_fd)
            else:
                codes = [run_worker(*jobs[0], lock_fd)]
        except KeyboardInterrupt:
            interrupted = True
            codes = [None] * len(jobs)
        except OSError as error:
            for _, log in jobs:
                with log.open("a") as output:
                    output.write(f"Worker launch failed: {error}\n")
            codes = [127] * len(jobs)
        status = next_issue.read_issues(cycle)[path.name[:2]]["status"]
        finished = ("done", "blocked", "in review") if role == "implement" else ("done", "blocked")
        outcomes = []
        for (record, log), code in zip(attempts, codes):
            message, usage = read_result(log)
            recovery = None
            if interrupted:
                outcome = "interrupted"
            elif role == "review":
                report = final_message(log) if code == 0 else ""
                outcome = "reviewed" if report else failure_kind(message)
                if report:
                    review = review_file(cycle, path, record["axis"])
                    review.parent.mkdir(exist_ok=True)
                    head = git(game, "rev-parse", "--short", "HEAD").decode().strip()
                    review.write_text(f"# {record['axis'].capitalize()} review of {path.name}\n\n"
                                      f"Reviewer: {provider} ({record['model']}), at {head}.\n\n{report}\n")
            else:
                outcome = status if status in finished else failure_kind(message)
            if role != "review" and outcome not in finished:
                recovery = directory / f"{record['attempt']}-recovery"
                snapshot(game, path, recovery)
                say(f"Unfinished work preserved; recovery snapshot: {recovery}")
            record.update(exit_code=code, outcome=outcome, duration_seconds=round(time.time() - started, 2),
                          usage=usage, recovery=str(recovery) if recovery else None)
            with (directory / "attempts.jsonl").open("a") as output:
                output.write(json.dumps(record) + "\n")
            outcomes.append(outcome)
        save_json(directory / "current.json", [record for record, _ in attempts])
        if interrupted:
            return 130
        if all(outcome in finished + ("reviewed",) for outcome in outcomes):
            continue
        if "authentication" in outcomes:
            say(f"Stopping: {provider} authentication needs attention. See {directory}")
            return 1
        if "quota" in outcomes:
            message = "\n".join(read_result(log)[0] for _, log in jobs)
            cooldowns[provider] = retry_at(message, wait)
            save_json(state_file, cooldowns)
            say(f"{provider} quota exhausted; cooling down until {datetime.fromtimestamp(cooldowns[provider]).astimezone().isoformat()}")
            if "failure" not in outcomes:
                continue
        failures[path] = failures.get(path, 0) + 1
        say(f"Worker stopped (exit {codes}); {path.name} {status} ({failures[path]}/2)")
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
