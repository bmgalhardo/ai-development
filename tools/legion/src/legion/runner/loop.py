"""The worker loop for one project: next issue, step, provider, run, record, outcome."""

from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime
import fcntl
import shlex
import signal
import subprocess
import time

from pydantic import BaseModel

from ..container import Container
from ..prompts import Prompts
from ..providers import registry
from ..tracker import Cycle, Tracker
from ..utils import save_json, say
from .attempts import Attempt, AttemptLog
from .cooldowns import Cooldowns
from .dashboard import Dashboard
from .repo import Repo
from .router import Router, Situation, Stop, Wait
from .sessions import TIMED_OUT, Session, Sessions

AXES = ("standards", "spec")
FINISHED = {"implement": ("done", "blocked", "in review"), "review": ("reviewed",), "fix": ("done", "blocked")}
STOPPED = 130  # the exit code of a run stopped by Ctrl-C or SIGTERM


class RunnerError(Exception):
    """A run that can't start or go on: another runner, no usable provider, or a dirty checkout."""


class Job(BaseModel):
    """An attempt and the command of its session."""

    attempt: Attempt
    command: list[str]


class Step(BaseModel):
    """What an issue needs next: implement it, review it on its missing axes, or fix it."""

    role: str
    axes: list[str] = []


class Launch:
    """A run for one project: its lock, the board beside it, and the loop."""

    def __init__(self, settings, project):
        self.settings = settings
        self.project = project
        self.folder = settings.runner_folder(project)

    def run(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        with (self.folder / "runner.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RunnerError(f"A worker loop already owns {self.project}. Stop it before starting another.") \
                    from None
            signal.signal(signal.SIGTERM, self.interrupt)
            if self.settings.container:
                # Holding the lock, any container of this project is left over from a killed runner.
                Container.remove_leftovers(self.project)
            dashboard = Dashboard(self.settings, self.folder)
            dashboard.start()
            try:
                return Runner(self.settings, self.project, lock.fileno()).run()
            except KeyboardInterrupt:
                return STOPPED
            finally:
                dashboard.stop()

    @staticmethod
    def interrupt(*_):
        raise KeyboardInterrupt


class Runner:
    """Takes the current cycle's issues one step at a time until none is ready."""

    def __init__(self, settings, project, lock_fd):
        self.settings = settings
        self.project = project
        self.root = settings.root
        self.repo = Repo(project)
        self.folder = settings.runner_folder(project)
        self.cooldowns = Cooldowns(self.root / ".scratch" / "runner" / "cooldowns.json")
        self.sessions = Sessions(lock_fd, settings.timeout, self.root)
        self.prompts = Prompts()
        self.router = Router(self.usable_providers())
        self.failures = Counter()  # issue path -> implementation failures this run
        self.failed = defaultdict(set)  # issue path -> providers that failed it this run; a retry prefers another
        self.signed_out = set()  # providers whose login failed; they sit out until the runner restarts

    def usable_providers(self):
        """The preference, without providers that aren't installed."""
        installed = registry.installed()
        for name in self.settings.preference:
            if name not in installed:
                say(f"{name} is not installed; running without it")
        usable = [name for name in self.settings.preference if name in installed]
        if not usable:
            raise RunnerError("No provider in LEGION_PREFERENCE is installed")
        return usable

    def run(self):
        cycle = Tracker.for_project(self.root, self.project).current_cycle()
        self.attempts = AttemptLog(cycle.path, self.root)
        self.check_clean(cycle)
        while True:
            cycle = Cycle.read(cycle.path)
            issue = cycle.next_issue()
            if issue is None:
                return self.finish(cycle)
            code = self.work_on(cycle, issue)
            if code is not None:
                return code

    def check_clean(self, cycle):
        claimed = any(issue.status in ("in progress", "in review") for issue in cycle.issues.values())
        if self.repo.dirty() and not claimed:
            raise RunnerError(f"{self.project} has uncommitted changes and no issue is in progress or in review: "
                             "commit or stash them first")

    def step(self, cycle, issue):
        if issue.status != "in review":
            return Step(role="implement")
        missing = [axis for axis in AXES if not self.review_file(cycle, issue, axis).exists()]
        return Step(role="review", axes=missing) if missing else Step(role="fix")

    def work_on(self, cycle, issue):
        """One step of the issue with the provider the router chooses; an exit code ends the run."""
        step = self.step(cycle, issue)
        situation = Situation(cooldowns=self.cooldowns.until, signed_out=self.signed_out,
                              failed=self.failed[issue.path], implementer=self.attempts.implementer(issue.path))
        decision = self.router.choose(step.role, situation, time.time())
        if isinstance(decision, Stop):
            say(f"Stopping: {', '.join(decision.signed_out)} authentication needs attention. "
                f"See {self.attempts.folder}")
            return 1
        if isinstance(decision, Wait):
            return self.wait(decision.until)
        provider = registry.provider(decision.provider, self.settings)
        jobs = self.jobs(cycle, issue, step, provider)
        codes = self.launch(provider, jobs)
        outcomes = [self.record(cycle, issue, provider, job.attempt, code) for job, code in zip(jobs, codes)]
        self.save_current([job.attempt for job in jobs])
        return STOPPED if None in codes else self.react(issue, provider, jobs, outcomes)

    def jobs(self, cycle, issue, step, provider):
        """The step's attempts (one per missing review axis), each with its session's command."""
        attempts = [self.attempts.new(issue.path, step.role, provider.name, self.settings, axis)
                    for axis in step.axes or [None]]
        self.save_current(attempts)
        for attempt in attempts:
            say(f"{issue.path.name}: {attempt.axis or attempt.role} using {provider.name} ({attempt.model}); "
                f"log: {attempt.log}")
        return [Job(attempt=attempt,
                    command=provider.command(step.role, self.prompt(cycle, issue, attempt), self.project))
                for attempt in attempts]

    def save_current(self, attempts):
        """The latest attempts, for the dashboard; with outcomes once they end."""
        save_json(self.folder / "current.json", [attempt.record() for attempt in attempts])

    def prompt(self, cycle, issue, attempt):
        reviews = " and ".join(str(self.review_file(cycle, issue, axis).relative_to(self.root)) for axis in AXES)
        return self.prompts.render(attempt.role, issue=attempt.issue, axis=attempt.axis, reviews=reviews)

    def launch(self, provider, jobs):
        """Run the jobs' sessions; their exit codes, None for each if interrupted, 127 if they couldn't start.

        In containers, each session's container is removed when the sessions end, however they end.
        """
        try:
            with ExitStack() as containers:
                return self.sessions.run([self.session(containers, provider, job) for job in jobs])
        except KeyboardInterrupt:
            return [None] * len(jobs)
        except OSError as error:
            for job in jobs:
                with job.attempt.log_path.open("a") as log:
                    log.write(f"Worker launch failed: {error}\n")
            return [127] * len(jobs)

    def session(self, containers, provider, job):
        """The job's session: its command as is, or in a worker container (LEGION_CONTAINER)."""
        if not self.settings.container:
            return Session(command=job.command, log=job.attempt.log_path)
        container = containers.enter_context(Container(self.settings, self.project, provider, job.attempt.role))
        return Session(command=container.command(job.command), log=job.attempt.log_path,
                       environment=container.environment(), keep=container.keep(), started=container.started,
                       stopped=container.remove)

    def record(self, cycle, issue, provider, attempt, code):
        """Read the session's result, save a review, snapshot unfinished work, and append the attempt."""
        result = provider.parse_log(attempt.log_path)
        status = Cycle.read(cycle.path).issues[issue.number].status
        outcome = self.outcome(attempt.role, provider, result, code, status)
        attempt.recovery = None
        if outcome == "reviewed":
            self.save_review(cycle, issue, attempt, result.report)
        if attempt.role != "review" and outcome not in FINISHED[attempt.role]:
            attempt.recovery = str(self.attempts.recovery(attempt))
            self.repo.snapshot(issue.path, self.attempts.recovery(attempt))
            say(f"Unfinished work preserved; recovery snapshot: {attempt.recovery}")
        started = datetime.fromisoformat(attempt.started_at).timestamp()
        attempt.exit_code, attempt.outcome, attempt.usage = code, outcome, result.usage
        attempt.duration_seconds = round(time.time() - started, 2)
        self.attempts.append(attempt)
        return outcome

    @staticmethod
    def outcome(role, provider, result, code, status):
        """What came of a session: its issue's new status, reviewed, timeout, interrupted, or a failure kind."""
        if code is None:
            return "interrupted"
        if role == "review" and code == 0 and result.report:
            return "reviewed"
        if role != "review" and status in FINISHED[role]:
            return status
        return "timeout" if code == TIMED_OUT else provider.classify(result.messages)

    def react(self, issue, provider, jobs, outcomes):
        """Continue after finished work, an authentication failure or a quota stop; count other failures."""
        if all(outcome in FINISHED[jobs[0].attempt.role] for outcome in outcomes):
            return None
        if "authentication" in outcomes:
            self.signed_out.add(provider.name)
            say(f"{provider.name} authentication failed; continuing without it (log in and restart to use it again)")
            return None
        if "quota" in outcomes:
            messages = "\n".join(provider.parse_log(job.attempt.log_path).messages for job in jobs)
            self.cooldowns.set(provider.name, provider.reset_at(messages, self.settings.wait))
            say(f"{provider.name} quota exhausted; cooling down until {self.cooldowns.reset_time(provider.name)}")
            if "failure" not in outcomes:
                return None
        self.failures[issue.path] += 1
        self.failed[issue.path].add(provider.name)
        say(f"Worker stopped ({', '.join(outcomes)}); {issue.path.name} ({self.failures[issue.path]}/2)")
        return 1 if self.failures[issue.path] >= 2 else None

    def save_review(self, cycle, issue, attempt, report):
        review = self.review_file(cycle, issue, attempt.axis)
        review.parent.mkdir(exist_ok=True)
        review.write_text(f"# {attempt.axis.capitalize()} review of {issue.path.name}\n\n"
                          f"Reviewer: {attempt.provider} ({attempt.model}), at {self.repo.head()}.\n\n{report}\n")

    @staticmethod
    def review_file(cycle, issue, axis):
        return cycle.path / "reviews" / f"{issue.number}-{axis}.md"

    def wait(self, until):
        """Wait for the earliest reset, in steps of at most a minute; the loop then routes again."""
        say(f"All configured providers cooling down; next reset in {int(until - time.time())}s (Ctrl-C stops safely)")
        while (delay := until - time.time()) > 0:
            time.sleep(min(delay, 60))
        return None

    def finish(self, cycle):
        say("No issue is ready.")
        for issue in cycle.issues.values():
            print(f"{issue.status:12s} {issue.path.name}")
        return self.after_build() if cycle.build and cycle.build.status == "done" else 0

    def after_build(self):
        """Run LEGION_AFTER_BUILD once the build is done; its exit code becomes the runner's."""
        command = self.settings.after_build
        if not command:
            say("The build is done; no after-build command (LEGION_AFTER_BUILD)")
            return 0
        command = command.replace("{project}", shlex.quote(str(self.project)))
        say(f"The build is done; running {command}")
        code = subprocess.run(command, shell=True, cwd=self.root, stdin=subprocess.DEVNULL).returncode
        if code:
            say(f"After-build command failed (exit {code})")
        return code
