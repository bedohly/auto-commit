"""Install or remove a daily run.

Windows  -> Task Scheduler (schtasks)
Linux    -> systemd user timer when available, otherwise crontab
macOS    -> crontab
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from autocommit import paths

TASK_NAME = "AutoCommit"
CRON_MARKER = "# autocommit"
SYSTEMD_UNIT = "autocommit"


class ScheduleError(Exception):
    pass


@dataclass
class ScheduleStatus:
    installed: bool
    backend: str
    detail: str = ""


def is_windows() -> bool:
    return os.name == "nt"


def launch_command(jitter_minutes: int = 0, windowless: bool = True):
    """Best command line for an unattended run on this machine."""
    console_script = shutil.which("autocommit")
    if console_script:
        command = [console_script]
    else:
        executable = sys.executable or "python"
        if is_windows() and windowless:
            candidate = Path(executable).with_name("pythonw.exe")
            if candidate.exists():
                executable = str(candidate)
        command = [executable, "-m", "autocommit"]
    command += ["run", "--today", "--quiet"]
    if jitter_minutes > 0:
        command += ["--jitter", str(jitter_minutes)]
    return command


def _quote(part: str) -> str:
    return '"' + part + '"' if " " in part else part


def command_string(jitter_minutes: int = 0) -> str:
    return " ".join(_quote(part) for part in launch_command(jitter_minutes))


def _run(args, check: bool = True, stdin_text=None):
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, errors="replace",
            input=stdin_text, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScheduleError(str(exc))
    if check and result.returncode != 0:
        raise ScheduleError((result.stderr or result.stdout).strip() or "command failed")
    return result


def _home_env_prefix() -> str:
    value = os.environ.get(paths.HOME_ENV)
    if not value:
        return ""
    return paths.HOME_ENV + '="' + value + '" '


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
def windows_install(hour: int, minute: int, jitter_minutes: int) -> ScheduleStatus:
    command = command_string(jitter_minutes)
    _run([
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/SC", "DAILY",
        "/ST", "{0:02d}:{1:02d}".format(hour, minute),
        "/TR", command,
        "/F",
    ])
    return ScheduleStatus(True, "schtasks", command)


def windows_remove() -> bool:
    result = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=False)
    return result.returncode == 0


def windows_status() -> ScheduleStatus:
    result = _run(["schtasks", "/Query", "/TN", TASK_NAME], check=False)
    if result.returncode != 0:
        return ScheduleStatus(False, "schtasks")
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    return ScheduleStatus(True, "schtasks", lines[-1].strip() if lines else TASK_NAME)


# --------------------------------------------------------------------------
# systemd (user scope)
# --------------------------------------------------------------------------
def systemd_available() -> bool:
    if is_windows() or not shutil.which("systemctl"):
        return False
    result = _run(["systemctl", "--user", "is-system-running"], check=False)
    combined = (result.stdout + result.stderr).lower()
    return "failed to connect" not in combined and "offline" not in combined


def systemd_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "systemd" / "user"


def systemd_units(hour: int, minute: int, jitter_minutes: int):
    """Return the (service, timer) unit file bodies."""
    service_lines = [
        "[Unit]",
        "Description=autocommit daily run",
        "",
        "[Service]",
        "Type=oneshot",
        "ExecStart=" + command_string(0),
    ]
    home_override = os.environ.get(paths.HOME_ENV)
    if home_override:
        service_lines.append("Environment=" + paths.HOME_ENV + "=" + home_override)
    service = "\n".join(service_lines) + "\n"

    timer = "\n".join([
        "[Unit]",
        "Description=autocommit daily timer",
        "",
        "[Timer]",
        "OnCalendar=*-*-* {0:02d}:{1:02d}:00".format(hour, minute),
        "RandomizedDelaySec={0}".format(max(0, jitter_minutes) * 60),
        "Persistent=true",
        "",
        "[Install]",
        "WantedBy=timers.target",
    ]) + "\n"
    return service, timer


def systemd_install(hour: int, minute: int, jitter_minutes: int) -> ScheduleStatus:
    directory = systemd_dir()
    directory.mkdir(parents=True, exist_ok=True)
    service, timer = systemd_units(hour, minute, jitter_minutes)
    (directory / (SYSTEMD_UNIT + ".service")).write_text(service, encoding="utf-8")
    (directory / (SYSTEMD_UNIT + ".timer")).write_text(timer, encoding="utf-8")
    _run(["systemctl", "--user", "daemon-reload"])
    _run(["systemctl", "--user", "enable", "--now", SYSTEMD_UNIT + ".timer"])
    return ScheduleStatus(True, "systemd", str(directory / (SYSTEMD_UNIT + ".timer")))


def systemd_remove() -> bool:
    _run(["systemctl", "--user", "disable", "--now", SYSTEMD_UNIT + ".timer"], check=False)
    removed = False
    for suffix in (".timer", ".service"):
        unit = systemd_dir() / (SYSTEMD_UNIT + suffix)
        if unit.exists():
            unit.unlink()
            removed = True
    _run(["systemctl", "--user", "daemon-reload"], check=False)
    return removed


def systemd_status() -> ScheduleStatus:
    unit = systemd_dir() / (SYSTEMD_UNIT + ".timer")
    if not unit.exists():
        return ScheduleStatus(False, "systemd")
    result = _run(["systemctl", "--user", "list-timers", SYSTEMD_UNIT + ".timer"], check=False)
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    return ScheduleStatus(True, "systemd", lines[0] if lines else str(unit))


# --------------------------------------------------------------------------
# cron
# --------------------------------------------------------------------------
def cron_available() -> bool:
    return not is_windows() and shutil.which("crontab") is not None


def read_crontab() -> str:
    result = _run(["crontab", "-l"], check=False)
    if result.returncode != 0:
        return ""
    return result.stdout


def strip_marker(content: str) -> str:
    kept = [line for line in content.splitlines() if CRON_MARKER not in line]
    return "\n".join(kept).strip("\n")


def cron_line(hour: int, minute: int, jitter_minutes: int) -> str:
    return "{0} {1} * * * {2}{3} {4}".format(
        minute, hour, _home_env_prefix(), command_string(jitter_minutes), CRON_MARKER
    )


def cron_install(hour: int, minute: int, jitter_minutes: int) -> ScheduleStatus:
    body = strip_marker(read_crontab())
    entry = cron_line(hour, minute, jitter_minutes)
    payload = (body + "\n" if body else "") + entry + "\n"
    _run(["crontab", "-"], stdin_text=payload)
    return ScheduleStatus(True, "cron", entry)


def cron_remove() -> bool:
    current = read_crontab()
    if CRON_MARKER not in current:
        return False
    payload = strip_marker(current)
    _run(["crontab", "-"], stdin_text=(payload + "\n") if payload else "")
    return True


def cron_status() -> ScheduleStatus:
    for line in read_crontab().splitlines():
        if CRON_MARKER in line:
            return ScheduleStatus(True, "cron", line.strip())
    return ScheduleStatus(False, "cron")


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------
def pick_backend(preferred: str = "auto") -> str:
    if preferred and preferred != "auto":
        return preferred
    if is_windows():
        return "schtasks"
    if systemd_available():
        return "systemd"
    if cron_available():
        return "cron"
    raise ScheduleError(
        "No supported scheduler found. Install cron or use systemd, then try again."
    )


def install(hour: int, minute: int, jitter_minutes: int = 0,
            backend: str = "auto") -> ScheduleStatus:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ScheduleError("Time must be between 00:00 and 23:59.")
    chosen = pick_backend(backend)
    if chosen == "schtasks":
        return windows_install(hour, minute, jitter_minutes)
    if chosen == "systemd":
        return systemd_install(hour, minute, jitter_minutes)
    if chosen == "cron":
        return cron_install(hour, minute, jitter_minutes)
    raise ScheduleError("Unknown scheduler backend: " + chosen)


def remove(backend: str = "auto") -> bool:
    if is_windows():
        return windows_remove()
    removed = False
    if shutil.which("systemctl"):
        removed = systemd_remove() or removed
    if cron_available():
        removed = cron_remove() or removed
    return removed


def status() -> ScheduleStatus:
    if is_windows():
        return windows_status()
    if shutil.which("systemctl"):
        found = systemd_status()
        if found.installed:
            return found
    if cron_available():
        return cron_status()
    return ScheduleStatus(False, "none")
