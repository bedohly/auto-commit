"""Platform-aware locations for configuration, state and cached repositories."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

APP_NAME = "autocommit"
HOME_ENV = "AUTOCOMMIT_HOME"


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _override() -> "Path | None":
    raw = os.environ.get(HOME_ENV)
    return Path(raw).expanduser() if raw else None


def config_dir() -> Path:
    """Directory holding config.json and the stored token."""
    override = _override()
    if override:
        return override / "config"
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(_home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(_home() / ".config")
    return Path(base) / APP_NAME


def data_dir() -> Path:
    """Directory holding cached clones and run logs."""
    override = _override()
    if override:
        return override / "data"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(_home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(_home() / ".local" / "share")
    return Path(base) / APP_NAME


def config_file() -> Path:
    return config_dir() / "config.json"


def token_file() -> Path:
    return config_dir() / "token"


def repos_dir() -> Path:
    return data_dir() / "repos"


def log_file() -> Path:
    return data_dir() / "run.log"


def repo_workdir(owner: str, name: str) -> Path:
    safe = "{0}__{1}".format(owner, name).replace("/", "_").replace("\\", "_")
    return repos_dir() / safe


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_tree(path) -> None:
    """Delete a directory tree, including git's read-only object files.

    On Windows every file under .git/objects is marked read-only, and a plain
    shutil.rmtree fails with PermissionError.
    """
    target = Path(path)
    if not target.exists():
        return

    def _force(func, item, _exc):
        try:
            os.chmod(item, stat.S_IWRITE)
            func(item)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(str(target), onexc=_force)
    else:  # pragma: no cover - older interpreters
        shutil.rmtree(str(target), onerror=_force)


def harden(path: Path) -> None:
    """Best-effort 'owner only' permissions for a secret file."""
    try:
        os.chmod(str(path), 0o600)
    except OSError:
        pass
    if os.name == "nt":
        import subprocess

        user = os.environ.get("USERNAME")
        if not user:
            return
        try:
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", "{0}:F".format(user)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
