import random
import unittest
from datetime import date

from autocommit import planner
from autocommit.config import Settings


def settings(**overrides):
    base = Settings(
        account="tester",
        author_name="Tester",
        author_email="tester@example.com",
        min_commits=1,
        max_commits=5,
        weekday_active_chance=1.0,
        weekend_active_chance=1.0,
        active_hour_start=9,
        active_hour_end=18,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


class PlannerTests(unittest.TestCase):
    def test_plan_is_deterministic_for_a_seed(self):
        start, end = date(2026, 3, 1), date(2026, 3, 21)
        first = planner.build_plan(start, end, settings(), random.Random(7))
        second = planner.build_plan(start, end, settings(), random.Random(7))
        self.assertEqual(
            [(item.when, item.message) for item in first],
            [(item.when, item.message) for item in second],
        )
        self.assertNotEqual(first, [])

    def test_commit_counts_stay_within_bounds(self):
        cfg = settings(min_commits=2, max_commits=4)
        plan = planner.build_plan(date(2026, 1, 1), date(2026, 2, 15), cfg, random.Random(3))
        for day in planner.summarize(plan):
            self.assertGreaterEqual(day.count, 2)
            self.assertLessEqual(day.count, 4)

    def test_times_stay_inside_the_active_window(self):
        cfg = settings(active_hour_start=10, active_hour_end=14, max_commits=8)
        plan = planner.build_plan(date(2026, 5, 1), date(2026, 5, 30), cfg, random.Random(11))
        self.assertTrue(plan)
        for item in plan:
            self.assertGreaterEqual(item.when.hour, 10)
            self.assertLess(item.when.hour, 14)

    def test_plan_is_chronological_with_unique_timestamps(self):
        plan = planner.build_plan(date(2026, 4, 1), date(2026, 4, 30), settings(max_commits=6),
                                  random.Random(5))
        stamps = [item.when for item in plan]
        self.assertEqual(stamps, sorted(stamps))
        minutes = [(item.when.date(), item.when.hour, item.when.minute) for item in plan]
        self.assertEqual(len(minutes), len(set(minutes)))

    def test_zero_chance_produces_no_commits(self):
        cfg = settings(weekday_active_chance=0.0, weekend_active_chance=0.0)
        plan = planner.build_plan(date(2026, 6, 1), date(2026, 6, 30), cfg, random.Random(1))
        self.assertEqual(plan, [])

    def test_rest_days_appear_when_chance_is_partial(self):
        cfg = settings(weekday_active_chance=0.5, weekend_active_chance=0.1)
        plan = planner.build_plan(date(2026, 1, 1), date(2026, 12, 31), cfg, random.Random(2))
        active_days = len(planner.summarize(plan))
        self.assertGreater(active_days, 0)
        self.assertLess(active_days, 365)

    def test_weekend_detection(self):
        self.assertTrue(planner.is_weekend(date(2026, 8, 15)))   # Saturday
        self.assertTrue(planner.is_weekend(date(2026, 8, 16)))   # Sunday
        self.assertFalse(planner.is_weekend(date(2026, 8, 17)))  # Monday

    def test_more_commits_than_minutes_available_is_capped(self):
        cfg = settings(active_hour_start=9, active_hour_end=10, min_commits=90, max_commits=90)
        plan = planner.build_plan(date(2026, 2, 2), date(2026, 2, 2), cfg, random.Random(4))
        self.assertEqual(len(plan), 60)

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(ValueError):
            planner.build_plan(date(2026, 3, 10), date(2026, 3, 1), settings(), random.Random(0))

    def test_summarize_groups_by_day(self):
        cfg = settings(min_commits=3, max_commits=3)
        plan = planner.build_plan(date(2026, 7, 1), date(2026, 7, 3), cfg, random.Random(9))
        summary = planner.summarize(plan)
        self.assertEqual([day.count for day in summary], [3, 3, 3])
        self.assertEqual([day.day.day for day in summary], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
