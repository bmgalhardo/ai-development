"""The project repo as the runner sees it: git that can't run the project's commands, and recovery snapshots."""

import re
import subprocess
import tarfile

# A session can edit the project's .git, and the runner's git runs on the host.
# These settings would make that git run a command, so the runner refuses a repo that has them.
UNSAFE_CONFIG = re.compile(r"^(core\.(fsmonitor|hookspath|pager|editor|sshcommand|askpass|gitproxy)"
                           r"|filter\.|diff\..*\.(command|textconv)|merge\..*\.driver|include|alias\.)",
                           re.IGNORECASE)
SAFE_GIT = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")


class UnsafeRepo(Exception):
    """The project's .git can run commands; inspect it before running git there."""


class Repo:
    def __init__(self, path):
        self.path = path

    def unsafe(self):
        """What in the project's .git could make git run a command: config keys and installed hooks."""
        local = subprocess.run(["git", "-C", str(self.path), "config", "--local", "--name-only", "--list"],
                               capture_output=True, text=True).stdout.split()
        hooks = self.path / ".git" / "hooks"
        installed = [hook.name for hook in hooks.iterdir() if not hook.name.endswith(".sample")] \
            if hooks.is_dir() else []
        return [key for key in local if UNSAFE_CONFIG.match(key)] + [f"hook {name}" for name in installed]

    def git(self, *args):
        """Run git in the project, refusing a .git that can run commands; external diff drivers are off."""
        found = self.unsafe()
        if found:
            raise UnsafeRepo(f"{self.path}/.git can run commands ({', '.join(found)}): "
                             "inspect it before running git there.")
        if args[0] == "diff":
            args = ("diff", "--no-ext-diff", "--no-textconv", *args[1:])
        return subprocess.check_output(["git", *SAFE_GIT, "-C", str(self.path), *args])

    def head(self):
        return self.git("rev-parse", "--short", "HEAD").decode().strip()

    def dirty(self):
        return bool(self.git("status", "--porcelain").strip())

    def snapshot(self, issue, folder):
        """Save tracked edits, the index, untracked files, HEAD and the issue, including failing work."""
        folder.mkdir()
        (folder / "HEAD").write_bytes(self.git("rev-parse", "HEAD"))
        (folder / "status.txt").write_bytes(self.git("status", "--porcelain"))
        (folder / "changes.patch").write_bytes(self.git("diff", "--binary", "HEAD"))
        (folder / "index.patch").write_bytes(self.git("diff", "--binary", "--cached"))
        (folder / "issue.md").write_bytes(issue.read_bytes())
        paths = self.git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
        with tarfile.open(folder / "untracked.tar", "w") as archive:
            for path in filter(None, paths):
                name = path.decode("utf-8", errors="surrogateescape")
                archive.add(self.path / name, arcname=name, recursive=False)
