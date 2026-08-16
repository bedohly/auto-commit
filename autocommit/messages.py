"""Commit message pools."""

from __future__ import annotations

CASUAL = [
    "update notes",
    "small cleanup",
    "tweak wording",
    "fix typo",
    "refresh log",
    "reorder entries",
    "adjust formatting",
    "add a note",
    "minor edit",
    "polish wording",
    "clean up whitespace",
    "keep the log tidy",
    "record today's entry",
    "shorten a line",
    "rephrase a sentence",
    "drop a stale line",
    "sync notes",
    "housekeeping",
    "touch up the log",
    "another small pass",
]

SCOPES = ["log", "notes", "activity", "docs", "journal", "entries"]

CONVENTIONAL_TYPES = [
    ("chore", ["update {scope}", "tidy {scope}", "rotate {scope}"]),
    ("docs", ["clarify {scope}", "expand {scope}", "fix wording in {scope}"]),
    ("style", ["format {scope}", "normalize {scope} spacing"]),
    ("refactor", ["reorganize {scope}", "simplify {scope}"]),
    ("fix", ["correct {scope} entry", "repair {scope} ordering"]),
]

STYLES = ("casual", "conventional", "mixed")


def build(rng, style: str = "mixed") -> str:
    """Return one commit message using the requested style."""
    if style not in STYLES:
        style = "mixed"
    if style == "mixed":
        style = rng.choice(("casual", "conventional"))
    if style == "casual":
        return rng.choice(CASUAL)
    kind, templates = rng.choice(CONVENTIONAL_TYPES)
    scope = rng.choice(SCOPES)
    return "{0}: {1}".format(kind, rng.choice(templates).format(scope=scope))
