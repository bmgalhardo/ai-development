#!/usr/bin/env python3
"""Sequential implement, review and fix runner with model selection and provider cooldowns."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4

from . import next_issue
from tools.publish.publish import server_url
from tools.settings import load_env
from .work_attempt import failure_kind, final_message, git, read_result, retry_at, snapshot

AXES = ("standards", "spec")
TIMED_OUT = 124  # the exit code of coreutils timeout


def cooldowns_file():
    """Provider reset times, shared by every project's runner: a provider's quota is per account."""
    return next_issue.WORKFLOW / ".scratch" / "runner" / "cooldowns.json"


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


def worker_command(provider, project, issue, role="implement", handoff=False, axis=None, reviews=()):
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
        # Codex's own sandbox can't start in a container; there the read-only mounts are the reviewer's sandbox.
        sandbox = "read-only" if role == "review" and not containerized() else "danger-full-access"
        command = ["codex", "exec", "--sandbox", sandbox, "-c",
                   'approval_policy="never"', "--color", "never", "--json"]
        if containerized():
            # The container has no .git for the workflow folder, and no host config that trusts it.
            command.append("--skip-git-repo-check")
    else:
        command = ["claude", "-p", "--add-dir", str(project), "--permission-mode", "auto",
                   "--max-budget-usd", os.environ.get("WORK_BUDGET_USD", "15"),
                   "--output-format", "json"]
        if role == "review":
            command.append("--disallowedTools=Edit,Write,NotebookEdit")
    if model:
        command.extend(["--model", model])
    command.append(instruction)
    if containerized():
        mounts = "review" if role == "review" else "implement"
        command = [str(next_issue.WORKFLOW / "tools/container/run.sh"), provider, mounts, str(project)] + command
    return command


def containerized():
    """Whether sessions run in worker containers (tools/container/README.md)."""
    return os.environ.get("WORK_CONTAINER", "0") == "1"


def remove_containers(label):
    """Remove the worker containers with this label; killing their docker client leaves them running."""
    try:
        found = subprocess.run(["docker", "ps", "-aq", "--filter", f"label={label}"],
                               capture_output=True, text=True).stdout.split()
        if found:
            subprocess.run(["docker", "rm", "-f", *found], capture_output=True)
    except FileNotFoundError:
        pass


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
    if containerized():
        remove_containers(f"work.pid={child.pid}")


def start_dashboard(directory):
    """Start the issue dashboard for this run, unless disabled or its port is taken; None otherwise."""
    port = int(os.environ.get("WORK_DASHBOARD_PORT", "8765"))
    if os.environ.get("WORK_DASHBOARD", "1") == "0":
        return None
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            say(f"Dashboard port {port} already in use; not starting another")
            return None
    if not shutil.which("uv"):
        say("Dashboard not started: uv not found")
        return None
    with (directory / "dashboard.log").open("w") as log:
        child = subprocess.Popen(["uv", "run", "--project", "tools/dashboard", "python", "-m", "tools.dashboard",
                                  "--host", os.environ.get("WORK_DASHBOARD_HOST", "127.0.0.1"), "--port", str(port)],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True)
    say(f"Dashboard on port {port}; it stops with this runner")
    return child


def publish_build(project):
    """Publish the project's outputs once its build is done; 0 when there is nothing to publish."""
    if os.environ.get("WORK_PUBLISH", "1") == "0":
        say("Not publishing: WORK_PUBLISH=0")
        return 0
    if not (project / ".agents/context/publishing.md").is_file():
        say("Nothing to publish: the project has no publishing doc")
        return 0
    if not server_url():
        say("Not publishing: no publish server (PUBLISH_URL)")
        return 0
    say("Publishing the build")
    code = subprocess.run([sys.executable, "-m", "tools.publish.publish", str(project)],
                          cwd=next_issue.WORKFLOW, stdin=subprocess.DEVNULL).returncode
    if code:
        say(f"Publishing failed (exit {code}); fix it and run /publish")
    return code


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
        # A session can finish its work yet never exit, e.g. waiting on a display server it started.
        timeout = int(os.environ.get("WORK_TIMEOUT", "14400"))
        expired = []
        def expire():
            for child in children:
                if child.poll() is None:
                    expired.append(child)
                    stop(child)
        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            codes = [child.wait() for child in children]
        finally:
            timer.cancel()
        for index, child in enumerate(children):
            if child in expired:
                outputs[index].write(f"\nWorker timed out after {timeout}s and was stopped.\n")
                codes[index] = TIMED_OUT
        return codes
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


