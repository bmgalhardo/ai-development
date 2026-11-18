"""The Forgejo and public GitHub repos, against the fake host."""

import unittest
from unittest.mock import patch

from overmind.memory.store import ForgejoRepo, GitHubPublicRepo, Http, NotFound, StoreError

from fake_forgejo import API, TOKEN
from memory_helpers import StoreTestCase


class ForgejoRepoTests(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.forge.repos["owner/context"].update({"L0.md": b"map", "homelab/todos.md": b"todo"})
        self.repo = ForgejoRepo(API, TOKEN)

    def test_read_and_list(self):
        self.assertEqual(self.repo.read("L0.md"), b"map")
        self.assertEqual([str(e) for e in self.repo.list()], ["L0.md", "homelab/"])
        self.assertEqual([str(e) for e in self.repo.list("homelab")], ["homelab/todos.md"])

    def test_a_missing_file_is_not_found(self):
        with self.assertRaises(NotFound):
            self.repo.read("nope.md")
        self.assertIsNone(self.repo.sha("nope.md"))

    def test_write_creates_then_replaces_with_the_current_sha(self):
        self.assertEqual(self.repo.write("new.md", b"one")[0], "created")
        self.assertEqual(self.repo.write("new.md", b"two")[0], "updated")
        self.assertEqual(self.forge.repos["owner/context"]["new.md"], b"two")

    def test_a_write_racing_another_is_refused(self):
        with patch.object(ForgejoRepo, "sha", return_value="stale"), \
                self.assertRaisesRegex(StoreError, "HTTP 409 sha does not match"):
            self.repo.write("L0.md", b"mine")
        self.assertEqual(self.forge.repos["owner/context"]["L0.md"], b"map")

    def test_delete(self):
        self.repo.delete("L0.md")
        self.assertNotIn("L0.md", self.forge.repos["owner/context"])
        with self.assertRaises(NotFound):
            self.repo.delete("L0.md")

    def test_other_reads_another_repo_on_the_host_with_the_same_token(self):
        self.forge.repos["owner/game"] = {"AGENTS.md": b"game notes"}
        self.assertEqual(self.repo.other("owner/game").read("AGENTS.md"), b"game notes")

    def test_a_wrong_token_is_an_error_naming_the_status(self):
        with self.assertRaisesRegex(StoreError, "HTTP 401 token is required"):
            ForgejoRepo(API, "wrong").read("L0.md")


class GitHubPublicRepoTests(unittest.TestCase):
    def test_reads_the_default_branch_without_a_token(self):
        sent = []

        def send(http, method, url, headers, body):
            sent.append((url, headers))
            return 200, b"readme"

        with patch.object(Http, "send", send):
            self.assertEqual(GitHubPublicRepo("someone/repo").read("README.md"), b"readme")
        self.assertEqual(sent, [("https://raw.githubusercontent.com/someone/repo/HEAD/README.md", {})])

    def test_is_read_only(self):
        with self.assertRaisesRegex(StoreError, "read only"):
            GitHubPublicRepo("someone/repo").write("x", b"")
