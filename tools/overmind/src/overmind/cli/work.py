"""The worker loop and its containers: run it, see what is next, read every issue's status, open a worker
shell, build the images."""

import os
import subprocess
import sys

import click

from .. import container
from ..providers import registry
from ..runner.loop import Launch
from ..settings import Settings
from ..tracker import Tracker

PROJECT_HELP = "the project's repo, relative to the workflow root (../<project>)"

project_argument = click.argument("project", metavar="PROJECT")


def _cycle(settings, project):
    return Tracker.for_project(settings.root, project).current_cycle()


@click.command()
@project_argument
def run(project):
    """Run the worker loop on the project until no issue is ready; returns the runner's exit code."""
    settings = Settings.load()
    return Launch(settings, Tracker.project(settings.root, project)).run()


@click.command("next")
@project_argument
def next_issue(project):
    """Print the next issue a worker should take in the current cycle, or nothing."""
    settings = Settings.load()
    cycle = _cycle(settings, project)
    issue = cycle.next_issue()
    if issue:
        click.echo(os.path.relpath(issue.path, settings.root))
    elif cycle.stuck():
        click.echo(cycle.stuck_message(), err=True)
        return 1


@click.command()
@project_argument
def status(project):
    """List every issue's status in the current cycle."""
    settings = Settings.load()
    cycle = _cycle(settings, project)
    for number, issue in cycle.issues.items():
        build_mark = " (build)" if issue is cycle.build else ""
        click.echo(f"{number}  {issue.status:12s} {issue.path.name}{build_mark}")


@click.command(context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False})
@click.argument("provider", type=click.Choice(registry.names()))
@click.argument("role", type=click.Choice(("implement", "review", "fix")))
@project_argument
@click.argument("argv", metavar="[COMMAND]...", nargs=-1, type=click.UNPROCESSED)
def shell(provider, role, project, argv):
    """Open a shell, or run a command, in a worker container for a provider in a role; its exit code.

    ROLE review mounts the project read-only. COMMAND defaults to bash.
    """
    settings = Settings.load()
    repo = Tracker.project(settings.root, project)
    tty = sys.stdin.isatty() and sys.stdout.isatty()
    with container.Container(settings, repo, registry.provider(provider, settings), role, tty=tty) as worker:
        return subprocess.run(worker.command(list(argv) or ["bash"]), cwd=settings.root,
                              env=os.environ | worker.environment(), pass_fds=worker.keep(), check=False).returncode


@click.command()
@click.argument("project", metavar="[PROJECT]", required=False)
def build(project):
    """Build the worker image, then the project's image on it when the project has a recipe; its exit code."""
    settings = Settings.load()
    target = [str(Tracker.project(settings.root, project))] if project else []
    return subprocess.run([str(container.FOLDER / "build.sh"), *target], check=False).returncode