def run(project, directory, lock_fd):
    implementers, reviewers = providers()
    wait = int(os.environ.get("WORK_WAIT", "1800"))
    if wait < 1:
        raise ValueError("WORK_WAIT must be positive")
    if int(os.environ.get("WORK_TIMEOUT", "14400")) < 1:
        raise ValueError("WORK_TIMEOUT must be positive")
    cycle = next_issue.current_cycle(project)
    issues = next_issue.read_issues(cycle)
    # The runner's state stays in directory; the cycle's attempts are kept with its issues.
    logs = cycle / "work"
    logs.mkdir(exist_ok=True)
    if git(project, "status", "--porcelain").strip() and not any(i["status"] in ("in progress", "in review") for i in issues.values()):
        raise ValueError(f"{project} has uncommitted changes and no issue is in progress or in review: commit or stash them first")
    state_file = cooldowns_file()
    state_file.parent.mkdir(exist_ok=True)
    cooldowns = json.loads(state_file.read_text()) if state_file.exists() else {}
    failures = {}
    failed = {}  # issue path -> providers that failed it this run; the retry prefers another
    signed_out = set()  # providers whose login failed; they sit out until the runner restarts
    while True:
        issues = next_issue.read_issues(cycle)
        issue = next_issue.next_issue(issues)
        if issue is None:
            say("No issue is ready.")
            for item in issues.values():
                print(f"{item['status']:12s} {item['path'].name}")
            build = next_issue.build_issue(issues)
            return publish_build(project) if build and build["status"] == "done" else 0
        path = issue["path"]
        reviews = [review_file(cycle, path, axis) for axis in AXES]
        missing = [axis for axis, review in zip(AXES, reviews) if not review.exists()]
        if issue["status"] != "in review":
            role = "implement"
        else:
            role = "review" if missing else "fix"
        available = [p for p in ((reviewers or implementers) if role == "review" else implementers)
                     if p not in signed_out]
        if not available:
            say(f"Stopping: {', '.join(sorted(signed_out))} authentication needs attention. See {logs}")
            return 1
        ready = [p for p in available if cooldowns.get(p, 0) <= time.time()]
        provider = next((p for p in ready if p not in failed.get(path, ())), ready[0] if ready else None)
        if provider is None:
            delay = max(1, min(cooldowns[p] for p in available) - time.time())
            say(f"All configured providers cooling down; next reset in {int(delay)}s (Ctrl-C stops safely)")
            while delay > 0:
                time.sleep(min(delay, 60))
                delay = min(cooldowns[p] for p in available) - time.time()
            continue
        if role == "review":
            attempts = [new_attempt(logs, path, role, provider, axis) for axis in missing]
            jobs = [(worker_command(provider, project, record["issue"], role, axis=record["axis"]), log)
                    for record, log in attempts]
        else:
            attempts = [new_attempt(logs, path, role, provider)]
            handoff = bool(reviewers) and issue is not next_issue.build_issue(issues)
            jobs = [(worker_command(provider, project, attempts[0][0]["issue"], role, handoff,
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
                outcome = "reviewed" if report else "timeout" if code == TIMED_OUT else failure_kind(message)
                if report:
                    review = review_file(cycle, path, record["axis"])
                    review.parent.mkdir(exist_ok=True)
                    head = git(project, "rev-parse", "--short", "HEAD").decode().strip()
                    review.write_text(f"# {record['axis'].capitalize()} review of {path.name}\n\n"
                                      f"Reviewer: {provider} ({record['model']}), at {head}.\n\n{report}\n")
            else:
                outcome = status if status in finished else "timeout" if code == TIMED_OUT else failure_kind(message)
            if role != "review" and outcome not in finished:
                recovery = logs / f"{record['attempt']}-recovery"
                snapshot(project, path, recovery)
                say(f"Unfinished work preserved; recovery snapshot: {recovery}")
            record.update(exit_code=code, outcome=outcome, duration_seconds=round(time.time() - started, 2),
                          usage=usage, recovery=str(recovery) if recovery else None)
            with (logs / "attempts.jsonl").open("a") as output:
                output.write(json.dumps(record) + "\n")
            outcomes.append(outcome)
        save_json(directory / "current.json", [record for record, _ in attempts])
        if interrupted:
            return 130
        if all(outcome in finished + ("reviewed",) for outcome in outcomes):
            continue
        if "authentication" in outcomes:
            signed_out.add(provider)
            say(f"{provider} authentication failed; continuing without it (log in and restart to use it again)")
            continue
        if "quota" in outcomes:
            message = "\n".join(read_result(log)[0] for _, log in jobs)
            cooldowns[provider] = retry_at(message, wait)
            save_json(state_file, cooldowns)
            say(f"{provider} quota exhausted; cooling down until {datetime.fromtimestamp(cooldowns[provider]).astimezone().isoformat()}")
            if "failure" not in outcomes:
                continue
        failures[path] = failures.get(path, 0) + 1
        failed.setdefault(path, set()).add(provider)
        say(f"Worker stopped (exit {codes}); {path.name} {status} ({failures[path]}/2)")
        if failures[path] >= 2:
            return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="project repo, relative to this workflow repo")
    args = parser.parse_args()
    load_env()
    os.chdir(next_issue.WORKFLOW)
    project = next_issue.project_root(args.project)
    directory = next_issue.WORKFLOW / ".scratch" / project.name / "runner"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "runner.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit(f"A worker loop already owns {project}. Stop it before starting another.")
        signal.signal(signal.SIGTERM, interrupt)
        if containerized():
            # Holding the lock, any container of this project is left over from a killed runner.
            remove_containers(f"work.project={project.name}")
        dashboard = start_dashboard(directory)
        try:
            return run(project, directory, lock.fileno())
        except KeyboardInterrupt:
            return 130
        finally:
            if dashboard:
                stop(dashboard)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
