"""A temporary config and cache home, a fake Forgejo behind `Http.send`, and the commands as a shell runs them."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from overmind import cli
from overmind.memory.store import Http

from fake_forgejo import API, TOKEN, FakeForgejo


class StoreTestCase(unittest.TestCase):
    """Each test gets an empty home and the profile `personal` set up against the fake host."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        environment = {"OVERMIND_MEMORY_HOME": str(self.home / "config"), "OVERMIND_MEMORY_CACHE": str(self.home / "cache")}
        cleared = {key: value for key, value in os.environ.items() if not key.startswith("OVERMIND_MEMORY_")}
        patcher = patch.dict(os.environ, cleared | environment, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.forge = FakeForgejo()
        forge = self.forge
        sender = patch.object(Http, "send", lambda http, *args: forge.send(http, *args))
        sender.start()
        self.addCleanup(sender.stop)

    def set_up_profile(self, name="personal", active=True):
        folder = self.home / "config" / name
        folder.mkdir(parents=True)
        (folder / "env").write_text(f"OVERMIND_MEMORY_API={API}\n")
        (folder / "token").write_text(TOKEN + "\n")
        if active:
            (self.home / "config" / "active").write_text(name + "\n")

    def run_command(self, *args, stdin=b""):
        """(exit code, stdout, stderr) of `overmind memory ARGS`."""
        out, err = io.StringIO(), io.StringIO()
        fake_stdin = io.TextIOWrapper(io.BytesIO(stdin))
        stdout = io.TextIOWrapper(io.BytesIO(), write_through=True)
        with redirect_stdout(stdout), redirect_stderr(err), patch.object(sys, "stdin", fake_stdin):
            code = cli.main(["memory", *args])
            stdout.flush()
        out.write(stdout.buffer.getvalue().decode())
        return code, out.getvalue(), err.getvalue()
