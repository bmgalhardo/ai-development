"""`overmind memory`: the context store's commands. See the README's Memory section."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from . import l0
from .profiles import OFF, Profile, ProfileError
from .store import GITHUB_PREFIX, ForgejoRepo, GitHubPublicRepo, NotFound, Repo, StoreError

REPO_HELP = "another repo, read only: owner/name on the store's host, or github:owner/name (public)"
MESSAGE_HELP = "the commit message (default: '<action> PATH')"


class Commands:
    """Each method is a command, taking the parsed arguments; it returns the exit code, or None for 0."""

    def __init__(self, profile: Profile):
        self.profile = profile

    def _store(self) -> ForgejoRepo:
        profile = self.profile.require()
        return ForgejoRepo(profile.api, profile.token, profile.ca)

    def _repo(self, ref: str | None) -> Repo:
        if ref and ref.startswith(GITHUB_PREFIX):
            return GitHubPublicRepo(ref[len(GITHUB_PREFIX):])
        store = self._store()
        return store.other(ref) if ref else store

    def get(self, args):
        """Print a file; it saves nothing."""
        sys.stdout.buffer.write(self._repo(args.repo).read(args.path))
        sys.stdout.flush()

    def ls(self, args):
        """List a folder; a folder ends in /."""
        for entry in self._repo(args.repo).list(args.folder):
            print(entry)

    def repos(self, args):
        """List the repos in L0.md's table, as references for -r."""
        text, _ = l0.fetch(self.profile.require())
        for repo in l0.table(text):
            print(f"{repo.ref:32s} {repo.description}")

    def put(self, args):
        """Write stdin to a file, creating or replacing it in one commit."""
        self._write(args.path, sys.stdin.buffer.read(), args.message)

    def edit(self, args):
        """Open a file in $VISUAL or $EDITOR and upload it if it changed; a new path creates the file."""
        store = self._store()
        try:
            before = store.read(args.path)
        except NotFound:
            before = b""
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / Path(args.path).name
            file.write_bytes(before)
            editor = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")
            if subprocess.run([*editor, str(file)], check=False).returncode:
                print(f"overmind memory: the editor failed; {args.path} unchanged", file=sys.stderr)
                return 1
            after = file.read_bytes()
        if after == before:
            print(f"no changes to {args.path}")
            return
        self._write(args.path, after, args.message, store)

    def rm(self, args):
        """Delete a file in one commit."""
        commit = self._store().delete(args.path, args.message)
        print(f"removed {args.path} {commit}")

    def l0(self, args):
        """Print L0.md for a session start: the cache when the store is away, nothing when memory is off."""
        text = l0.for_session(self.profile)
        output = l0.hook_output(text) if args.json else text
        if output:
            print(output)

    def setup(self, args):
        """Ask for the active profile's API URL, token and CA file, test them, and save them only if they work."""
        profile = self.profile
        if profile.off:
            raise ProfileError("memory is off on this machine: `overmind memory use <profile>` (e.g. personal, work) first")
        print(f"Profile: {profile.name}")
        url = args.url or _ask("Context repo API URL (https://<forgejo>/api/v1/repos/<owner>/<repo>)", profile.api)
        if not url:
            raise ProfileError("no URL given")
        known = profile.token_file.is_file()
        token = getpass.getpass("Token (blank keeps the current one): " if known
                                else "Forgejo token (repo read/write): ").strip()
        if not token and not known:
            raise ProfileError("no token given")
        ca = _ask("CA certificate file, if the system does not trust the server (blank for none)", profile.ca)
        if ca and not os.access(ca, os.R_OK):
            raise ProfileError(f"cannot read {ca}")
        profile.api, profile.ca, profile.token = url.rstrip("/"), ca, token or profile.token
        try:
            repo = ForgejoRepo(profile.api, profile.token, profile.ca).describe()
        except StoreError as error:
            raise ProfileError(f"could not read {profile.api} with that token; nothing saved ({error})") from error
        profile.save(token or None)
        visibility = "private" if repo.get("private") else "PUBLIC: anyone can read it"
        print(f"ok: profile '{profile.name}' -> {repo.get('full_name')} ({visibility})")

    def use(self, args):
        """Show the active profile, or switch to another; off (the default) turns memory off."""
        if not args.profile:
            print(self.profile.name)
            return
        Profile.use(args.profile)
        if args.profile == OFF:
            print("memory is off on this machine; session hooks print nothing")
        elif args.profile in Profile.names():
            print(f"active profile: {args.profile}")
        else:
            print(f"active profile: {args.profile} (not set up yet: run `overmind memory setup`)")

    def profiles(self, args):
        """List the profiles set up on this machine."""
        for name in Profile.names():
            print(name)

    def _write(self, path: str, content: bytes, message: str | None, store: ForgejoRepo | None = None):
        store = store or self._store()
        action, commit = store.write(path, content, message)
        print(f"{action} {path} {commit}")


def _ask(question: str, current: str) -> str:
    answer = input(f"{question}{f' [{current}]' if current else ''}: ").strip()
    return answer or current


def build_parser():
    parser = argparse.ArgumentParser(prog="overmind memory", description=__doc__,
                                     epilog="Set OVERMIND_MEMORY_PROFILE to pick a profile for one shell or one command.")
    commands = parser.add_subparsers(dest="command", metavar="command")
    commands.required = True

    def command(name):
        return commands.add_parser(name, help=getattr(Commands, name).__doc__)

    get = command("get")
    get.add_argument("-r", "--repo", help=REPO_HELP)
    get.add_argument("path")
    ls = command("ls")
    ls.add_argument("-r", "--repo", help=REPO_HELP)
    ls.add_argument("folder", nargs="?", default="")
    command("repos")
    for name in ("put", "edit", "rm"):
        sub = command(name)
        sub.add_argument("path")
        sub.add_argument("-m", "--message", help=MESSAGE_HELP)
    command("l0").add_argument("--json", action="store_true", help="wrap it as SessionStart additionalContext")
    command("setup").add_argument("url", nargs="?", help="the context repo's API URL")
    command("use").add_argument("profile", nargs="?", help="a profile name, or off")
    command("profiles")
    return parser


def main(argv=None):
    """Run a command; its exit code."""
    args = build_parser().parse_args(argv)
    try:
        code = getattr(Commands(Profile.active()), args.command)(args)
    except (ProfileError, StoreError, OSError) as error:
        print(f"overmind memory: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return code or 0


if __name__ == "__main__":
    sys.exit(main())
