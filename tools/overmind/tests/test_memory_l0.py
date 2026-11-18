"""The L0 for a session start, its cache, the hook's JSON and the repo table."""

import json
import unittest

from overmind.memory import l0
from overmind.memory.profiles import Profile

from memory_helpers import StoreTestCase

TABLE = """\
| Repo | What it is | Remote |
|---|---|---|
| `homelab` | The infrastructure. | GitHub `someone/homelab` |
| `game` | A game. | Forgejo `owner/game` |
| `notes` | No remote yet. | none |
"""


class SessionTests(StoreTestCase):
    def test_off_or_not_set_up_adds_nothing(self):
        self.assertEqual(l0.for_session(Profile.active()), "")
        self.assertEqual(l0.hook_output(""), "")

    def test_the_l0_is_fetched_and_cached(self):
        self.set_up_profile()
        self.forge.repos["owner/context"]["L0.md"] = b"# map"
        profile = Profile.active()
        self.assertEqual(l0.for_session(profile), "# map")
        self.assertEqual((profile.cache / "L0.md").read_text(), "# map")

    def test_the_cache_stands_in_when_the_store_is_down(self):
        self.set_up_profile()
        self.forge.repos["owner/context"]["L0.md"] = b"# map"
        profile = Profile.active()
        l0.for_session(profile)
        self.forge.down = True
        text = l0.for_session(profile)
        self.assertTrue(text.startswith("(context store 'personal' unreachable: cached L0 from "))
        self.assertTrue(text.endswith("\n# map"))

    def test_down_with_no_cache_says_so_and_never_raises(self):
        self.set_up_profile()
        self.forge.down = True
        self.assertEqual(l0.for_session(Profile.active()),
                         "(context store 'personal' unreachable and no cached L0)")

    def test_hook_output_is_session_start_additional_context(self):
        self.assertEqual(json.loads(l0.hook_output("# map")),
                         {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "# map"}})


class TableTests(unittest.TestCase):
    def test_rows_with_a_host_and_repo_become_references(self):
        self.assertEqual([(r.ref, r.description) for r in l0.table(TABLE)],
                         [("github:someone/homelab", "The infrastructure."), ("owner/game", "A game.")])
