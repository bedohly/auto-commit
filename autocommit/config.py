"""Persisted settings for autocommit."""

from __future__ import annotations

import json
from datetime import datetime
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from autocommit import paths

DEFAULT_COMMIT_FILE = "activity.md"


@dataclass
class RepoTarget:
    owner: str = ""
    name: str = ""
    branch: str = "main"
    private: bool = False

    @property
    def full_name(self) -> str:
        return "{0}/{1}".format(self.owner, self.name)

    @property
    def clone_url(self) -> str:
        return "https://github.com/{0}/{1}.git".format(self.owner, self.name)

    def is_set(self) -> bool:
        return bool(self.owner and self.name)


@dataclass
class Settings:
    """Everything the tool needs between runs, minus the token."""

    account: str = ""
    author_name: str = ""
    author_email: str = ""
    repo: RepoTarget = field(default_factory=RepoTarget)

    # These defaults are the 'starter' profile: the quietest one, ramping up
    # over its first month. See autocommit/profiles.py.
    commit_file: str = DEFAULT_COMMIT_FILE
    min_commits: int = 1
    max_commits: int = 2
    weekday_active_chance: float = 0.45
    weekend_active_chance: float = 0.15
    active_hour_start: int = 10
    active_hour_end: int = 22
    message_style: str = "mixed"  # casual | conventional | mixed
    jitter_minutes: int = 0

    # Which preset was applied, and the ramp it starts from. During the first
    # `ramp_days` days after `started_on` the rate grows from almost nothing to
    # the configured one, instead of switching on at full volume.
    profile: str = "starter"
    ramp_days: int = 30
    started_on: str = ""

    # Issue / pull request / review automation. Off by default: unlike commits,
    # these cannot be backdated and they are visible to anyone browsing the repo.
    activity_enabled: bool = False
    activity_chance: float = 0.5
    issues_min: int = 0
    issues_max: int = 1
    pulls_min: int = 0
    pulls_max: int = 1
    pull_commits_min: int = 1
    pull_commits_max: int = 3
    review_pulls: bool = True
    merge_pulls: bool = True
    close_issues: bool = True

    def validate(self) -> None:
        if self.min_commits < 1:
            raise ValueError("min_commits must be at least 1")
        if self.max_commits < self.min_commits:
            raise ValueError("max_commits must be greater than or equal to min_commits")
        if self.max_commits > 100:
            raise ValueError("max_commits must be 100 or lower")
        for name in ("weekday_active_chance", "weekend_active_chance"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError("{0} must be between 0 and 1".format(name))
        if not 0 <= self.active_hour_start <= 23:
            raise ValueError("active_hour_start must be between 0 and 23")
        if not 1 <= self.active_hour_end <= 24:
            raise ValueError("active_hour_end must be between 1 and 24")
        if self.active_hour_end <= self.active_hour_start:
            raise ValueError("active_hour_end must be greater than active_hour_start")
        if self.message_style not in ("casual", "conventional", "mixed"):
            raise ValueError("message_style must be casual, conventional or mixed")
        if self.jitter_minutes < 0:
            raise ValueError("jitter_minutes cannot be negative")
        if self.ramp_days < 0:
            raise ValueError("ramp_days cannot be negative")
        if self.ramp_days > 3650:
            raise ValueError("ramp_days must be 3650 or lower")
        if self.started_on:
            try:
                datetime.strptime(self.started_on, "%Y-%m-%d")
            except ValueError:
                raise ValueError("started_on must look like YYYY-MM-DD")
        for low, high in (("issues_min", "issues_max"),
                          ("pulls_min", "pulls_max"),
                          ("pull_commits_min", "pull_commits_max")):
            low_value, high_value = getattr(self, low), getattr(self, high)
            if low_value < 0:
                raise ValueError("{0} cannot be negative".format(low))
            if high_value < low_value:
                raise ValueError("{0} must be greater than or equal to {1}".format(high, low))
            if high_value > 20:
                raise ValueError("{0} must be 20 or lower".format(high))
        if self.pull_commits_min < 1:
            raise ValueError("pull_commits_min must be at least 1")
        if not 0.0 <= self.activity_chance <= 1.0:
            raise ValueError("activity_chance must be between 0 and 1")
        if not self.commit_file or self.commit_file.startswith(("/", "\\")):
            raise ValueError("commit_file must be a relative path inside the repository")
        if ".." in Path(self.commit_file).parts:
            raise ValueError("commit_file must stay inside the repository")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        data = {key: value for key, value in (raw or {}).items() if key in known}
        repo_raw = data.pop("repo", None) or {}
        settings = cls(**data)
        if isinstance(repo_raw, dict):
            repo_known = {f.name for f in fields(RepoTarget)}
            settings.repo = RepoTarget(
                **{k: v for k, v in repo_raw.items() if k in repo_known}
            )
        return settings


EDITABLE = (
    "commit_file",
    "min_commits",
    "max_commits",
    "weekday_active_chance",
    "weekend_active_chance",
    "active_hour_start",
    "active_hour_end",
    "message_style",
    "author_name",
    "author_email",
    "jitter_minutes",
    "ramp_days",
    "activity_enabled",
    "activity_chance",
    "issues_min",
    "issues_max",
    "pulls_min",
    "pulls_max",
    "pull_commits_min",
    "pull_commits_max",
    "review_pulls",
    "merge_pulls",
    "close_issues",
)


def coerce(current, raw: str):
    """Convert a string from the console into the type the field already has."""
    if isinstance(current, bool):
        lowered = raw.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ValueError("Expected true or false, got '{0}'.".format(raw))
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            raise ValueError("Expected a whole number, got '{0}'.".format(raw))
    if isinstance(current, float):
        try:
            return float(raw)
        except ValueError:
            raise ValueError("Expected a number, got '{0}'.".format(raw))
    return raw


def apply_setting(settings: Settings, key: str, raw: str) -> Settings:
    """Set one editable field, validating the result before returning."""
    key = key.strip().lower()
    if key not in EDITABLE:
        raise ValueError(
            "Unknown setting '{0}'. Editable settings: {1}".format(key, ", ".join(EDITABLE))
        )
    previous = getattr(settings, key)
    setattr(settings, key, coerce(previous, raw))
    try:
        settings.validate()
    except ValueError:
        setattr(settings, key, previous)
        raise
    return settings


def load() -> Settings:
    path = paths.config_file()
    if not path.exists():
        return Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    return Settings.from_dict(raw)


def save(settings: Settings) -> Path:
    settings.validate()
    path = paths.config_file()
    paths.ensure_dir(path.parent)
    payload = json.dumps(settings.to_dict(), indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    return path
