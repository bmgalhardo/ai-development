"""Worker containers: a session's `docker run` command, its login, and its removal.

The image recipes, the build script and the container's machine notes sit beside this file.
No provider is named here: each provider gives its own login and session folder.
"""

import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

FOLDER = Path(__file__).parent
WORKER_IMAGE = "legion-worker"
AGENT_NOTES = ("AGENTS.md", ".agents")  # all a session reads from the workflow repo, with their links
# The host's machine notes, in `.agents`; inside a container, `machine.md` here replaces them.
MACHINE_NOTES = Path("context/machine.local.md")


class Container:
    """One session's container: a provider in a role on a project, with the same absolute paths as the host.

    Use it as a context manager: entering takes the provider's login; leaving releases it and removes
    the container, which a stopped docker client leaves running.
    """

    def __init__(self, settings, project, provider, role, tty=False):
        self.settings = settings
        self.root = settings.root
        self.project = project
        self.provider = provider
        self.role = role
        self.tty = tty
        self.name = f"legion-{project.name}-{provider.name}-{role}-{uuid4().hex[:8]}"
        self.login = None

    def __enter__(self):
        self.login = self.provider.container_login()
        return self

    def __exit__(self, *_):
        self.login.release()
        self.docker("rm", "-f", self.name)

    def command(self, command):
        """`docker run` for the session's command; waits first for a login another session holds."""
        wait = ["flock", str(self.login.wait_for)] if self.login.wait_for else []
        return [*wait, "docker", "run", "--rm", *(["-it"] if self.tty else []), "--init", "--name", self.name,
                *self.labels(), "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--memory", self.settings.container_memory,
                "--pids-limit", str(self.settings.container_pids), *self.mounts(),
                *[part for name in self.environment() for part in ("-e", name)],
                "-w", str(self.root), self.image(), *command]

    def environment(self):
        """Variables the docker client passes in by name: the git identity and the provider's login."""
        return self.git_identity() | self.login.environment

    def keep(self):
        """File descriptors the docker client holds for the container's life: a locked login."""
        return [self.login.held.fileno()] if self.login.held else []

    def started(self):
        """Once the docker client holds the login, let go of this process's copy: the lock is then the client's."""
        self.login.release()

    def labels(self):
        labels = {"project": self.project.name, "provider": self.provider.name, "role": self.role,
                  "pid": os.getpid()}
        return [part for key, value in labels.items() for part in ("--label", f"legion.{key}={value}")]

    def mounts(self):
        """The agent notes read-only; the project and its scratch, read-only for a reviewer; the login and sessions."""
        scratch = self.root / ".scratch" / self.project.name
        sessions = scratch / "sessions" / self.provider.name
        sessions.mkdir(parents=True, exist_ok=True)
        access = "ro" if self.role == "review" else "rw"
        volumes = [*self.workflow_mounts(), (scratch, scratch, access), (self.project, self.project, access),
                   *[(mount.host, mount.target, "rw" if mount.writable else "ro") for mount in self.login.mounts],
                   (sessions, self.login.sessions, "rw")]
        return [part for host, target, mode in volumes for part in ("-v", f"{host}:{target}:{mode}")]

    def workflow_mounts(self):
        """Only what a session reads from the workflow repo: the agent notes, skills and context, and their links.

        A read-only mount can't cover a missing file, so the machine notes are replaced only when the host has them.
        """
        volumes = []
        for name in AGENT_NOTES:
            volumes += [(self.root / name, path, "ro") for path in self.links(name)]
        if (self.root / ".agents" / MACHINE_NOTES).is_file():
            volumes += [(FOLDER / "machine.md", path / MACHINE_NOTES, "ro") for path in self.links(".agents")]
        return volumes

    def links(self, name):
        """The workflow root's entry `name` and its symbolic links in the root."""
        target = (self.root / name).resolve()
        return [self.root / name, *sorted(path for path in self.root.iterdir()
                                          if path.is_symlink() and path.resolve() == target)]

    def image(self):
        """WORK_IMAGE, else the project's image when built, else the worker image."""
        if self.settings.image:
            return self.settings.image
        project_image = f"legion-{self.project.name}"
        return project_image if self.docker("image", "inspect", project_image) == 0 else WORKER_IMAGE

    def git_identity(self):
        """The host's git author (its environment, else its config), as author and committer."""
        try:
            ident = subprocess.run(["git", "var", "GIT_AUTHOR_IDENT"], cwd=self.root, capture_output=True,
                                   text=True).stdout
        except OSError:
            return {}
        match = re.match(r"(.*) <(.*)> \d+ [+-]\d{4}$", ident.strip())
        if not match:
            return {}
        return {f"GIT_{who}_{part}": value for who in ("AUTHOR", "COMMITTER")
                for part, value in (("NAME", match[1]), ("EMAIL", match[2]))}

    @classmethod
    def remove_leftovers(cls, project):
        """Remove every container of the project: run while holding its runner lock, they are a killed run's."""
        try:
            found = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=legion.project={project.name}"],
                                   capture_output=True, text=True).stdout.split()
        except OSError:
            return
        if found:
            cls.docker("rm", "-f", *found)

    @staticmethod
    def docker(*args):
        """Run a docker command quietly; its exit code, or None when docker isn't installed."""
        try:
            return subprocess.run(["docker", *args], capture_output=True).returncode
        except OSError:
            return None
