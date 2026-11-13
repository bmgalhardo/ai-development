"""The issue board, started beside a run and stopped with it."""

import importlib.util
import socket
import subprocess
import sys

from ..utils import say
from .sessions import Sessions


class Dashboard:
    def __init__(self, settings, folder):
        self.settings = settings
        self.log = folder / "dashboard.log"
        self.child = None

    def command(self):
        return [sys.executable, "-m", "overmind.cli", "dashboard",
                "--host", self.settings.dashboard_host, "--port", str(self.settings.dashboard_port)]

    def start(self):
        """Start the board unless it is turned off, its port is taken, or its dependencies are missing."""
        port = self.settings.dashboard_port
        if not self.settings.dashboard:
            return
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                say(f"Dashboard port {port} already in use; not starting another")
                return
        if importlib.util.find_spec("fastapi") is None:
            say("Dashboard not started: run through tools/overmind.sh, which installs its dependencies")
            return
        with self.log.open("w") as log:
            self.child = subprocess.Popen(self.command(), stdin=subprocess.DEVNULL, stdout=log,
                                          stderr=subprocess.STDOUT, start_new_session=True, cwd=self.settings.root)
        say(f"Dashboard on port {port}; it stops with this runner")

    def stop(self):
        if self.child:
            Sessions.stop(self.child)
