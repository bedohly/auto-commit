"""Profiles and the ramp that eases a new setup into its configured rate."""

import random
import unittest
from datetime import date, timedelta

from autocommit import planner, profiles
from autocommit.config import Settings


class ProfileTests(unittest.TestCase):
    def test_every_profile_is_valid(self):
        for name in profiles.NAMES:
            settings = profiles.apply(Settings(), name, date(2026, 1, 1))
            settings.validate()
            self.assertEqual(settings.profile, name)
            self.assertEqual(settings.started_on, "2026-01-01")

    def test_profiles_are_ordered_from_quiet_to_loud(self):
        rates = []
        for name in profiles.NAMES:
            values = profiles.get(name).values
            rates.append(values["max_commits"] * values["weekday_active_chance"])
        self.assertEqual(rates, sorted(rates))

    def test_the_default_settings_are_the_starter_profile(self):
        self.assertEqual(profiles.matches(Settings()), profiles.DEFAULT_PROFILE)
        self.assertEqual(Settings().profile, profiles.DEFAULT_PROFILE)

    def test_starter_is_the_quietest_and_ramps(self):
        starter = profiles.get("starter").values
        self.assertEqual(starter["ramp_days"], 30)
        self.assertFalse(starter["activity_enabled"])
        for name in ("casual", "steady", "heavy"):
            other = profiles.get(name).values
            self.assertGreaterEqual(other["max_commits"], starter["max_commits"])

    def test_only_the_loudest_profile_skips_the_ramp(self):
        self.assertEqual(profiles.get("heavy").values["ramp_days"], 0)
        for name in ("starter", "casual", "steady"):
            self.assertGreater(profiles.get(name).values["ramp_days"], 0)

    def test_applying_a_profile_restarts_the_ramp(self):
        settings = profiles.apply(Settings(), "casual", date(2026, 1, 1))
        profiles.apply(settings, "steady", date(2026, 6, 1))
        self.assertEqual(settings.started_on, "2026-06-01")
        self.assertEqual(settings.ramp_days, 7)

    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            profiles.get("turbo")
        self.assertIn("starter", str(caught.exception))

    def test_describe_reports_edits(self):
        settings = profiles.apply(Settings(), "casual", date(2026, 1, 1))
        self.assertEqual(profiles.describe(settings), "casual")
        settings.max_commits += 5
        self.assertEqual(profiles.describe(settings), "casual (edited)")
        blank = Settings(profile="")
        blank.max_commits = 99
        self.assertEqual(profiles.describe(blank), "custom")

    def test_rate_line_is_readable(self):
        line = profiles.get("starter").rate_line()
        self.assertIn("1-2 commits/day", line)
        self.assertIn("45% of weekdays", line)


class RampTests(unittest.TestCase):
    def _settings(self, **overrides):
        settings = profiles.apply(Settings(), "starter", date(2026, 1, 1))
        for key, value in overrides.items():
            setattr(settings, key, value)
        return settings

    def test_factor_grows_from_zero_to_one(self):
        settings = self._settings()
        start = date(2026, 1, 1)
        self.assertEqual(planner.ramp_factor(start, settings), 0.0)
        self.assertAlmostEqual(planner.ramp_factor(start + timedelta(days=15), settings), 0.5)
        self.assertEqual(planner.ramp_factor(start + timedelta(days=30), settings), 1.0)
        self.assertEqual(planner.ramp_factor(start + timedelta(days=90), settings), 1.0)

    def test_days_before_the_start_are_at_the_floor(self):
        settings = self._settings()
        self.assertEqual(planner.ramp_factor(date(2025, 12, 1), settings), 0.0)

    def test_no_ramp_configured_means_full_rate(self):
        settings = self._settings(ramp_days=0)
        self.assertEqual(planner.ramp_factor(date(2026, 1, 1), settings), 1.0)
        settings = self._settings(started_on="")
        self.assertEqual(planner.ramp_factor(date(2026, 1, 1), settings), 1.0)

    def test_a_corrupt_start_date_does_not_break_planning(self):
        settings = self._settings()
        settings.started_on = "not-a-date"
        self.assertEqual(planner.ramp_factor(date(2026, 1, 1), settings), 1.0)

    def test_limits_grow_with_the_ramp(self):
        settings = self._settings(min_commits=1, max_commits=6)
        start = date(2026, 1, 1)
        first, first_weekday, _ = planner.effective_limits(start, settings)
        mid, mid_weekday, _ = planner.effective_limits(start + timedelta(days=15), settings)
        last, last_weekday, _ = planner.effective_limits(start + timedelta(days=30), settings)
        self.assertEqual(first, 1)
        self.assertGreater(mid, first)
        self.assertEqual(last, 6)
        self.assertLess(first_weekday, mid_weekday)
        self.assertLess(mid_weekday, last_weekday)
        self.assertAlmostEqual(last_weekday, settings.weekday_active_chance)

    def test_the_floor_never_reaches_zero(self):
        settings = self._settings()
        _, weekday, weekend = planner.effective_limits(date(2026, 1, 1), settings)
        self.assertGreater(weekday, 0)
        self.assertGreater(weekend, 0)

    def test_early_weeks_are_quieter_than_later_weeks(self):
        settings = self._settings()
        start = date(2026, 1, 1)
        rng = random.Random(4)
        first_month = planner.build_plan(start, start + timedelta(days=29), settings, rng)
        later = planner.build_plan(start + timedelta(days=60),
                                   start + timedelta(days=89), settings, random.Random(4))
        self.assertLess(len(first_month), len(later))

    def test_the_first_week_is_the_quietest(self):
        settings = self._settings()
        start = date(2026, 1, 1)
        weeks = []
        for index in range(4):
            begin = start + timedelta(days=index * 7)
            weeks.append(len(planner.build_plan(begin, begin + timedelta(days=6),
                                                settings, random.Random(index + 1))))
        self.assertEqual(weeks[0], min(weeks))

    def test_a_ramped_plan_is_still_deterministic(self):
        settings = self._settings()
        first = planner.build_plan(date(2026, 1, 1), date(2026, 2, 15), settings,
                                   random.Random(8))
        second = planner.build_plan(date(2026, 1, 1), date(2026, 2, 15), settings,
                                    random.Random(8))
        self.assertEqual([item.when for item in first], [item.when for item in second])

    def test_heavy_profile_starts_at_full_rate(self):
        settings = profiles.apply(Settings(), "heavy", date(2026, 1, 1))
        top, weekday, _ = planner.effective_limits(date(2026, 1, 1), settings)
        self.assertEqual(top, settings.max_commits)
        self.assertAlmostEqual(weekday, settings.weekday_active_chance)


class RampCopyTests(unittest.TestCase):
    def test_ramp_line_wording(self):
        from autocommit import cli

        settings = profiles.apply(Settings(), "starter", date(2026, 1, 1))
        text = cli.ramp_line(settings, date(2026, 1, 11))
        self.assertIn("day 10 of 30", text)
        self.assertIn("33%", text)
        self.assertEqual(cli.ramp_line(settings, date(2026, 3, 1)), "full rate")

    def test_ramp_line_without_a_ramp(self):
        from autocommit import cli

        settings = profiles.apply(Settings(), "heavy", date(2026, 1, 1))
        self.assertEqual(cli.ramp_line(settings, date(2026, 1, 1)), "full rate")


if __name__ == "__main__":
    unittest.main()
