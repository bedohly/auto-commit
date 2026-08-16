"""Console and rendering tests. No terminal and no network required."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

from autocommit import config, console, paths, ui
from autocommit.config import RepoTarget, Settings


@contextmanager
def captured():
    """Capture stdout and stderr together; ui.fail() writes to stderr."""
    buffer = io.StringIO()
    previous_out, previous_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = buffer
    try:
        yield buffer
    finally:
        sys.stdout, sys.stderr = previous_out, previous_err


class TempHome(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="autocommit-console-")
        self._previous = os.environ.get(paths.HOME_ENV)
        os.environ[paths.HOME_ENV] = self.home
        os.environ["AUTOCOMMIT_NO_COLOR"] = "1"
        ui.reset_glyph_cache()

    def tearDown(self):
        if self._previous is None:
            os.environ.pop(paths.HOME_ENV, None)
        else:
            os.environ[paths.HOME_ENV] = self._previous
        os.environ.pop("AUTOCOMMIT_NO_COLOR", None)
        ui.reset_glyph_cache()
        paths.remove_tree(self.home)


class RenderingTests(unittest.TestCase):
    def setUp(self):
        os.environ["AUTOCOMMIT_NO_COLOR"] = "1"
        ui.reset_glyph_cache()

    def tearDown(self):
        os.environ.pop("AUTOCOMMIT_NO_COLOR", None)
        os.environ.pop("AUTOCOMMIT_ASCII", None)
        ui.reset_glyph_cache()

    def test_box_borders_line_up(self):
        with captured() as out:
            ui.box_title("AUTOCOMMIT", "v9.9.9")
        lines = [line for line in out.getvalue().split("\n") if line.strip()]
        self.assertEqual(len(lines), 3)
        self.assertEqual(len({len(line) for line in lines}), 1)
        self.assertIn("AUTOCOMMIT", lines[1])
        self.assertIn("v9.9.9", lines[1])

    def test_overlong_title_drops_the_tag_instead_of_overflowing(self):
        with captured() as out:
            ui.box_title("X" * 200, "v9.9.9")
        lines = [line for line in out.getvalue().split("\n") if line.strip()]
        self.assertEqual(len(lines), 3)
        self.assertGreaterEqual(len(lines[1]), len(lines[0]))

    def test_ascii_fallback_can_be_forced(self):
        os.environ["AUTOCOMMIT_ASCII"] = "1"
        ui.reset_glyph_cache()
        self.assertFalse(ui.supports_unicode())
        self.assertEqual(ui.glyphs(), ui.ASCII_GLYPHS)
        with captured() as out:
            ui.box_title("TITLE")
        self.assertNotIn("╭", out.getvalue())
        self.assertIn("+", out.getvalue())

    def test_glyph_sets_have_the_same_keys(self):
        self.assertEqual(set(ui.UNICODE_GLYPHS), set(ui.ASCII_GLYPHS))

    def test_visible_length_ignores_ansi(self):
        self.assertEqual(ui.visible_length("\033[31mred\033[0m"), 3)
        self.assertEqual(ui.visible_length("plain"), 5)

    def test_width_is_clamped(self):
        self.assertGreaterEqual(ui.width(), 56)
        self.assertLessEqual(ui.width(), 84)

    def test_field_and_bullet_render(self):
        with captured() as out:
            ui.field("account", "octocat", "ok")
            ui.field("plain", "no dot")
            ui.bullet("something happened", "warn")
        text = out.getvalue()
        self.assertIn("account", text)
        self.assertIn("octocat", text)
        self.assertIn("no dot", text)
        self.assertIn("something happened", text)


class DispatchTests(TempHome):
    def setUp(self):
        super().setUp()
        self.console = console.Console()

    def test_every_command_has_a_unique_name_and_usage(self):
        names = self.console.names
        self.assertEqual(len(names), len(set(names)))
        for command in self.console.commands:
            self.assertTrue(command.usage.startswith("/" + command.name))
            self.assertTrue(command.summary.endswith("."))

    def test_help_lists_all_commands(self):
        with captured() as out:
            self.console.execute("/help")
        text = out.getvalue()
        for name in self.console.names:
            self.assertIn("/" + name, text)

    def test_slash_is_optional(self):
        with captured() as bare:
            self.console.execute("help")
        with captured() as slashed:
            self.console.execute("/help")
        self.assertEqual(bare.getvalue(), slashed.getvalue())

    def test_aliases_resolve(self):
        for alias, target in (("/h", "help"), ("/?", "help"), ("/st", "status"),
                              ("/cls", "clear"), ("/q", "quit")):
            self.assertIs(self.console._index[alias.lstrip("/")],
                          self.console._index[target])

    def test_unknown_command_suggests_a_close_match(self):
        with captured() as out:
            self.console.execute("/statu")
        text = out.getvalue()
        self.assertIn("Unknown command", text)
        self.assertIn("/status", text)

    def test_unknown_command_without_a_match_points_at_help(self):
        with captured() as out:
            self.console.execute("/zzzzzz")
        self.assertIn("/help", out.getvalue())

    def test_blank_lines_are_ignored(self):
        with captured() as out:
            self.console.execute("")
            self.console.execute("   ")
            self.console.execute("/")
        self.assertEqual(out.getvalue(), "")

    def test_quit_stops_the_loop(self):
        with captured():
            still_running = self.console.execute("/quit")
        self.assertFalse(still_running)
        self.assertFalse(self.console.running)

    def test_quoted_arguments_survive(self):
        captured_args = []
        self.console._index["set"].handler = lambda args: captured_args.extend(args)
        with captured():
            self.console.execute('/set author_name "The Octocat"')
        self.assertEqual(captured_args, ["author_name", "The Octocat"])

    def test_unbalanced_quotes_do_not_crash(self):
        with captured() as out:
            self.console.execute('/set author_name "unclosed')
        self.assertNotIn("Traceback", out.getvalue())

    def test_errors_are_reported_not_raised(self):
        with captured() as out:
            self.console.execute("/run 0")          # invalid day count
            self.console.execute("/set nope 1")     # unknown setting
            self.console.execute("/new")            # missing argument
        text = out.getvalue()
        self.assertNotIn("Traceback", text)
        self.assertIn("at least 1", text)
        self.assertIn("Unknown setting", text)
        self.assertIn("Usage", text)


class StatusTests(TempHome):
    def _settings(self):
        return Settings(
            account="octocat",
            author_name="The Octocat",
            author_email="1+octocat@users.noreply.github.com",
            repo=RepoTarget(owner="octocat", name="activity-log", branch="main"),
        )

    def test_status_without_configuration(self):
        with mock.patch("autocommit.auth.resolve", return_value=None):
            with captured() as out:
                console.render_status()
        text = out.getvalue()
        self.assertIn("not signed in", text)
        self.assertIn("none selected", text)
        self.assertIn("never", text)

    def test_status_with_a_configured_repository(self):
        config.save(self._settings())
        with mock.patch("autocommit.auth.resolve", return_value=None):
            with captured() as out:
                console.render_status()
        text = out.getvalue()
        self.assertIn("octocat/activity-log", text)
        self.assertIn("branch main", text)
        self.assertIn("1+octocat@users.noreply.github.com", text)

    def test_status_reads_the_last_run(self):
        config.save(self._settings())
        paths.ensure_dir(paths.log_file().parent)
        paths.log_file().write_text(
            "2026-08-16T14:30:00\toctocat/activity-log\tcommits=24\tdays=10\tpushed=yes\n",
            encoding="utf-8")
        with mock.patch("autocommit.auth.resolve", return_value=None):
            with captured() as out:
                console.render_status()
        self.assertIn("2026-08-16 14:30", out.getvalue())
        self.assertIn("commits 24", out.getvalue())

    def test_log_command_without_history(self):
        with captured() as out:
            console.Console().execute("/log")
        self.assertIn("No runs recorded yet", out.getvalue())

    def test_log_command_shows_recent_entries(self):
        paths.ensure_dir(paths.log_file().parent)
        rows = "".join(
            "2026-08-{0:02d}T10:00:00\toctocat/log\tcommits={0}\tdays=1\tpushed=yes\n".format(day)
            for day in range(1, 13)
        )
        paths.log_file().write_text(rows, encoding="utf-8")
        with captured() as out:
            console.Console().execute("/log 3")
        text = out.getvalue()
        self.assertIn("2026-08-12", text)
        self.assertNotIn("2026-08-01", text)


class SettingsCommandTests(TempHome):
    def setUp(self):
        super().setUp()
        config.save(Settings(account="octocat",
                             repo=RepoTarget(owner="octocat", name="log", branch="main")))
        self.console = console.Console()

    def test_set_updates_and_persists(self):
        with captured():
            self.console.execute("/set max_commits 9")
        self.assertEqual(config.load().max_commits, 9)

    def test_set_accepts_a_float(self):
        with captured():
            self.console.execute("/set weekend_active_chance 0.2")
        self.assertAlmostEqual(config.load().weekend_active_chance, 0.2)

    def test_set_rejects_a_bad_value_and_keeps_the_old_one(self):
        before = config.load().max_commits
        with captured() as out:
            self.console.execute("/set max_commits banana")
        self.assertIn("whole number", out.getvalue())
        self.assertEqual(config.load().max_commits, before)

    def test_set_rolls_back_when_validation_fails(self):
        with captured() as out:
            self.console.execute("/set min_commits 50")   # would exceed max_commits
        self.assertIn("greater than or equal", out.getvalue())
        self.assertEqual(config.load().min_commits, 1)

    def test_set_refuses_non_editable_fields(self):
        with captured() as out:
            self.console.execute("/set account someone-else")
        self.assertIn("Unknown setting", out.getvalue())
        self.assertEqual(config.load().account, "octocat")

    def test_plan_previews_without_committing(self):
        with captured() as out:
            self.console.execute("/plan 7")
        text = out.getvalue()
        self.assertIn("PLAN", text)
        self.assertIn("preview", text.lower())
        self.assertFalse(paths.repos_dir().exists())


if __name__ == "__main__":
    unittest.main()
