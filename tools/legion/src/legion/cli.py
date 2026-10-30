"""Legion's commands. Run them from the workflow root, or through `tools/legion.sh`."""

import argparse
import os
import subprocess
import sys

from .runner.loop import Launch, RunnerError
from .runner.repo import UnsafeRepoError
from .settings import Settings, SettingsError
from .tracker import Tracker, TrackerError

PROJECT_HELP = "the project's repo, relative to the workflow root (../<project>)"


class Commands:
    """Each method is a command, taking the parsed arguments."""

    def __init__(self, settings):
        self.settings = settings

    def _cycle(self, project):
        return Tracker.for_project(self.settings.root, project).current_cycle()

    def run(self, args):
        """Run the worker loop on the project until no issue is ready; returns the runner's exit code."""
        return Launch(self.settings, Tracker.project(self.settings.root, args.project)).run()

    def next(self, args):
        """Print the next issue a worker should take in the current cycle, or nothing."""
        issue = self._cycle(args.project).next_issue()
        if issue:
            print(os.path.relpath(issue.path, self.settings.root))

    def status(self, args):
        """List every issue's status in the current cycle."""
        for number, issue in self._cycle(args.project).issues.items():
            print(f"{number}  {issue.status:12s} {issue.path.name}")

    def dashboard(self, args):
        """Serve the read-only issue board; it never starts or touches workers."""
        try:
            import uvicorn
            from .dashboard.app import create_app
        except ImportError:
            sys.exit("The dashboard needs Legion's dashboard group: run it through tools/legion.sh dashboard")
        uvicorn.run(create_app(self.settings.root), host=args.host or self.settings.dashboard_host,
                    port=args.port or self.settings.dashboard_port)


def build_parser():
    parser = argparse.ArgumentParser(prog="legion", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "next", "status"):
        commands.add_parser(name, help=getattr(Commands, name).__doc__).add_argument("project", help=PROJECT_HELP)
    dashboard = commands.add_parser("dashboard", help=Commands.dashboard.__doc__)
    dashboard.add_argument("--host", help="bind address (default: WORK_DASHBOARD_HOST, else this host only)")
    dashboard.add_argument("--port", type=int, help="port (default: WORK_DASHBOARD_PORT, else 8765)")
    return parser


def main(argv=None):
    """Run a command; its exit code (the console script exits with it)."""
    args = build_parser().parse_args(argv)
    try:
        code = getattr(Commands(Settings.load()), args.command)(args)
    except (SettingsError, TrackerError, RunnerError, UnsafeRepoError, OSError,
            subprocess.CalledProcessError) as error:
        sys.exit(str(error))
    return code or 0


if __name__ == "__main__":
    sys.exit(main())
