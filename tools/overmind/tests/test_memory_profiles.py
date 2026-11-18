"""Which profile is active, what it reads from its files and the environment, and how it saves."""

import os
import stat

from overmind.memory.profiles import OFF, Profile, ProfileError

from fake_forgejo import API, TOKEN
from memory_helpers import StoreTestCase


class ProfileTests(StoreTestCase):
    def test_a_new_machine_is_off(self):
        profile = Profile.active()
        self.assertEqual(profile.name, OFF)
        self.assertFalse(profile.set_up)
        with self.assertRaisesRegex(ProfileError, "memory is off"):
            profile.require()

    def test_the_active_file_picks_the_profile_and_its_files_set_it_up(self):
        self.set_up_profile()
        profile = Profile.active()
        self.assertEqual((profile.name, profile.api, profile.token), ("personal", API, TOKEN))
        self.assertTrue(profile.set_up)

    def test_context_profile_wins_over_the_active_file(self):
        self.set_up_profile()
        os.environ["OVERMIND_MEMORY_PROFILE"] = "work"
        profile = Profile.active()
        self.assertEqual(profile.name, "work")
        with self.assertRaisesRegex(ProfileError, "'work' is not set up"):
            profile.require()

    def test_the_environment_wins_over_the_files(self):
        self.set_up_profile()
        os.environ.update(OVERMIND_MEMORY_API="https://other.test/api/v1/repos/a/b/", OVERMIND_MEMORY_TOKEN="env-token")
        profile = Profile.active()
        self.assertEqual((profile.api, profile.token), ("https://other.test/api/v1/repos/a/b", "env-token"))

    def test_save_writes_private_files_and_keeps_the_token_when_none_is_given(self):
        profile = Profile("work", api=API, ca="/ca.crt")
        profile.save("first")
        profile.save(None)
        env, token = profile.folder / "env", profile.folder / "token"
        self.assertEqual(env.read_text(), f"OVERMIND_MEMORY_API={API}\nOVERMIND_MEMORY_CA=/ca.crt\n")
        self.assertEqual(token.read_text(), "first\n")
        for path in (env, token):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_names_lists_only_profiles_with_an_env_file(self):
        self.set_up_profile("personal")
        (self.home / "config" / "empty").mkdir()
        self.assertEqual(Profile.names(), ["personal"])
