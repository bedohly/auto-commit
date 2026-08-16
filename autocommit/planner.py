"""Turns settings plus a date range into a concrete list of commits."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from autocommit import messages
from autocommit.config import Settings

SATURDAY = 5


@dataclass
class PlannedCommit:
    when: datetime
    message: str

    @property
    def day(self) -> date:
        return self.when.date()


@dataclass
class DaySummary:
    day: date
    count: int


def daterange(start: date, end: date):
    if end < start:
        raise ValueError("The end date cannot be before the start date.")
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def is_weekend(day: date) -> bool:
    return day.weekday() >= SATURDAY


RAMP_FLOOR = 0.35


def ramp_factor(day: date, settings: Settings) -> float:
    """How far into its ramp a day sits, from 0.0 on day one to 1.0 at the end.

    Returns 1.0 when no ramp is configured, which is the case for every
    hand-tuned setup and for profiles that do not use one.
    """
    if settings.ramp_days <= 0 or not settings.started_on:
        return 1.0
    try:
        start = datetime.strptime(settings.started_on, "%Y-%m-%d").date()
    except ValueError:
        return 1.0
    elapsed = (day - start).days
    if elapsed <= 0:
        return 0.0
    return min(1.0, float(elapsed) / settings.ramp_days)


def effective_limits(day: date, settings: Settings):
    """(max commits, weekday chance, weekend chance) for one day of the ramp."""
    factor = ramp_factor(day, settings)
    if factor >= 1.0:
        return (settings.max_commits,
                settings.weekday_active_chance,
                settings.weekend_active_chance)
    span = settings.max_commits - settings.min_commits
    top = settings.min_commits + int(round(span * factor))
    scale = RAMP_FLOOR + (1.0 - RAMP_FLOOR) * factor
    return (max(settings.min_commits, top),
            settings.weekday_active_chance * scale,
            settings.weekend_active_chance * scale)


def commits_for_day(day: date, settings: Settings, rng: random.Random) -> int:
    """Decide how many commits a single day gets (0 means a rest day)."""
    high, weekday_chance, weekend_chance = effective_limits(day, settings)
    chance = weekend_chance if is_weekend(day) else weekday_chance
    if rng.random() >= chance:
        return 0
    low = settings.min_commits
    if high <= low:
        return low
    # Triangular keeps most days near the low end, which looks far more
    # natural than a flat distribution across the range.
    value = int(round(rng.triangular(low, high, low)))
    return max(low, min(high, value))


def _times_for_day(day: date, count: int, settings: Settings, rng: random.Random):
    """Pick `count` distinct minute-resolution times inside the active window."""
    start_minute = settings.active_hour_start * 60
    end_minute = settings.active_hour_end * 60 - 1
    span = end_minute - start_minute + 1
    if count >= span:
        chosen = list(range(start_minute, start_minute + min(count, span)))
    else:
        chosen = rng.sample(range(start_minute, end_minute + 1), count)
    chosen.sort()
    stamps = []
    for minute in chosen:
        stamps.append(
            datetime.combine(day, time(hour=minute // 60, minute=minute % 60, second=rng.randrange(60)))
        )
    return stamps


def build_plan(start: date, end: date, settings: Settings, rng: "random.Random | None" = None):
    """Return the chronologically ordered commits to create for [start, end]."""
    settings.validate()
    rng = rng or random.Random()
    plan = []
    for day in daterange(start, end):
        count = commits_for_day(day, settings, rng)
        if not count:
            continue
        for stamp in _times_for_day(day, count, settings, rng):
            plan.append(PlannedCommit(when=stamp, message=messages.build(rng, settings.message_style)))
    plan.sort(key=lambda item: item.when)
    return plan


def summarize(plan):
    """Group a plan into per-day counts, preserving chronological order."""
    summary = []
    for item in plan:
        if summary and summary[-1].day == item.day:
            summary[-1].count += 1
        else:
            summary.append(DaySummary(day=item.day, count=1))
    return summary
