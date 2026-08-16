"""Token discovery and storage.

Resolution order:
  1. --token argument / AUTOCOMMIT_TOKEN / GITHUB_TOKEN
  2. the token saved by `autocommit login`
  3. the GitHub CLI (`gh auth token`), when installed and logged in
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

from autocommit import paths

ENV_VARS = ("AUTOCOMMIT_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
REQUIRED_SCOPES = ("repo", "public_repo")


@dataclass
class TokenInfo:
    value: str
    source: str  # env | file | gh

    def masked(self) -> str:
        if len(self.value) <= 8:
            return "*" * len(self.value)
        return "{0}{1}{2}".format(self.value[:4], "*" * 8, self.value[-4:])


def gh_available() -> bool:
    return shutil.which("gh") is not None


def gh_token() -> str:
    """Return the token from the GitHub CLI, or an empty string."""
    if not gh_available():
        return ""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def env_token() -> str:
    for name in ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def stored_token() -> str:
    path = paths.token_file()
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def store_token(token: str) -> None:
    path = paths.token_file()
    paths.ensure_dir(path.parent)
    path.write_text(token.strip() + "\n", encoding="utf-8")
    paths.harden(path)


def forget_token() -> bool:
    path = paths.token_file()
    if path.exists():
        path.unlink()
        return True
    return False


def resolve(explicit: str = "") -> "TokenInfo | None":
    if explicit:
        return TokenInfo(explicit.strip(), "argument")
    value = env_token()
    if value:
        return TokenInfo(value, "environment")
    value = stored_token()
    if value:
        return TokenInfo(value, "saved login")
    value = gh_token()
    if value:
        return TokenInfo(value, "github cli")
    return None


def missing_scope(scopes) -> bool:
    """True when the token clearly cannot push to a repository.

    Fine-grained tokens report no scopes at all, so an empty list is treated as
    'unknown' rather than 'insufficient'.
    """
    if not scopes:
        return False
    return not any(scope in scopes for scope in REQUIRED_SCOPES)
