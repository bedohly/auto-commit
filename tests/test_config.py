import os
import shutil
import tempfile
import unittest

from autocommit import config, paths
from autocommit.config import RepoTarget, Settings


class TempHome(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="autocommit-test-")
        self._previous = os.environ.get(paths.HOME_ENV)
        os.environ[paths.HOME_ENV] = self.home

    def tearDown(self):
        if self._previous is None:
            os.environ.pop(paths.HOME_ENV, None)
        else:
            os.environ[paths.HOME_ENV] = self._previous
        shutil.rmtree(self.home, ignore_errors=True)


class ConfigTests(TempHome):
    def test_missing_config_returns_defaults(self):
        loaded = config.load()
        self.assertEqual(loaded.commit_file, "activity.md")
        self.assertFalse(loaded.repo.is_set())

    def test_save_and_load_roundtrip(self):
        settings = Settings(
            account="octocat",
            author_name="The Octocat",
            author_email="1+octocat@users.noreply.github.com",
            repo=RepoTarget(owner="octocat", name="activity-log", branch="main", private=True),
            min_commits=2,
            max_commits=7,
            message_style="conventional",
        )
        config.save(settings)
        loaded = config.load()
        self.assertEqual(loaded.repo.full_name, "octocat/activity-log")
        self.assertEqual(loaded.repo.branch, "main")
        self.assertTrue(loaded.repo.private)
        self.assertEqual(loaded.min_commits, 2)
        self.assertEqual(loaded.max_commits, 7)
        self.assertEqual(loaded.message_style, "conventional")
        self.assertEqual(loaded.author_email, "1+octocat@users.noreply.github.com")

    def test_unknown_keys_are_ignored(self):
        settings = Settings.from_dict({"account": "x", "totally_unknown": 1,
                                       "repo": {"owner": "a", "name": "b", "nope": 2}})
        self.assertEqual(settings.account, "x")
        self.assertEqual(settings.repo.full_name, "a/b")

    def test_corrupt_config_falls_back_to_defaults(self):
        paths.ensure_dir(paths.config_file().parent)
        paths.config_file().write_text("{not json", encoding="utf-8")
        self.assertEqual(config.load().commit_file, "activity.md")

    def test_clone_url(self):
        target = RepoTarget(owner="octocat", name="hello")
        self.assertEqual(target.clone_url, "https://github.com/octocat/hello.git")

    def test_validation_rejects_bad_values(self):
        cases = [
            Settings(min_commits=0),
            Settings(min_commits=5, max_commits=2),
            Settings(weekday_active_chance=1.5),
            Settings(active_hour_start=20, active_hour_end=9),
            Settings(message_style="loud"),
            Settings(commit_file="../escape.md"),
            Settings(commit_file="/etc/passwd"),
            Settings(jitter_minutes=-1),
        ]
        for settings in cases:
            with self.assertRaises(ValueError):
                settings.validate()

    def test_paths_are_separated_by_home_override(self):
        self.assertTrue(str(paths.config_file()).startswith(self.home))
        self.assertTrue(str(paths.repos_dir()).startswith(self.home))
        workdir = paths.repo_workdir("octocat", "hello")
        self.assertTrue(workdir.name.endswith("octocat__hello"))


class TokenStorageTests(TempHome):
    def test_store_and_forget(self):
        from autocommit import auth

        for name in auth.ENV_VARS:
            os.environ.pop(name, None)
        self.assertEqual(auth.stored_token(), "")
        auth.store_token("ghp_example_token")
        self.assertEqual(auth.stored_token(), "ghp_example_token")
        info = auth.resolve()
        self.assertIsNotNone(info)
        self.assertEqual(info.value, "ghp_example_token")
        self.assertIn("*", info.masked())
        self.assertNotIn("example", info.masked())
        self.assertTrue(auth.forget_token())
        self.assertEqual(auth.stored_token(), "")

    def test_environment_wins_over_stored_token(self):
        from autocommit import auth

        auth.store_token("stored-token")
        os.environ["AUTOCOMMIT_TOKEN"] = "env-token"
        try:
            self.assertEqual(auth.resolve().value, "env-token")
        finally:
            os.environ.pop("AUTOCOMMIT_TOKEN", None)

    def test_scope_check(self):
        from autocommit import auth

        self.assertFalse(auth.missing_scope([]))              # fine-grained token
        self.assertFalse(auth.missing_scope(["repo", "gist"]))
        self.assertFalse(auth.missing_scope(["public_repo"]))
        self.assertTrue(auth.missing_scope(["gist", "read:org"]))


if __name__ == "__main__":
    unittest.main()
