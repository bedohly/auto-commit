"""Thin wrapper around the git binary.

The token is handed to git through a one-shot credential helper that reads an
environment variable, so it never lands in argv, in .git/config, or on disk.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from autocommit import paths

TOKEN_ENV = "AUTOCOMMIT_GIT_TOKEN"

CREDENTIAL_HELPER = (
    '!f() { test "$1" = get && '
    'echo username=x-access-token && '
    'echo "password=$' + TOKEN_ENV + '"; }; f'
)

BASE_CONFIG = [
    "-c", "core.autocrlf=false",
    "-c", "core.safecrlf=false",
    "-c", "commit.gpgsign=false",
    "-c", "tag.gpgsign=false",
    "-c", "advice.detachedHead=false",
    "-c", "gc.auto=0",
]


class GitError(Exception):
    pass


def git_path() -> str:
    found = shutil.which("git")
    if not found:
        raise GitError("git was not found on PATH. Install git and try again.")
    return found


def git_version() -> str:
    result = run(["--version"])
    return result.stdout.strip()


def run(args, cwd: "Path | None" = None, token: str = "", check: bool = True, timeout: int = 300):
    """Run a git command and return the CompletedProcess."""
    command = [git_path()] + list(BASE_CONFIG)
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env.setdefault("LC_ALL", "C")
    if token:
        env[TOKEN_ENV] = token
        command += ["-c", "credential.helper=", "-c", "credential.helper=" + CREDENTIAL_HELPER]
    command += list(args)
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError("git timed out after {0}s: git {1}".format(timeout, " ".join(args))) from exc
    except OSError as exc:
        raise GitError("Could not start git: {0}".format(exc)) from exc
    if check and result.returncode != 0:
        raise GitError(scrub(result.stderr.strip() or result.stdout.strip(), token))
    return result


def scrub(text: str, token: str) -> str:
    if token and token in text:
        text = text.replace(token, "***")
    return text or "git failed with no output"


def git_date(when: datetime) -> str:
    """Format a naive local datetime the way git expects, with a real offset."""
    aware = when if when.tzinfo else when.astimezone()
    return aware.strftime("%Y-%m-%dT%H:%M:%S%z")


class LocalRepo:
    """A cached working copy of the target repository."""

    def __init__(self, path, remote_url: str, branch: str, token: str = ""):
        self.path = Path(path)
        self.remote_url = remote_url
        self.branch = branch
        self.token = token

    # -- helpers ----------------------------------------------------------
    def _git(self, args, check: bool = True, timeout: int = 300):
        return run(args, cwd=self.path, token=self.token, check=check, timeout=timeout)

    @property
    def is_initialized(self) -> bool:
        return (self.path / ".git").exists()

    def head(self) -> str:
        result = self._git(["rev-parse", "HEAD"], check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    def has_commits(self) -> bool:
        return bool(self.head())

    def commit_count(self) -> int:
        result = self._git(["rev-list", "--count", "HEAD"], check=False)
        if result.returncode != 0:
            return 0
        try:
            return int(result.stdout.strip())
        except ValueError:
            return 0

    # -- lifecycle --------------------------------------------------------
    def sync(self) -> str:
        """Make the working copy match the remote branch. Returns a status word."""
        if not self.is_initialized:
            return self._create()
        self._git(["remote", "set-url", "origin", self.remote_url], check=False)
        fetched = self._git(
            ["fetch", "--depth=1", "origin", self.branch], check=False, timeout=600
        )
        if fetched.returncode == 0:
            self._git(["checkout", "-B", self.branch, "FETCH_HEAD"])
            self._git(["reset", "--hard", "FETCH_HEAD"])
        else:
            # Remote branch does not exist yet (brand-new repository).
            self._git(["checkout", "-B", self.branch], check=False)
        self._git(["clean", "-fd"], check=False)
        return "updated"

    def _create(self) -> str:
        if self.path.exists():
            paths.remove_tree(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        cloned = run(
            [
                "clone",
                "--depth=1",
                "--single-branch",
                "--branch",
                self.branch,
                self.remote_url,
                str(self.path),
            ],
            token=self.token,
            check=False,
            timeout=900,
        )
        if cloned.returncode == 0:
            return "cloned"
        # An empty repository cannot be cloned with --branch; start from scratch.
        self.path.mkdir(parents=True, exist_ok=True)
        self._git(["init"])
        # HEAD is unborn here, so point it at the target branch directly.
        self._git(["symbolic-ref", "HEAD", "refs/heads/" + self.branch])
        self._git(["remote", "add", "origin", self.remote_url], check=False)
        return "initialized"

    # -- branches ---------------------------------------------------------
    def start_branch(self, name: str) -> None:
        """Create (or reset) a working branch on top of the current HEAD."""
        self._git(["checkout", "-B", name])

    def switch(self, name: str) -> None:
        self._git(["checkout", name])

    def current_branch(self) -> str:
        result = self._git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    def push_branch(self, name: str) -> str:
        result = self._git(
            ["push", "--force-with-lease", "origin", "HEAD:refs/heads/" + name],
            check=False,
            timeout=900,
        )
        if result.returncode != 0:
            raise GitError(scrub(result.stderr.strip() or result.stdout.strip(), self.token))
        return scrub((result.stderr or result.stdout).strip(), self.token)

    def delete_local_branch(self, name: str) -> None:
        self._git(["branch", "-D", name], check=False)

    def configure_identity(self, name: str, email: str) -> None:
        self._git(["config", "user.name", name])
        self._git(["config", "user.email", email])

    # -- writing ----------------------------------------------------------
    def append_entry(self, relative_path: str, line: str) -> None:
        target = self.path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        header_needed = not target.exists() or target.stat().st_size == 0
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            if header_needed:
                handle.write("# Activity log\n\n")
            handle.write(line.rstrip("\n") + "\n")

    def commit(self, relative_path: str, message: str, when: datetime,
               author_name: str, author_email: str) -> str:
        stamp = git_date(when)
        overrides = {
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
        }
        previous = {key: os.environ.get(key) for key in overrides}
        os.environ.update(overrides)
        try:
            self._git(["add", "--", relative_path])
            self._git(["commit", "--allow-empty", "-m", message])
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        return self.head()

    def push(self) -> str:
        result = self._git(
            ["push", "origin", "HEAD:refs/heads/" + self.branch],
            check=False,
            timeout=900,
        )
        if result.returncode != 0:
            raise GitError(scrub(result.stderr.strip() or result.stdout.strip(), self.token))
        return scrub((result.stderr or result.stdout).strip(), self.token)
