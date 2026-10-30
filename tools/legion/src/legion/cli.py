"""Legion's commands. Run them from the workflow root, or through `tools/legion.sh`."""

import argparse
import os
import sys

from .settings import Settings, SettingsError
from .tracker import Tracker, TrackerError


class Commands:
    """Each method is a command, taking the project repo relative to the workflow root."""

    def __init__(self, settings):
        self.settings = settings

    def cycle(self, project):
        return Tracker.for_project(self.settings.root, project).current_cycle()

    def next(self, project):
        """Print the next issue a worker should take in the current cycle, or nothing."""
        issue = self.cycle(project).next_issue()
        if issue:
            print(os.path.relpath(issue.path, self.settings.root))

    def status(self, project):
        """List every issue's status in the current cycle."""
        for number, issue in self.cycle(project).issues.items():
            print(f"{number}  {issue.status:12s} {issue.path.name}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="legion", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("next", "status"):
        command = commands.add_parser(name, help=getattr(Commands, name).__doc__)
        command.add_argument("project", help="the project's repo, relative to the workflow root (../<project>)")
    args = parser.parse_args(argv)
    try:
        getattr(Commands(Settings.load()), args.command)(args.project)
    except (SettingsError, TrackerError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
