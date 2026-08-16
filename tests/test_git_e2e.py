"""End-to-end tests against a local bare repository.

These exercise the real git binary and the real push path, without touching
github.com.
"""

import os
import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from autocommit import config, gitrepo, paths, planner, runner
from autocommit.config import RepoTarget, Settings
from autocommit.gitrepo import CREDENTIAL_HELPER, TOKEN_ENV, LocalRepo


def git_missing():
    return shutil.which("git") is None


def bare_log(bare: Path, branch: str = "main"):
    """Return (author_name, author_email, iso_date, subject) for every commit."""
    result = subprocess.run(
        ["git", "--git-dir", str(bare), "log", branch, "--format=%an|%ae|%aI|%s"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    lines = [line for line in result.stdout.strip().splitlines() if line]
    return [tuple(line.split("|", 3)) for line in lines]


def parse_git_date(value: str) -> datetime:
    """Parse git's %aI. Python 3.9 cannot read the 'Z' suffix git emits in UTC."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def show_file(bare: Path, branch: str, path: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir", str(bare), "show", "{0}:{1}".format(branch, path)],
        capture_output=True, text=True,
    )
    return result.stdout


@unittest.skipIf(git_missing(), "git is not installed")
class GitEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="autocommit-e2e-"))
        self.home = self.root / "home"
        self.home.mkdir()
        self._previous = os.environ.get(paths.HOME_ENV)
        os.environ[paths.HOME_ENV] = str(self.home)

        self.bare = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.bare)],
                       capture_output=True, text=True, check=True)
        self.remote_url = self.bare.as_posix()
        self.workdir = self.root / "work"

        self.settings = Settings(
            account="tester",
            author_name="Test Person",
            author_email="99+tester@users.noreply.github.com",
            repo=RepoTarget(owner="tester", name="activity-log", branch="main"),
            commit_file="activity.md",
            min_commits=2,
            max_commits=3,
            weekday_active_chance=1.0,
            weekend_active_chance=1.0,
            active_hour_start=9,
            active_hour_end=18,
        )

    def tearDown(self):
        if self._previous is None:
            os.environ.pop(paths.HOME_ENV, None)
        else:
            os.environ[paths.HOME_ENV] = self._previous
        paths.remove_tree(self.root)

    # -- building blocks --------------------------------------------------
    def test_empty_remote_is_initialized_then_pushed(self):
        plan = planner.build_plan(date(2026, 3, 2), date(2026, 3, 4),
                                  self.settings, random.Random(42))
        result = runner.execute(self.settings, plan, workdir=self.workdir,
                                remote_url=self.remote_url)

        self.assertEqual(result.repo_status, "initialized")
        self.assertEqual(result.created, len(plan))
        self.assertTrue(result.pushed)

        commits = bare_log(self.bare)
        self.assertEqual(len(commits), len(plan))
        for name, email, _, _ in commits:
            self.assertEqual(name, "Test Person")
            self.assertEqual(email, "99+tester@users.noreply.github.com")

    def test_commit_dates_match_the_plan(self):
        plan = planner.build_plan(date(2026, 3, 2), date(2026, 3, 6),
                                  self.settings, random.Random(7))
        runner.execute(self.settings, plan, workdir=self.workdir, remote_url=self.remote_url)

        pushed = list(reversed(bare_log(self.bare)))  # git log is newest first
        self.assertEqual(len(pushed), len(plan))
        for planned, (_, _, iso, subject) in zip(plan, pushed):
            recorded = parse_git_date(iso).replace(tzinfo=None)
            self.assertEqual(recorded, planned.when)
            self.assertEqual(subject, planned.message)

    def test_second_run_fetches_and_appends(self):
        first = planner.build_plan(date(2026, 3, 2), date(2026, 3, 3),
                                   self.settings, random.Random(1))
        runner.execute(self.settings, first, workdir=self.workdir, remote_url=self.remote_url)

        second_plan = planner.build_plan(date(2026, 3, 4), date(2026, 3, 5),
                                         self.settings, random.Random(2))
        second = runner.execute(self.settings, second_plan, workdir=self.workdir,
                                remote_url=self.remote_url)

        self.assertEqual(second.repo_status, "updated")
        self.assertEqual(len(bare_log(self.bare)), len(first) + len(second_plan))

        content = show_file(self.bare, "main", "activity.md")
        self.assertIn("# Activity log", content)
        entry_lines = [line for line in content.splitlines() if line.startswith("- ")]
        self.assertEqual(len(entry_lines), len(first) + len(second_plan))

    def test_a_fresh_clone_of_an_existing_remote(self):
        plan = planner.build_plan(date(2026, 3, 2), date(2026, 3, 2),
                                  self.settings, random.Random(3))
        runner.execute(self.settings, plan, workdir=self.workdir, remote_url=self.remote_url)
        paths.remove_tree(self.workdir)

        again = planner.build_plan(date(2026, 3, 3), date(2026, 3, 3),
                                   self.settings, random.Random(4))
        result = runner.execute(self.settings, again, workdir=self.workdir,
                                remote_url=self.remote_url)
        self.assertEqual(result.repo_status, "cloned")
        self.assertEqual(len(bare_log(self.bare)), len(plan) + len(again))

    def test_no_push_leaves_the_remote_untouched(self):
        plan = planner.build_plan(date(2026, 3, 2), date(2026, 3, 2),
                                  self.settings, random.Random(5))
        result = runner.execute(self.settings, plan, workdir=self.workdir,
                                remote_url=self.remote_url, push=False)
        self.assertFalse(result.pushed)
        self.assertEqual(bare_log(self.bare), [])
        self.assertEqual(result.created, len(plan))

    def test_nested_commit_file_path(self):
        self.settings.commit_file = "logs/daily/activity.md"
        plan = planner.build_plan(date(2026, 3, 2), date(2026, 3, 2),
                                  self.settings, random.Random(6))
        runner.execute(self.settings, plan, workdir=self.workdir, remote_url=self.remote_url)
        content = show_file(self.bare, "main", "logs/daily/activity.md")
        self.assertIn("# Activity log", content)

    def test_non_default_branch(self):
        self.settings.repo.branch = "activity"
        plan = planner.build_plan(date(2026, 3, 2), date(2026, 3, 2),
                                  self.settings, random.Random(8))
        runner.execute(self.settings, plan, workdir=self.workdir, remote_url=self.remote_url)
        self.assertEqual(len(bare_log(self.bare, "activity")), len(plan))

    def test_run_log_is_written(self):
        plan = planner.build_plan(date(2026, 3, 2), date(2026, 3, 2),
                                  self.settings, random.Random(9))
        result = runner.execute(self.settings, plan, workdir=self.workdir,
                                remote_url=self.remote_url)
        runner.append_run_log(result, self.settings, datetime(2026, 3, 2, 12, 0, 0))
        self.assertIn("tester/activity-log", paths.log_file().read_text(encoding="utf-8"))


@unittest.skipIf(git_missing(), "git is not installed")
class CredentialHelperTests(unittest.TestCase):
    def test_helper_feeds_the_token_to_git(self):
        env = dict(os.environ)
        env[TOKEN_ENV] = "ghp_unit_test_value"
        env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git", "-c", "credential.helper=", "-c", "credential.helper=" + CREDENTIAL_HELPER,
             "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("username=x-access-token", result.stdout)
        self.assertIn("password=ghp_unit_test_value", result.stdout)

    def test_errors_never_leak_the_token(self):
        message = gitrepo.scrub("fatal: bad credentials ghp_secret", "ghp_secret")
        self.assertNotIn("ghp_secret", message)
        self.assertIn("***", message)


@unittest.skipIf(git_missing(), "git is not installed")
class CliEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="autocommit-cli-"))
        self.home = self.root / "home"
        self.home.mkdir()
        self._previous = os.environ.get(paths.HOME_ENV)
        os.environ[paths.HOME_ENV] = str(self.home)

        self.bare = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.bare)],
                       capture_output=True, text=True, check=True)
        self.workdir = self.root / "work"

        config.save(Settings(
            account="tester",
            author_name="CLI Tester",
            author_email="7+cli@users.noreply.github.com",
            repo=RepoTarget(owner="tester", name="activity-log", branch="main"),
            min_commits=1,
            max_commits=2,
            weekday_active_chance=1.0,
            weekend_active_chance=1.0,
        ))

    def tearDown(self):
        if self._previous is None:
            os.environ.pop(paths.HOME_ENV, None)
        else:
            os.environ[paths.HOME_ENV] = self._previous
        paths.remove_tree(self.root)

    def _run(self, *extra):
        from autocommit.cli import main

        argv = ["run", "--from", "2026-03-02", "--to", "2026-03-04", "--seed", "21",
                "--yes", "--quiet", "--remote", self.bare.as_posix(),
                "--workdir", str(self.workdir)]
        return main(argv + list(extra))

    def test_dry_run_changes_nothing(self):
        self.assertEqual(self._run("--dry-run"), 0)
        self.assertEqual(bare_log(self.bare), [])
        self.assertFalse(self.workdir.exists())

    def test_run_pushes_to_the_remote(self):
        self.assertEqual(self._run(), 0)
        commits = bare_log(self.bare)
        self.assertGreater(len(commits), 0)
        for name, email, _, _ in commits:
            self.assertEqual(name, "CLI Tester")
            self.assertEqual(email, "7+cli@users.noreply.github.com")

    def test_seeded_runs_produce_the_same_plan(self):
        self.assertEqual(self._run(), 0)
        first = [subject for _, _, _, subject in bare_log(self.bare)]
        paths.remove_tree(self.workdir)
        paths.remove_tree(self.bare)
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.bare)],
                       capture_output=True, text=True, check=True)
        self.assertEqual(self._run(), 0)
        second = [subject for _, _, _, subject in bare_log(self.bare)]
        self.assertEqual(first, second)

    def test_run_without_a_selected_repository_fails_cleanly(self):
        from autocommit.cli import main

        config.save(Settings(account="tester"))
        self.assertEqual(main(["run", "--dry-run"]), 1)

    def test_status_runs_without_a_token(self):
        from unittest import mock

        from autocommit.cli import main

        saved = {name: os.environ.pop(name, None)
                 for name in ("AUTOCOMMIT_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")}
        try:
            with mock.patch("autocommit.auth.gh_token", return_value=""):
                self.assertEqual(main(["status"]), 0)
        finally:
            for name, value in saved.items():
                if value is not None:
                    os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
