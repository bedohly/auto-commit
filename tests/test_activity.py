"""Issue / pull request / review automation.

The GitHub side is a recording fake; the git side is real, against a local
bare repository. Nothing here reaches github.com.
"""

import os
import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from autocommit import activity, config, messages, paths, planner, runner
from autocommit.config import RepoTarget, Settings
from autocommit.github import GitHubError


def git_missing():
    return shutil.which("git") is None


class FakeClient:
    """Records every call and hands back predictable numbers."""

    def __init__(self, login="tester", merge_ok=True, review_error=False):
        self.login = login
        self.merge_ok = merge_ok
        self.review_error = review_error
        self.calls = []
        self._next = 100

    def _number(self):
        self._next += 1
        return self._next

    def whoami(self):
        from autocommit.github import User

        return User(login=self.login, id=42, name="Tester")

    def create_issue(self, owner, name, title, body=""):
        number = self._number()
        self.calls.append(("issue", owner, name, title, number))
        return number

    def close_issue(self, owner, name, number):
        self.calls.append(("close_issue", owner, name, number))

    def create_pull(self, owner, name, title, head, base, body=""):
        number = self._number()
        self.calls.append(("pull", owner, name, head, base, number))
        return number

    def create_review(self, owner, name, number, body, event="COMMENT"):
        if self.review_error:
            raise GitHubError("Can not approve your own pull request", 422)
        self.calls.append(("review", number, event))

    def merge_pull(self, owner, name, number, method="squash"):
        self.calls.append(("merge", number, method))
        return self.merge_ok

    def delete_branch(self, owner, name, branch):
        self.calls.append(("delete_branch", branch))
        return True

    def kinds(self):
        return [call[0] for call in self.calls]


