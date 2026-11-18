"""Overmind's commands: the `overmind` group and its subcommands. Run them from the workflow root, or through
`tools/overmind.sh`.

| Module | Commands |
|---|---|
| `work.py` | The worker loop and its containers: `run`, `next`, `status`, `shell`, `build` |
| `dashboard.py` | The read-only issue board: `dashboard` |
| `memory.py` | The agents' memory, the context store: the `memory` group |

Settings load inside each command that needs them, so `memory` and `--help` work outside the workflow root.
This package is the only interface layer: it imports the domain packages, and none of them imports it.
"""

import subprocess
import sys

import click

from ..runner.loop import RunnerError
from ..runner.repo import UnsafeRepoError
from ..core.settings import SettingsError
from ..core.tracker import TrackerError
from .dashboard import dashboard
from .memory import memory
from .work import build, next_issue, run, shell, status

# What a command may fail with: main exits with the message, never a traceback.
FAILURES = (SettingsError, TrackerError, RunnerError, UnsafeRepoError, OSError, subprocess.CalledProcessError)


class OrderedGroup(click.Group):
    """A group whose help lists its commands in the order they were added, not alphabetically."""

    def list_commands(self, ctx):
        return list(self.commands)


@click.group(cls=OrderedGroup, context_settings={"help_option_names": ["-h", "--help"]})
def overmind():
    """Runs and observes the implementation of tickets by coding agents, and keeps their memory."""


for command in (run, next_issue, status, shell, build, dashboard, memory):
    overmind.add_command(command)


def main(argv=None):
    """Run a command; its exit code (the console script exits with it)."""
    try:
        code = overmind.main(args=argv, prog_name="overmind", standalone_mode=False)
    except click.exceptions.Exit as done:
        return done.exit_code
    except click.ClickException as error:
        error.show()
        return error.exit_code
    except click.Abort:
        click.echo("Aborted.", err=True)
        return 130
    except FAILURES as error:
        sys.exit(str(error))
    return code or 0
