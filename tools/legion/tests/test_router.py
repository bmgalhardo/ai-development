"""Which provider takes a step, from a table of situations; no processes or files."""

import unittest

from legion.runner.router import Router, Situation, Stop, Use, Wait

NOW = 1000.0
COOLING = {"cooldowns": {"claude": NOW + 600}}  # Claude out of quota for ten minutes


class RouterTests(unittest.TestCase):
    def choose(self, preference, role, **situation):
        return Router(preference).choose(role, Situation(**situation), NOW)

    def test_the_table(self):
        both = ["claude", "codex"]
        table = [
            # implement and fix: the first ready provider in the preference
            ("normal implement", both, "implement", {}, Use(provider="claude")),
            ("normal fix", both, "fix", {"implementer": "claude"}, Use(provider="claude")),
            ("claude cooling implements with codex", both, "implement", COOLING, Use(provider="codex")),
            ("an expired cooldown is ready", both, "implement", {"cooldowns": {"claude": NOW}},
             Use(provider="claude")),
            ("a retry prefers a provider that hasn't failed", both, "implement", {"failed": {"claude"}},
             Use(provider="codex")),
            ("only failed providers left: retry anyway", both, "implement",
             {"failed": {"claude", "codex"}}, Use(provider="claude")),
            ("a signed-out provider sits out", both, "implement", {"signed_out": {"claude"}},
             Use(provider="codex")),
            # review: another provider than the implementer, else the implementer; never waiting
            ("normal review", both, "review", {"implementer": "claude"}, Use(provider="codex")),
            ("codex implemented, claude reviews", both, "review", {"implementer": "codex"},
             Use(provider="claude")),
            ("claude cooling: codex reviews its own work", both, "review",
             {"implementer": "codex"} | COOLING, Use(provider="codex")),
            ("reviewer cooling: the implementer reviews", both, "review",
             {"implementer": "claude", "cooldowns": {"codex": NOW + 600}}, Use(provider="claude")),
            ("no implementer known: the first ready", both, "review", {}, Use(provider="claude")),
            ("review prefers independence over a past failure", both, "review",
             {"implementer": "claude", "failed": {"codex"}}, Use(provider="codex")),
            # one provider does everything
            ("one provider implements", ["claude"], "implement", {}, Use(provider="claude")),
            ("one provider reviews itself", ["claude"], "review", {"implementer": "claude"},
             Use(provider="claude")),
            ("one provider fixes", ["claude"], "fix", {"implementer": "claude"}, Use(provider="claude")),
            ("the preference order wins", ["codex", "claude"], "implement", {}, Use(provider="codex")),
            # waiting and stopping
            ("everyone cooling: wait for the earliest reset", both, "implement",
             {"cooldowns": {"claude": NOW + 600, "codex": NOW + 300}}, Wait(until=NOW + 300)),
            ("a review waits only when everyone is cooling", both, "review",
             {"implementer": "claude", "cooldowns": {"claude": NOW + 600, "codex": NOW + 900}},
             Wait(until=NOW + 600)),
            ("a signed-out provider's cooldown doesn't count", both, "implement",
             {"signed_out": {"codex"}, "cooldowns": {"claude": NOW + 600, "codex": NOW + 60}},
             Wait(until=NOW + 600)),
            ("everyone signed out: stop", both, "implement", {"signed_out": {"claude", "codex"}},
             Stop(signed_out=["claude", "codex"])),
        ]
        for name, preference, role, situation, expected in table:
            with self.subTest(name):
                self.assertEqual(self.choose(preference, role, **situation), expected)


if __name__ == "__main__":
    unittest.main()
