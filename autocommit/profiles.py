"""Ready-made settings bundles, so nobody has to tune eleven numbers by hand.

Each profile is a plain dict of Settings fields. The ones with a `ramp_days`
value start quiet and grow into their configured rate over that many days,
which is both gentler on the API and closer to how a real week of work looks
than jumping straight to the full rate on day one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

DEFAULT_PROFILE = "starter"


@dataclass
class Profile:
    name: str
    summary: str
    detail: str
    values: dict

    def rate_line(self) -> str:
        values = self.values
        return "{0}-{1} commits/day, {2:.0%} of weekdays, {3:.0%} of weekends".format(
            values["min_commits"], values["max_commits"],
            values["weekday_active_chance"], values["weekend_active_chance"],
        )


PROFILES = [
    Profile(
        name="starter",
        summary="Quiet. Starts near nothing and grows over a month.",
        detail="The gentlest option and the default. A day or two of commits a "
               "week to begin with, working up to its full rate across 30 days. "
               "No issues or pull requests.",
        values=dict(
            min_commits=1, max_commits=2,
            weekday_active_chance=0.45, weekend_active_chance=0.15,
            active_hour_start=10, active_hour_end=22,
            message_style="mixed",
            ramp_days=30,
            activity_enabled=False,
        ),
    ),
    Profile(
        name="casual",
        summary="A few commits on most weekdays.",
        detail="What a side project looks like. Reaches its full rate in two "
               "weeks. Still no issues or pull requests.",
        values=dict(
            min_commits=1, max_commits=3,
            weekday_active_chance=0.60, weekend_active_chance=0.25,
            active_hour_start=9, active_hour_end=23,
            message_style="mixed",
            ramp_days=14,
            activity_enabled=False,
        ),
    ),
    Profile(
        name="steady",
        summary="Most days covered, with the odd issue and pull request.",
        detail="Turns on the issue and pull request round at a low rate, so "
               "roughly one in four days gets one. Reaches full rate in a week.",
        values=dict(
            min_commits=1, max_commits=4,
            weekday_active_chance=0.80, weekend_active_chance=0.40,
            active_hour_start=9, active_hour_end=23,
            message_style="mixed",
            ramp_days=7,
            activity_enabled=True, activity_chance=0.25,
            issues_min=0, issues_max=1,
            pulls_min=0, pulls_max=1,
        ),
    ),
    Profile(
        name="heavy",
        summary="Everything, every day, straight away. Hard to miss.",
        detail="No ramp and no quiet days to speak of. A graph this uniform is "
               "the obvious kind; pick it only if you do not care who notices.",
        values=dict(
            min_commits=2, max_commits=8,
            weekday_active_chance=0.95, weekend_active_chance=0.80,
            active_hour_start=8, active_hour_end=24,
            message_style="mixed",
            ramp_days=0,
            activity_enabled=True, activity_chance=0.60,
            issues_min=0, issues_max=2,
            pulls_min=0, pulls_max=2,
        ),
    ),
]

BY_NAME = {profile.name: profile for profile in PROFILES}
NAMES = [profile.name for profile in PROFILES]


def get(name: str) -> Profile:
    key = (name or "").strip().lower()
    if key not in BY_NAME:
        raise ValueError(
            "Unknown profile '{0}'. Choose one of: {1}".format(name, ", ".join(NAMES))
        )
    return BY_NAME[key]


def apply(settings, name: str, today: "date | None" = None):
    """Copy a profile onto `settings` and restart its ramp from today."""
    profile = get(name)
    for key, value in profile.values.items():
        setattr(settings, key, value)
    settings.profile = profile.name
    settings.started_on = (today or date.today()).isoformat()
    settings.validate()
    return settings


def matches(settings) -> str:
    """Name of the profile whose values `settings` still carries, if any."""
    for profile in PROFILES:
        if all(getattr(settings, key) == value for key, value in profile.values.items()):
            return profile.name
    return ""


def describe(settings) -> str:
    """What to call the current settings: a profile name, or how they differ."""
    exact = matches(settings)
    if exact:
        return exact
    if settings.profile:
        return settings.profile + " (edited)"
    return "custom"
