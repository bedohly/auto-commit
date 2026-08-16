"""Scheduler tests. Nothing here installs a real task or cron entry."""

import os
import sys
import unittest

from autocommit import schedule


class CommandTests(unittest.TestCase):
    def test_launch_command_runs_today_quietly(self):
        command = schedule.launch_command()
        self.assertIn("run", command)
        self.assertIn("--today", command)
        self.assertIn("--quiet", command)
        self.assertNotIn("--jitter", command)

    def test_launch_command_carries_jitter(self):
        command = schedule.launch_command(45)
        self.assertIn("--jitter", command)
        self.assertIn("45", command)

    def test_command_string_quotes_paths_with_spaces(self):
        quoted = schedule._quote("C:/Program Files/python.exe")
        self.assertTrue(quoted.startswith('"') and quoted.endswith('"'))
        self.assertEqual(schedule._quote("autocommit"), "autocommit")


class CronTests(unittest.TestCase):
    def test_cron_line_shape(self):
        line = schedule.cron_line(20, 30, 60)
        self.assertTrue(line.startswith("30 20 * * * "))
        self.assertIn(schedule.CRON_MARKER, line)
        self.assertIn("--jitter 60", line)

    def test_strip_marker_keeps_other_entries(self):
        content = "\n".join([
            "0 1 * * * /usr/bin/backup",
            "30 20 * * * autocommit run # autocommit",
            "@reboot /usr/bin/something",
        ])
        stripped = schedule.strip_marker(content)
        self.assertNotIn("autocommit", stripped)
        self.assertIn("/usr/bin/backup", stripped)
        self.assertIn("@reboot", stripped)

    def test_strip_marker_on_empty_input(self):
        self.assertEqual(schedule.strip_marker(""), "")


class SystemdTests(unittest.TestCase):
    def test_units_contain_the_expected_directives(self):
        service, timer = schedule.systemd_units(21, 5, 30)
        self.assertIn("[Service]", service)
        self.assertIn("Type=oneshot", service)
        self.assertIn("ExecStart=", service)
        self.assertIn("OnCalendar=*-*-* 21:05:00", timer)
        self.assertIn("RandomizedDelaySec=1800", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("WantedBy=timers.target", timer)

    def test_home_override_is_propagated(self):
        os.environ["AUTOCOMMIT_HOME"] = "/tmp/ac-home"
        try:
            service, _ = schedule.systemd_units(9, 0, 0)
            self.assertIn("Environment=AUTOCOMMIT_HOME=/tmp/ac-home", service)
        finally:
            os.environ.pop("AUTOCOMMIT_HOME", None)


class OutputDecodingTests(unittest.TestCase):
    """schtasks and friends answer in the local OEM codepage, not UTF-8."""

    def test_undecodable_output_does_not_raise(self):
        script = "import sys; sys.stdout.buffer.write(b'\\x8d\\xff done')"
        result = schedule._run([sys.executable, "-c", script], check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("done", result.stdout)


class DispatchTests(unittest.TestCase):
    def test_backend_choice_matches_the_platform(self):
        if os.name == "nt":
            self.assertEqual(schedule.pick_backend(), "schtasks")
        else:
            self.assertIn(schedule.pick_backend("cron"), ("cron", "systemd"))

    def test_explicit_backend_is_respected(self):
        self.assertEqual(schedule.pick_backend("systemd"), "systemd")

    def test_invalid_times_are_rejected(self):
        for hour, minute in ((24, 0), (-1, 0), (10, 60), (10, -5)):
            with self.assertRaises(schedule.ScheduleError):
                schedule.install(hour, minute)


if __name__ == "__main__":
    unittest.main()
