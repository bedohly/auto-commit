"""Persisted settings for autocommit."""

from __future__ import annotations

import json
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

    commit_file: str = DEFAULT_COMMIT_FILE
    min_commits: int = 1
    max_commits: int = 6
    weekday_active_chance: float = 0.85
    weekend_active_chance: float = 0.45
    active_hour_start: int = 9
    active_hour_end: int = 23
    message_style: str = "mixed"  # casual | conventional | mixed
    jitter_minutes: int = 0

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
