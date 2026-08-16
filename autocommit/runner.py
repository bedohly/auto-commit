"""Ties settings, the plan and the local clone together."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from autocommit import paths, planner
from autocommit.config import Settings
from autocommit.gitrepo import LocalRepo


@dataclass
class RunResult:
    plan: list = field(default_factory=list)
    created: int = 0
    pushed: bool = False
    repo_status: str = ""
    head_before: str = ""
    head_after: str = ""
    workdir: str = ""

    @property
    def days(self) -> int:
        return len(planner.summarize(self.plan))


def entry_line(when: datetime, message: str) -> str:
    stamp = (when if when.tzinfo else when.astimezone()).isoformat(timespec="seconds")
    return "- {0} - {1}".format(stamp, message)


def build_plan(settings: Settings, start: date, end: date, seed: "int | None" = None):
    rng = random.Random(seed) if seed is not None else random.Random()
    return planner.build_plan(start, end, settings, rng)


def open_repo(settings: Settings, token: str = "", workdir: "Path | None" = None,
              remote_url: str = "") -> LocalRepo:
    target = settings.repo
    path = workdir or paths.repo_workdir(target.owner, target.name)
    return LocalRepo(
        path=path,
        remote_url=remote_url or target.clone_url,
        branch=target.branch or "main",
        token=token,
    )


def execute(settings: Settings, plan, token: str = "", push: bool = True,
            workdir: "Path | None" = None, remote_url: str = "",
            on_progress=None) -> RunResult:
    """Create every planned commit locally and (optionally) push them."""
    settings.validate()
    result = RunResult(plan=list(plan))
    if not plan:
        return result

    repo = open_repo(settings, token=token, workdir=workdir, remote_url=remote_url)
    result.workdir = str(repo.path)
    result.repo_status = repo.sync()
    result.head_before = repo.head()

    author_name = settings.author_name or settings.account or "autocommit"
    author_email = settings.author_email or "autocommit@users.noreply.github.com"
    repo.configure_identity(author_name, author_email)

    for index, item in enumerate(plan, start=1):
        repo.append_entry(settings.commit_file, entry_line(item.when, item.message))
        repo.commit(
            relative_path=settings.commit_file,
            message=item.message,
            when=item.when,
            author_name=author_name,
            author_email=author_email,
        )
        result.created += 1
        if on_progress:
            on_progress(index, len(plan), item)

    result.head_after = repo.head()
    if push:
        repo.push()
        result.pushed = True
    return result


def append_run_log(result: RunResult, settings: Settings, when: datetime) -> None:
    path = paths.log_file()
    paths.ensure_dir(path.parent)
    line = "{0}\t{1}\tcommits={2}\tdays={3}\tpushed={4}\n".format(
        when.isoformat(timespec="seconds"),
        settings.repo.full_name,
        result.created,
        result.days,
        "yes" if result.pushed else "no",
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
