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

# --------------------------------------------------------------------------
# Issue / pull request / review copy
# --------------------------------------------------------------------------
ISSUE_TITLES = [
    "Tidy up the activity log format",
    "Add a short header to the log file",
    "Trim entries older than the current month",
    "Document how the log is generated",
    "Normalize spacing in the log",
    "Group log entries by week",
    "Shorten the timestamp format",
    "Review the log for duplicate lines",
    "Sort the entries consistently",
    "Note the timezone used in the log",
]

ISSUE_BODIES = [
    "The file has grown a bit; worth a pass to keep it readable.",
    "Small housekeeping item, no rush.",
    "Noticed this while skimming the log. Filing so it is not forgotten.",
    "Would make the file easier to scan.",
    "Low priority, but easy to fix.",
]

PULL_TITLES = [
    "Tidy the activity log",
    "Housekeeping pass over the log",
    "Small formatting cleanup",
    "Refresh the log entries",
    "Keep the log consistent",
    "Minor log maintenance",
    "Clean up recent entries",
]

PULL_BODIES = [
    "A few small edits to keep the log tidy.",
    "Routine housekeeping. Nothing behavioural.",
    "Formatting only; no functional change.",
    "Keeping the entries consistent with the rest of the file.",
]

REVIEW_BODIES = [
    "Looks fine to me.",
    "Reads well, nothing blocking.",
    "Small and self-contained. Good to go.",
    "No concerns here.",
    "Straightforward change.",
]

BRANCH_WORDS = [
    "tidy", "cleanup", "housekeeping", "polish", "refresh",
    "format", "notes", "maintenance", "sweep", "touchup",
]


def issue(rng):
    """Return a (title, body) pair for a new issue."""
    return rng.choice(ISSUE_TITLES), rng.choice(ISSUE_BODIES)


def pull(rng):
    """Return a (title, body) pair for a new pull request."""
    return rng.choice(PULL_TITLES), rng.choice(PULL_BODIES)


def review(rng) -> str:
    return rng.choice(REVIEW_BODIES)


def branch_name(rng, stamp: str, index: int) -> str:
    """A branch name that is obviously machine-made and easy to clean up."""
    return "autocommit/{0}-{1}-{2}".format(rng.choice(BRANCH_WORDS), stamp, index)


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
