"""Small terminal helpers: colors, prompts and menus. All output is English."""

from __future__ import annotations

import os
import sys

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}


def _enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        for handle_id in (-11, -12):  # stdout, stderr
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:  # pragma: no cover - cosmetic only
        pass


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("AUTOCOMMIT_NO_COLOR"):
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


_enable_windows_ansi()


def paint(text: str, *styles: str) -> str:
    if not styles or not color_enabled():
        return text
    prefix = "".join(_ANSI.get(style, "") for style in styles)
    return "{0}{1}{2}".format(prefix, text, _ANSI["reset"])


def say(text: str = "") -> None:
    print(text)


def info(text: str) -> None:
    print("{0} {1}".format(paint("::", "blue"), text))


def ok(text: str) -> None:
    print("{0} {1}".format(paint("OK", "green", "bold"), text))


def warn(text: str) -> None:
    print("{0} {1}".format(paint("!!", "yellow", "bold"), text))


def fail(text: str) -> None:
    print("{0} {1}".format(paint("XX", "red", "bold"), text), file=sys.stderr)


def hint(text: str) -> None:
    print(paint("   " + text, "grey"))


def banner(title: str, subtitle: str = "") -> None:
    line = "=" * 52
    print()
    print(paint(line, "magenta"))
    print(paint("  " + title, "magenta", "bold"))
    if subtitle:
        print(paint("  " + subtitle, "grey"))
    print(paint(line, "magenta"))


def rule(label: str = "") -> None:
    if label:
        print(paint("-- {0} ".format(label).ljust(52, "-"), "grey"))
    else:
        print(paint("-" * 52, "grey"))


def is_interactive() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def ask(question: str, default: str = "") -> str:
    suffix = " [{0}]".format(default) if default else ""
    try:
        raw = input("{0}{1}: ".format(question, suffix)).strip()
    except EOFError:
        return default
    return raw or default


def ask_int(question: str, default: int, minimum: int = 0, maximum: int = 10 ** 6) -> int:
    while True:
        raw = ask(question, str(default))
        try:
            value = int(raw)
        except ValueError:
            warn("Enter a whole number.")
            continue
        if value < minimum or value > maximum:
            warn("Enter a number between {0} and {1}.".format(minimum, maximum))
            continue
        return value


def ask_float(question: str, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    while True:
        raw = ask(question, str(default))
        try:
            value = float(raw)
        except ValueError:
            warn("Enter a number.")
            continue
        if value < minimum or value > maximum:
            warn("Enter a value between {0} and {1}.".format(minimum, maximum))
            continue
        return value


def confirm(question: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            raw = input("{0} {1} ".format(question, suffix)).strip().lower()
        except EOFError:
            return default
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        warn("Please answer 'y' or 'n'.")


def choose(title: str, options, allow_back: bool = True):
    """Render a numbered menu and return the index of the chosen entry.

    Returns None when the user picks the 'back / cancel' entry.
    """
    print()
    print(paint(title, "bold"))
    for index, option in enumerate(options, start=1):
        print("  {0:>2}) {1}".format(index, option))
    if allow_back:
        print("  {0:>2}) {1}".format(0, "Back"))
    while True:
        raw = ask("Choice")
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            warn("Enter one of the listed numbers.")
            continue
        if allow_back and value == 0:
            return None
        if 1 <= value <= len(options):
            return value - 1
        warn("Enter one of the listed numbers.")