def settings(**overrides):
    base = Settings(
        account="tester",
        author_name="Test Person",
        author_email="99+tester@users.noreply.github.com",
        repo=RepoTarget(owner="tester", name="activity-log", branch="main"),
        activity_enabled=True,
        activity_chance=1.0,
        issues_min=1, issues_max=1,
        pulls_min=1, pulls_max=1,
        pull_commits_min=1, pull_commits_max=1,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


class PlanTests(unittest.TestCase):
    def test_zero_chance_produces_nothing(self):
        plan = activity.build_plan(settings(activity_chance=0.0), random.Random(1))
        self.assertTrue(plan.is_empty)
        self.assertEqual(plan.describe(), "nothing today")

    def test_counts_stay_within_bounds(self):
        cfg = settings(issues_min=1, issues_max=3, pulls_min=0, pulls_max=2)
        for seed in range(30):
            plan = activity.build_plan(cfg, random.Random(seed))
            self.assertGreaterEqual(plan.issues, 1)
            self.assertLessEqual(plan.issues, 3)
            self.assertLessEqual(plan.pulls, 2)
            self.assertEqual(len(plan.pull_commits), plan.pulls)

    def test_plan_is_deterministic_for_a_seed(self):
        cfg = settings(issues_max=3, pulls_max=3, pull_commits_max=4)
        first = activity.build_plan(cfg, random.Random(9))
        second = activity.build_plan(cfg, random.Random(9))
        self.assertEqual(first, second)

    def test_describe_mentions_what_will_happen(self):
        plan = activity.build_plan(settings(), random.Random(2))
        text = plan.describe()
        self.assertIn("pull request", text)
        self.assertIn("issue", text)
        self.assertIn("merged", text)

    def test_toggles_are_carried_into_the_plan(self):
        plan = activity.build_plan(
            settings(review_pulls=False, merge_pulls=False, close_issues=False),
            random.Random(3))
        self.assertFalse(plan.review)
        self.assertFalse(plan.merge)
        self.assertFalse(plan.close)


class OwnershipTests(unittest.TestCase):
    def test_owner_passes(self):
        activity.guard_ownership(settings(), "tester")
        activity.guard_ownership(settings(), "TESTER")  # login case does not matter

    def test_someone_elses_repository_is_refused(self):
        cfg = settings()
        cfg.repo.owner = "another-person"
        with self.assertRaises(activity.OwnershipError) as caught:
            activity.guard_ownership(cfg, "tester")
        message = str(caught.exception)
        self.assertIn("repositories you own", message)
        self.assertIn("spam", message)

    def test_unset_repository_is_refused(self):
        with self.assertRaises(activity.OwnershipError):
            activity.guard_ownership(Settings(), "tester")


class MessageTests(unittest.TestCase):
    def test_issue_and_pull_copy(self):
        rng = random.Random(4)
        title, body = messages.issue(rng)
        self.assertIn(title, messages.ISSUE_TITLES)
        self.assertIn(body, messages.ISSUE_BODIES)
        title, body = messages.pull(rng)
        self.assertIn(title, messages.PULL_TITLES)
        self.assertIn(body, messages.PULL_BODIES)
        self.assertIn(messages.review(rng), messages.REVIEW_BODIES)

    def test_branch_names_are_namespaced_and_unique(self):
        rng = random.Random(5)
        names = {messages.branch_name(rng, "20260816", index) for index in range(5)}
        self.assertEqual(len(names), 5)
        for name in names:
            self.assertTrue(name.startswith("autocommit/"))
            self.assertIn("20260816", name)


@unittest.skipIf(git_missing(), "git is not installed")
class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="autocommit-activity-"))
        self.home = self.root / "home"
        self.home.mkdir()
        self._previous = os.environ.get(paths.HOME_ENV)
        os.environ[paths.HOME_ENV] = str(self.home)

        self.bare = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.bare)],
                       capture_output=True, text=True, check=True)
        self.remote_url = self.bare.as_posix()
        self.workdir = self.root / "work"
        self.settings = settings()
        self.now = datetime(2026, 8, 16, 14, 30, 0)

    def tearDown(self):
        if self._previous is None:
            os.environ.pop(paths.HOME_ENV, None)
        else:
            os.environ[paths.HOME_ENV] = self._previous
        paths.remove_tree(self.root)

    def _seed_repository(self):
        """Give the remote a main branch with one commit, like a real repo."""
        plan = planner.build_plan(self.now.date(), self.now.date(), self.settings,
                                  random.Random(1))
        runner.execute(self.settings, plan[:1], workdir=self.workdir,
                       remote_url=self.remote_url)

    def _branches(self):
        result = subprocess.run(
            ["git", "--git-dir", str(self.bare), "branch", "--format=%(refname:short)"],
            capture_output=True, text=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _run(self, plan, client=None, rng=None):
        client = client or FakeClient()
        result = activity.execute(
            self.settings, plan, client, workdir=self.workdir,
            remote_url=self.remote_url, rng=rng or random.Random(7), now=self.now)
        return client, result

    def test_empty_plan_does_nothing(self):
        client, result = self._run(activity.ActivityPlan())
        self.assertEqual(client.calls, [])
        self.assertEqual(result.pulls, [])

    def test_issue_only_plan_needs_no_repository(self):
        client, result = self._run(activity.ActivityPlan(issues=2, close=True))
        self.assertEqual(len(result.issues), 2)
        self.assertEqual(client.kinds(), ["issue", "close_issue", "issue", "close_issue"])
        self.assertFalse(self.workdir.exists())

    def test_issues_stay_open_when_close_is_off(self):
        client, _ = self._run(activity.ActivityPlan(issues=1, close=False))
        self.assertEqual(client.kinds(), ["issue"])

    def test_pull_request_pushes_a_real_branch(self):
        self._seed_repository()
        plan = activity.ActivityPlan(pulls=1, pull_commits=[2], review=True, merge=False)
        client, result = self._run(plan)

        self.assertEqual(len(result.pulls), 1)
        self.assertEqual(result.reviews, 1)
        pushed = [name for name in self._branches() if name.startswith("autocommit/")]
        self.assertEqual(len(pushed), 1)

        head = [call for call in client.calls if call[0] == "pull"][0][3]
        self.assertEqual(head, pushed[0])
        base = [call for call in client.calls if call[0] == "pull"][0][4]
        self.assertEqual(base, "main")

        count = subprocess.run(
            ["git", "--git-dir", str(self.bare), "rev-list", "--count", pushed[0], "^main"],
            capture_output=True, text=True)
        self.assertEqual(count.stdout.strip(), "2")

    def test_merge_deletes_the_remote_branch(self):
        self._seed_repository()
        plan = activity.ActivityPlan(pulls=1, pull_commits=[1], merge=True)
        client, result = self._run(plan)
        self.assertEqual(result.merged, 1)
        self.assertIn("merge", client.kinds())
        self.assertIn("delete_branch", client.kinds())

    def test_unmergeable_pull_request_is_reported_not_raised(self):
        self._seed_repository()
        plan = activity.ActivityPlan(pulls=1, pull_commits=[1], merge=True)
        events = []
        client = FakeClient(merge_ok=False)
        activity.execute(self.settings, plan, client, workdir=self.workdir,
                         remote_url=self.remote_url, rng=random.Random(2),
                         now=self.now, on_event=events.append)
        self.assertNotIn("delete_branch", client.kinds())
        self.assertTrue(any("could not be merged" in line for line in events))

    def test_a_failing_review_does_not_abort_the_run(self):
        self._seed_repository()
        plan = activity.ActivityPlan(pulls=1, pull_commits=[1], review=True, merge=False,
                                     issues=1)
        events = []
        client = FakeClient(review_error=True)
        result = activity.execute(self.settings, plan, client, workdir=self.workdir,
                                  remote_url=self.remote_url, rng=random.Random(3),
                                  now=self.now, on_event=events.append)
        self.assertEqual(result.reviews, 0)
        self.assertEqual(len(result.issues), 1)
        self.assertTrue(any("review on" in line for line in events))

    def test_empty_repository_skips_pull_requests_but_keeps_issues(self):
        plan = activity.ActivityPlan(pulls=1, pull_commits=[1], issues=1)
        client, result = self._run(plan)
        self.assertEqual(result.pulls, [])
        self.assertEqual(len(result.issues), 1)
        self.assertIn("no commits yet", result.skipped)

    def test_two_pull_requests_use_distinct_branches(self):
        self._seed_repository()
        plan = activity.ActivityPlan(pulls=2, pull_commits=[1, 1], merge=False)
        client, result = self._run(plan)
        self.assertEqual(len(result.pulls), 2)
        pushed = [name for name in self._branches() if name.startswith("autocommit/")]
        self.assertEqual(len(set(pushed)), 2)

    def test_the_default_branch_is_left_checked_out(self):
        self._seed_repository()
        plan = activity.ActivityPlan(pulls=1, pull_commits=[1], merge=False)
        self._run(plan)
        repo = runner.open_repo(self.settings, workdir=self.workdir,
                                remote_url=self.remote_url)
        self.assertEqual(repo.current_branch(), "main")

    def test_main_is_untouched_when_nothing_is_merged(self):
        self._seed_repository()
        before = subprocess.run(
            ["git", "--git-dir", str(self.bare), "rev-parse", "main"],
            capture_output=True, text=True).stdout.strip()
        self._run(activity.ActivityPlan(pulls=1, pull_commits=[1], merge=False))
        after = subprocess.run(
            ["git", "--git-dir", str(self.bare), "rev-parse", "main"],
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(before, after)


class ConfigTests(unittest.TestCase):
    def test_activity_is_off_by_default(self):
        self.assertFalse(Settings().activity_enabled)

    def test_activity_fields_are_editable(self):
        for key in ("activity_enabled", "activity_chance", "issues_min", "issues_max",
                    "pulls_min", "pulls_max", "pull_commits_min", "pull_commits_max",
                    "review_pulls", "merge_pulls", "close_issues"):
            self.assertIn(key, config.EDITABLE)

    def test_booleans_can_be_set_from_text(self):
        cfg = Settings()
        config.apply_setting(cfg, "activity_enabled", "true")
        self.assertTrue(cfg.activity_enabled)
        config.apply_setting(cfg, "activity_enabled", "off")
        self.assertFalse(cfg.activity_enabled)
        with self.assertRaises(ValueError):
            config.apply_setting(cfg, "activity_enabled", "maybe")

    def test_bad_ranges_are_rejected(self):
        for key, value in (("issues_max", "-1"), ("pulls_max", "99"),
                           ("pull_commits_min", "0"), ("activity_chance", "2")):
            with self.assertRaises(ValueError):
                config.apply_setting(Settings(), key, value)


if __name__ == "__main__":
    unittest.main()
