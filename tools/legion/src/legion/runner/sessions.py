"""Worker sessions as child processes: started together, held to a time limit, stopped with their children."""

import os
from pathlib import Path
import signal
import subprocess
import threading
from typing import Callable

from pydantic import BaseModel

TIMED_OUT = 124  # the exit code of coreutils timeout


class Session(BaseModel):
    """A session's command and log, with variables to add to its environment and file descriptors it holds.

    `started` runs once the session's process holds them, so the runner can let go of its own copies;
    `stopped` runs right after the session is stopped (a timeout or Ctrl-C), before the others end.
    """

    command: list[str]
    log: Path
    environment: dict[str, str] = {}
    keep: list[int] = []
    started: Callable[[], None] | None = None
    stopped: Callable[[], None] | None = None


class Sessions:
    def __init__(self, lock_fd, timeout, cwd):
        self.lock_fd = lock_fd
        self.timeout = timeout
        self.cwd = cwd

    def run(self, sessions):
        """Run the sessions at once; return their exit codes. Ctrl-C stops them all."""
        outputs, children = [], []
        try:
            for session in sessions:
                outputs.append(session.log.open("w"))
                # Children hold the lock too, so a killed runner cannot leave an unowned worker.
                children.append(subprocess.Popen(session.command, stdin=subprocess.DEVNULL, stdout=outputs[-1],
                                                 stderr=subprocess.STDOUT, start_new_session=True,
                                                 pass_fds=(self.lock_fd, *session.keep), cwd=self.cwd,
                                                 env=os.environ | session.environment))
                if session.started:
                    session.started()
            return self.wait(sessions, children, outputs)
        except KeyboardInterrupt:
            for session, child in zip(sessions, children):
                self.stop(child)
                self.stopped(session)
            raise
        finally:
            for output in outputs:
                output.close()

    def wait(self, sessions, children, outputs):
        """Wait for every child; one still running at the time limit is stopped and gets TIMED_OUT.

        A session can finish its work yet never exit, e.g. waiting on a display server it started.
        """
        expired = []

        def expire():
            for session, child in zip(sessions, children):
                if child.poll() is None:
                    expired.append(child)
                    self.stop(child)
                    self.stopped(session)
        timer = threading.Timer(self.timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            codes = [child.wait() for child in children]
        finally:
            timer.cancel()
            timer.join()  # a stopped session's cleanup finishes before the codes return
        for index, child in enumerate(children):
            if child in expired:
                outputs[index].write(f"\nWorker timed out after {self.timeout}s and was stopped.\n")
                codes[index] = TIMED_OUT
        return codes

    @staticmethod
    def stopped(session):
        if session.stopped:
            session.stopped()

    @staticmethod
    def stop(child):
        """Stop a session's process group: SIGTERM, then SIGKILL for whatever survives."""
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if child.poll() is None:
            child.wait()
