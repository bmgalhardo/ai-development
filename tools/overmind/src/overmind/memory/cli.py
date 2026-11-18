"""`overmind memory`: the context store's commands, as the `memory` group. See the README's Memory section.

The active profile loads inside each command, so the group needs no settings and works from any folder.
A ProfileError or StoreError ends the command with `overmind memory: <message>` and exit code 1.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

import click

from . import l0 as l0_map
from .profiles import OFF, Profile, ProfileError
from .store import GITHUB_PREFIX, ForgejoRepo, GitHubPublicRepo, NotFound, Repo, StoreError

REPO_HELP = "Another repo, read only: owner/name on the store's host, or github:owner/name (public)."
MESSAGE_HELP = "The commit message (default: '<action> PATH')."


class Failed(click.ClickException):
    """A memory command that could not finish, shown as `overmind memory: <message>`."""

    def show(self, file=None):
        click.echo(f"overmind memory: {self.message}", err=True)


class MemoryGroup(click.Group):
    """Turns the store's and the profile's errors into `Failed`, for every command in the group; its help
    lists the commands in the order they are defined (read, write, profiles)."""

    def list_commands(self, ctx):
        return list(self.commands)

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except (ProfileError, StoreError, OSError) as error:
            raise Failed(str(error)) from error


@click.group(cls=MemoryGroup, epilog="Set OVERMIND_MEMORY_PROFILE to pick a profile for one shell or one command.")
def memory():
    """The agents' memory: a private context store, read and written over its host's API, never cloned."""


repo_option = click.option("-r", "--repo", "ref", metavar="REPO", help=REPO_HELP)
message_option = click.option("-m", "--message", help=MESSAGE_HELP)


def _store() -> ForgejoRepo:
    profile = Profile.active().require()
    return ForgejoRepo(profile.api, profile.token, profile.ca)


def _repo(ref: str | None) -> Repo:
    if ref and ref.startswith(GITHUB_PREFIX):
        return GitHubPublicRepo(ref[len(GITHUB_PREFIX):])
    store = _store()
    return store.other(ref) if ref else store


def _write(path: str, content: bytes, message: str | None, store: ForgejoRepo | None = None) -> None:
    action, commit = (store or _store()).write(path, content, message)
    click.echo(f"{action} {path} {commit}")


# Read


@memory.command()
@repo_option
@click.argument("path")
def get(ref, path):
    """Print a file; it saves nothing."""
    sys.stdout.buffer.write(_repo(ref).read(path))
    sys.stdout.flush()


@memory.command()
@repo_option
@click.argument("folder", default="")
def ls(ref, folder):
    """List a folder; a folder ends in /."""
    for entry in _repo(ref).list(folder):
        click.echo(str(entry))


@memory.command()
def repos():
    """List the repos in L0.md's table, as references for -r."""
    text, _ = l0_map.fetch(Profile.active().require())
    for repo in l0_map.table(text):
        click.echo(f"{repo.ref:32s} {repo.description}")


@memory.command()
@click.option("--json", "as_json", is_flag=True, help="Wrap it as SessionStart additionalContext.")
def l0(as_json):
    """Print L0.md for a session start: the cache when the store is away, nothing when memory is off."""
    text = l0_map.for_session(Profile.active())
    output = l0_map.hook_output(text) if as_json else text
    if output:
        click.echo(output)


# Write


@memory.command()
@click.argument("path")
@message_option
def put(path, message):
    """Write stdin to a file, creating or replacing it in one commit."""
    _write(path, sys.stdin.buffer.read(), message)


@memory.command()
@click.argument("path")
@message_option
def edit(path, message):
    """Open a file in $VISUAL or $EDITOR and upload it if it changed; a new path creates the file."""
    store = _store()
    try:
        before = store.read(path)
    except NotFound:
        before = b""
    with tempfile.TemporaryDirectory() as folder:
        file = Path(folder) / Path(path).name
        file.write_bytes(before)
        editor = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")
        if subprocess.run([*editor, str(file)], check=False).returncode:
            raise Failed(f"the editor failed; {path} unchanged")
        after = file.read_bytes()
    if after == before:
        click.echo(f"no changes to {path}")
        return
    _write(path, after, message, store)


@memory.command()
@click.argument("path")
@message_option
def rm(path, message):
    """Delete a file in one commit."""
    commit = _store().delete(path, message)
    click.echo(f"removed {path} {commit}")


# Profiles


@memory.command()
@click.argument("url", required=False)
def setup(url):
    """Ask for the active profile's API URL, token and CA file; save them only if they work."""
    profile = Profile.active()
    if profile.off:
        raise ProfileError("memory is off on this machine: `overmind memory use <profile>` (e.g. personal, work) first")
    click.echo(f"Profile: {profile.name}")
    url = url or click.prompt("Context repo API URL (https://<forgejo>/api/v1/repos/<owner>/<repo>)",
                              default=profile.api or None)
    known = profile.token_file.is_file()
    token = click.prompt("Token (blank keeps the current one)" if known else "Forgejo token (repo read/write)",
                         hide_input=True, default="" if known else None, show_default=False).strip()
    ca = click.prompt("CA certificate file, if the system does not trust the server (blank for none)",
                      default=profile.ca, show_default=bool(profile.ca)).strip()
    if ca and not os.access(ca, os.R_OK):
        raise ProfileError(f"cannot read {ca}")
    profile.api, profile.ca, profile.token = url.rstrip("/"), ca, token or profile.token
    try:
        repo = ForgejoRepo(profile.api, profile.token, profile.ca).describe()
    except StoreError as error:
        raise ProfileError(f"could not read {profile.api} with that token; nothing saved ({error})") from error
    profile.save(token or None)
    visibility = "private" if repo.get("private") else "PUBLIC: anyone can read it"
    click.echo(f"ok: profile '{profile.name}' -> {repo.get('full_name')} ({visibility})")


@memory.command()
@click.argument("name", metavar="[PROFILE]", required=False)
def use(name):
    """Show the active profile, or switch to another; off (the default) turns memory off."""
    if not name:
        click.echo(Profile.active().name)
        return
    Profile.use(name)
    if name == OFF:
        click.echo("memory is off on this machine; session hooks print nothing")
    elif name in Profile.names():
        click.echo(f"active profile: {name}")
    else:
        click.echo(f"active profile: {name} (not set up yet: run `overmind memory setup`)")


@memory.command()
def profiles():
    """List the profiles set up on this machine."""
    for name in Profile.names():
        click.echo(name)


def main(argv=None):
    """`overmind memory ARGV`; its exit code."""
    from ..cli import main as overmind_main

    return overmind_main(["memory", *(sys.argv[1:] if argv is None else argv)])
