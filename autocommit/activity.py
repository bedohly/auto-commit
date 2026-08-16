"""Issues, pull requests and reviews.

Unlike commits, none of this can be backdated: GitHub stamps an issue or a pull
request at the moment it is created, so an activity run only ever affects
today. It is also public in a way commits are not — the items sit in the
repository's Issues and Pull requests tabs for anyone to read.

Everything here is restricted to repositories the authenticated user owns.
Opening automated issues or pull requests against somebody else's project is
spam, so `guard_ownership` refuses it outright rather than leaving it to the
caller to remember.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from autocommit import messages, runner
from autocommit.config import Settings
from autocommit.github import GitHubClient, GitHubError


class OwnershipError(Exception):
    """Raised when the target repository is not owned by the signed-in user."""


@dataclass
class ActivityPlan:
    issues: int = 0
    pulls: int = 0
    pull_commits: list = field(default_factory=list)
    review: bool = False
    merge: bool = False
    close: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.issues and not self.pulls

    def describe(self) -> str:
        if self.is_empty:
            return "nothing today"
        parts = []
        if self.pulls:
            total = sum(self.pull_commits)
            parts.append("{0} pull request(s) with {1} commit(s)".format(self.pulls, total))
            if self.review:
                parts.append("a review on each")
            if self.merge:
                parts.append("merged and branch deleted")
        if self.issues:
            parts.append("{0} issue(s)".format(self.issues))
            if self.close:
                parts.append("closed again")
        return ", ".join(parts)


@dataclass
class ActivityResult:
    issues: list = field(default_factory=list)
    pulls: list = field(default_factory=list)
    reviews: int = 0
    merged: int = 0
    skipped: str = ""


def build_plan(settings: Settings, rng: "random.Random | None" = None) -> ActivityPlan:
    """Decide what today's activity run should create."""
    settings.validate()
    rng = rng or random.Random()
    if rng.random() >= settings.activity_chance:
        return ActivityPlan()

    plan = ActivityPlan(
        issues=rng.randint(settings.issues_min, settings.issues_max),
        pulls=rng.randint(settings.pulls_min, settings.pulls_max),
        review=settings.review_pulls,
        merge=settings.merge_pulls,
        close=settings.close_issues,
    )
    plan.pull_commits = [
        rng.randint(settings.pull_commits_min, settings.pull_commits_max)
        for _ in range(plan.pulls)
    ]
    return plan


def guard_ownership(settings: Settings, login: str) -> None:
    """Refuse to touch a repository the signed-in user does not own."""
    owner = (settings.repo.owner or "").lower()
    if not owner:
        raise OwnershipError("No repository selected.")
    if owner != (login or "").lower():
        raise OwnershipError(
            "Issue and pull request automation only runs on repositories you own. "
            "{0} belongs to {1}, not {2}. Opening automated items in someone "
            "else's repository is spam.".format(
                settings.repo.full_name, settings.repo.owner, login or "this account")
        )


def execute(settings: Settings, plan: ActivityPlan, client: GitHubClient,
            token: str = "", workdir=None, remote_url: str = "",
            rng: "random.Random | None" = None, now: "datetime | None" = None,
            on_event=None) -> ActivityResult:
    """Create the planned issues and pull requests."""
    rng = rng or random.Random()
    now = now or datetime.now()
    result = ActivityResult()
    if plan.is_empty:
        return result

    owner, name = settings.repo.owner, settings.repo.name
    base = settings.repo.branch or "main"

    def announce(text):
        if on_event:
            on_event(text)

    if plan.pulls:
        repo = runner.open_repo(settings, token=token, workdir=workdir,
                                remote_url=remote_url)
        repo.sync()
        if not repo.has_commits():
            result.skipped = ("The repository has no commits yet, so a pull request has "
                              "nothing to branch from. Run a normal commit round first.")
            plan = ActivityPlan(issues=plan.issues, close=plan.close)
        else:
            repo.configure_identity(
                settings.author_name or settings.account or "autocommit",
                settings.author_email or "autocommit@users.noreply.github.com",
            )
            stamp = now.strftime("%Y%m%d")
            for index in range(plan.pulls):
                branch = messages.branch_name(rng, stamp, index + 1)
                repo.sync()
                repo.start_branch(branch)
                for _ in range(plan.pull_commits[index]):
                    message = messages.build(rng, settings.message_style)
                    repo.append_entry(settings.commit_file,
                                      runner.entry_line(now, message))
                    repo.commit(settings.commit_file, message, now,
                                settings.author_name or settings.account or "autocommit",
                                settings.author_email or
                                "autocommit@users.noreply.github.com")
                repo.push_branch(branch)
                announce("pushed branch {0}".format(branch))

                title, body = messages.pull(rng)
                number = client.create_pull(owner, name, title, branch, base, body)
                result.pulls.append(number)
                announce("opened pull request #{0}".format(number))

                if plan.review:
                    try:
                        client.create_review(owner, name, number, messages.review(rng))
                        result.reviews += 1
                        announce("reviewed #{0}".format(number))
                    except GitHubError as exc:
                        announce("review on #{0} failed: {1}".format(number, exc))

                if plan.merge:
                    if client.merge_pull(owner, name, number):
                        result.merged += 1
                        announce("merged #{0}".format(number))
                        client.delete_branch(owner, name, branch)
                    else:
                        announce("#{0} could not be merged automatically".format(number))

                repo.switch(base)
                repo.delete_local_branch(branch)

    for _ in range(plan.issues):
        title, body = messages.issue(rng)
        number = client.create_issue(owner, name, title, body)
        result.issues.append(number)
        announce("opened issue #{0}".format(number))
        if plan.close:
            client.close_issue(owner, name, number)
            announce("closed issue #{0}".format(number))

    return result
