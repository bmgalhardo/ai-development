"""The `docker run` command of each provider and role, its logins and its removal."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from overmind.runner import container
from overmind.runner.container import Container
from overmind.core.providers import registry
from overmind.core.settings import Settings

HOME = Path("/home/worker")


def volumes(command):
    """The `-v` mounts of a docker command, as {target: (host, mode)}."""
    found = {}
    for index, part in enumerate(command):
        if part == "-v":
            host, target, mode = command[index + 1].split(":")
            found[target] = (host, mode)
    return found


def labels(command):
    return dict(command[index + 1].split("=", 1) for index, part in enumerate(command) if part == "--label")


class ContainerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "AGENTS.md").write_text("notes\n")
        (self.root / "CLAUDE.md").symlink_to("AGENTS.md")
        (self.root / ".agents/context").mkdir(parents=True)
        (self.root / ".claude").symlink_to(".agents")
        self.project = self.root / "project"
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        self.logins = self.root / ".logins"
        self.logins.mkdir()
        (self.logins / ".claude.login").write_text("setup-token\n")
        (self.logins / ".codex.login").write_text("{}\n")
        clean = {key: value for key, value in os.environ.items() if not key.upper().startswith("OVERMIND_")}
        patcher = patch.dict(os.environ, clean | {"GIT_AUTHOR_NAME": "Worker Owner",
                                                  "GIT_AUTHOR_EMAIL": "owner@example.com"}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.removed = []
        docker = patch.object(Container, "docker", side_effect=lambda *args: self.removed.append(args) or 1)
        docker.start()
        self.addCleanup(docker.stop)

    def container(self, provider, role, **values):
        settings = Settings(_env_file=None, root=self.root, container=True, **values)
        return Container(settings, self.project, registry.provider(provider, settings), role)

    def test_each_provider_and_role_gets_its_own_login_and_mounts(self):
        scratch = str(self.root / ".scratch/project")
        project = str(self.project)
        expected = {
            ("claude", "implement"): ("rw", HOME / ".claude/projects"),
            ("claude", "review"): ("ro", HOME / ".claude/projects"),
            ("codex", "fix"): ("rw", HOME / ".codex/sessions"),
            ("codex", "review"): ("ro", HOME / ".codex/sessions"),
        }
        for (provider, role), (access, sessions) in expected.items():
            with self.subTest(provider=provider, role=role), self.container(provider, role) as worker:
                mounts = volumes(worker.command(["true"]))
                self.assertEqual(mounts[project], (project, access))
                self.assertEqual(mounts[scratch], (scratch, access))
                self.assertEqual(mounts[str(sessions)], (f"{scratch}/sessions/{provider}", "rw"))
                self.assertTrue(Path(scratch, "sessions", provider).is_dir())
                self.assertEqual(labels(worker.command(["true"])),
                                 {"overmind.project": "project", "overmind.provider": provider, "overmind.role": role,
                                  "overmind.pid": str(os.getpid())})

    def test_claude_gets_its_token_by_name_and_no_other_login(self):
        with self.container("claude", "implement") as worker:
            command = worker.command(["true"])
            self.assertEqual(worker.environment()["CLAUDE_CODE_OAUTH_TOKEN"], "setup-token")
            self.assertIn("CLAUDE_CODE_OAUTH_TOKEN", command)
            self.assertNotIn("setup-token", " ".join(command))
            self.assertNotIn(str(HOME / ".codex/auth.json"), volumes(command))

    def test_codex_gets_its_login_writable_and_no_token(self):
        with self.container("codex", "review") as worker:
            command = worker.command(["true"])
            self.assertEqual(volumes(command)[str(HOME / ".codex/auth.json")],
                             (str(self.logins / ".codex.login"), "rw"))
            self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", worker.environment())

    def test_a_codex_login_is_locked_until_the_session_holds_it(self):
        login = self.logins / ".codex.login"
        with self.container("codex", "implement") as worker:
            self.assertEqual(len(worker.keep()), 1)
            self.assertNotEqual(subprocess.run(["flock", "-n", str(login), "true"]).returncode, 0)
            worker.started()
            self.assertEqual(subprocess.run(["flock", "-n", str(login), "true"]).returncode, 0)

    def test_a_second_codex_session_takes_the_next_free_login_else_waits_for_the_first(self):
        first = self.logins / ".codex.login"
        with self.container("codex", "review") as one, self.container("codex", "review") as two:
            self.assertEqual(two.command(["true"])[:2], ["flock", str(first)])
            self.assertEqual(two.keep(), [])
            self.assertEqual(volumes(two.command(["true"]))[str(HOME / ".codex/auth.json")][0], str(first))
            (self.logins / ".codex-2.login").write_text("{}\n")
            with self.container("codex", "review") as three:
                self.assertEqual(three.command(["true"])[0], "docker")
                self.assertEqual(volumes(three.command(["true"]))[str(HOME / ".codex/auth.json")][0],
                                 str(self.logins / ".codex-2.login"))
        with self.container("codex", "review") as again:
            self.assertEqual(again.command(["true"])[0], "docker")

    def test_a_missing_login_stops_the_session_before_docker(self):
        (self.logins / ".claude.login").unlink()
        (self.logins / ".codex.login").unlink()
        for provider in ("claude", "codex"):
            with self.subTest(provider=provider), self.assertRaises(OSError):
                with self.container(provider, "implement"):
                    pass

    def test_leaving_removes_the_container_by_name(self):
        with self.container("claude", "implement") as worker:
            name = worker.command(["true"])[worker.command(["true"]).index("--name") + 1]
        self.assertIn(("rm", "-f", name), self.removed)
        self.assertTrue(name.startswith("overmind-project-claude-implement-"))

    def test_only_the_agent_notes_and_their_links_are_mounted_read_only(self):
        with self.container("claude", "implement") as worker:
            mounts = volumes(worker.command(["true"]))
        for link, name in (("AGENTS.md", "AGENTS.md"), ("CLAUDE.md", "AGENTS.md"), (".agents", ".agents"),
                           (".claude", ".agents")):
            self.assertEqual(mounts[str(self.root / link)], (str(self.root / name), "ro"))
        self.assertFalse(any("machine" in target for target in mounts))

    def test_the_machine_notes_are_replaced_when_the_host_has_them(self):
        (self.root / ".agents/context/machine.local.md").write_text("host notes\n")
        with self.container("claude", "implement") as worker:
            mounts = volumes(worker.command(["true"]))
        for link in (".agents", ".claude"):
            self.assertEqual(mounts[str(self.root / link / "context/machine.local.md")],
                             (str(container.FOLDER / "machine.md"), "ro"))

    def test_limits_user_identity_and_working_folder(self):
        with self.container("claude", "implement", container_memory="2g", container_pids=64) as worker:
            command = worker.command(["claude", "-p"])
            environment = worker.environment()
        self.assertEqual(command[command.index("--memory") + 1], "2g")
        self.assertEqual(command[command.index("--pids-limit") + 1], "64")
        self.assertEqual(command[command.index("--user") + 1], f"{os.getuid()}:{os.getgid()}")
        self.assertIn("ALL", command)
        self.assertEqual(command[-5:], ["-w", str(self.root), "overmind-worker", "claude", "-p"])
        self.assertEqual({key: environment[key] for key in environment if key.startswith("GIT_")},
                         {"GIT_AUTHOR_NAME": "Worker Owner", "GIT_AUTHOR_EMAIL": "owner@example.com",
                          "GIT_COMMITTER_NAME": "Worker Owner", "GIT_COMMITTER_EMAIL": "owner@example.com"})

    def test_the_image_is_the_setting_else_the_projects_else_the_workers(self):
        with self.container("claude", "implement", image="custom") as worker:
            self.assertEqual(worker.image(), "custom")
        with self.container("claude", "implement") as worker:
            self.assertEqual(worker.image(), "overmind-worker")
            with patch.object(Container, "docker", return_value=0):
                self.assertEqual(worker.image(), "overmind-project")

    def test_container_code_names_no_provider(self):
        source = Path(container.__file__).read_text().lower()
        for name in registry.names():
            self.assertNotIn(name, source)


if __name__ == "__main__":
    unittest.main()
