"""The commands, as a shell runs them."""

from contextlib import redirect_stdout
import io
import os
from unittest.mock import patch

from overmind.memory.profiles import Profile

from fake_forgejo import API, TOKEN
from memory_helpers import StoreTestCase
from test_memory_l0 import TABLE


class CommandTests(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.set_up_profile()
        self.files = self.forge.repos["owner/context"]
        self.files.update({"L0.md": TABLE.encode(), "homelab/todos.md": b"todo"})

    def test_get_ls_and_repos(self):
        self.assertEqual(self.run_command("get", "homelab/todos.md"), (0, "todo", ""))
        self.assertEqual(self.run_command("ls")[1], "L0.md\nhomelab/\n")
        self.assertEqual(self.run_command("repos")[1].split(), ["github:someone/homelab", "The", "infrastructure.",
                                                                "owner/game", "A", "game."])

    def test_get_from_another_repo(self):
        self.forge.repos["owner/game"] = {"AGENTS.md": b"game notes"}
        self.assertEqual(self.run_command("get", "-r", "owner/game", "AGENTS.md")[1], "game notes")

    def test_put_creates_then_updates_and_rm_removes(self):
        self.assertEqual(self.run_command("put", "new.md", stdin=b"one"), (0, "created new.md 0000001\n", ""))
        self.assertEqual(self.run_command("put", "new.md", "-m", "why", stdin=b"two")[1], "updated new.md 0000002\n")
        self.assertEqual(self.run_command("rm", "new.md")[1], "removed new.md 0000003\n")
        self.assertNotIn("new.md", self.files)

    def test_off_refuses_store_commands_and_the_hook_prints_nothing(self):
        os.environ["OVERMIND_MEMORY_PROFILE"] = "off"
        self.assertEqual(self.run_command("ls"),
                         (1, "", "overmind memory: memory is off on this machine (`overmind memory use <profile>` to turn it on)\n"))
        self.assertEqual(self.run_command("l0", "--json"), (0, "", ""))

    def test_edit_uploads_only_a_change(self):
        with patch.dict(os.environ, {"EDITOR": "true"}):
            self.assertEqual(self.run_command("edit", "L0.md")[1], "no changes to L0.md\n")
        editor = self.home / "editor"
        editor.write_text('#!/bin/sh\necho added >> "$1"\n')
        editor.chmod(0o755)
        with patch.dict(os.environ, {"EDITOR": str(editor)}):
            self.assertEqual(self.run_command("edit", "fresh.md")[1], "created fresh.md 0000001\n")
        self.assertEqual(self.files["fresh.md"], b"added\n")

    def test_use_and_profiles(self):
        self.assertEqual(self.run_command("use")[1], "personal\n")
        self.assertEqual(self.run_command("use", "work")[1], "active profile: work (not set up yet: run `overmind memory setup`)\n")
        self.assertEqual(self.run_command("use", "off")[1], "memory is off on this machine; session hooks print nothing\n")
        self.assertEqual(self.run_command("profiles")[1], "personal\n")


class SetupTests(StoreTestCase):
    def setUp(self):
        super().setUp()
        Profile.use("work")

    def setup_with(self, token, url=API):
        with patch("click.termui.visible_prompt_func", return_value=""), \
                patch("click.termui.hidden_prompt_func", return_value=token):
            return self.run_command("setup", url)

    def test_a_working_token_is_saved(self):
        code, out, _ = self.setup_with(TOKEN)
        self.assertEqual(code, 0)
        self.assertIn("ok: profile 'work' -> owner/context (private)", out)
        self.assertEqual(Profile.load("work").token, TOKEN)

    def test_a_failing_token_saves_nothing(self):
        code, _, err = self.setup_with("wrong")
        self.assertEqual(code, 1)
        self.assertIn("nothing saved", err)
        self.assertFalse((self.home / "config" / "work" / "env").exists())

    def test_setup_needs_a_profile_on(self):
        Profile.use("off")
        self.assertIn("overmind memory use <profile>", self.run_command("setup", API)[2])


class OvermindDispatchTests(StoreTestCase):
    def test_overmind_memory_runs_the_memory_commands_without_overmind_settings(self):
        from overmind import cli as overmind_cli
        self.set_up_profile()
        output = io.StringIO()
        with redirect_stdout(output), patch.dict(os.environ, {"OVERMIND_PREFERENCE": "not-a-provider"}):
            self.assertEqual(overmind_cli.main(["memory", "use"]), 0)
        self.assertEqual(output.getvalue(), "personal\n")
