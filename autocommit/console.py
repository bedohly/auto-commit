"""The interactive console: a slash-command shell with a status panel.

Runs identically on Linux, macOS and Windows. Line editing and history come
from the stdlib `readline` module where it exists (Unix); on Windows the
console host provides its own. Nothing here needs a third-party package.
"""

from __future__ import annotations

import argparse
import difflib
import shlex
from datetime import date, timedelta

from autocommit import __version__, auth, cli, config, paths, runner, schedule, ui
from autocommit.github import GitHubClient, GitHubError
from autocommit.gitrepo import GitError, git_version

PROMPT_NAME = "autocommit"

try:  # pragma: no cover - depends on the platform
    import readline
except ImportError:  # pragma: no cover - Windows without pyreadline
    readline = None


class Command:
    def __init__(self, name, summary, usage, handler, aliases=()):
        self.name = name
        self.summary = summary
        self.usage = usage
        self.handler = handler
        self.aliases = tuple(aliases)


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _describe_schedule(state) -> str:
    if not state.installed:
        return "not installed"
    return "{0} ({1})".format(state.detail or "installed", state.backend)


def _last_run_line() -> str:
    path = paths.log_file()
    if not path.exists():
        return ""
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return ""
    if not lines:
        return ""
    parts = lines[-1].split("\t")
    stamp = parts[0].replace("T", " ")[:16]
    details = " ".join(part.replace("=", " ") for part in parts[2:])
    return "{0} {1} {2}".format(stamp, ui.glyphs()["mid"], details).strip()


def render_status(token: str = "") -> None:
    """The status panel, shared by the console and `autocommit status`."""
    settings = config.load()
    ui.box_title("AUTOCOMMIT", "v" + __version__)

    info = auth.resolve(token)
    if info:
        ui.field("account", "{0}  {1}".format(
            settings.account or "signed in", ui.paint("(" + info.source + ")", "grey")), "ok")
    else:
        ui.field("account", "not signed in  " + ui.paint("/login", "cyan"), "bad")

    if settings.repo.is_set():
        ui.field("repository", "{0}  {1}".format(
            settings.repo.full_name,
            ui.paint("branch " + settings.repo.branch, "grey")), "ok")
    else:
        ui.field("repository", "none selected  " + ui.paint("/select", "cyan"), "bad")

    ui.field("author", "{0} <{1}>".format(
        settings.author_name or "-", settings.author_email or "-"),
        "ok" if settings.author_email else "warn")

    mid = ui.glyphs()["mid"]
    ui.field("cadence", "{0}-{1} commits/day {2} weekdays {3:.0%} {2} weekends {4:.0%}".format(
        settings.min_commits, settings.max_commits, mid,
        settings.weekday_active_chance, settings.weekend_active_chance))
    ui.field("window", "{0:02d}:00-{1:02d}:00 local {2} {3}".format(
        settings.active_hour_start, settings.active_hour_end, mid, settings.commit_file))

    state = schedule.status()
    ui.field("schedule", _describe_schedule(state), "ok" if state.installed else "warn")

    last = _last_run_line()
    if last:
        ui.field("last run", last, "ok")
    else:
        ui.field("last run", "never")


class Console:
    """Reads slash commands and dispatches them. Testable line by line."""

    def __init__(self, token: str = ""):
        self.token = token
        self.running = True
        self.commands = []
        self._index = {}
        self._register_all()

    # -- registration -----------------------------------------------------
    def _register(self, name, summary, usage, handler, aliases=()):
        command = Command(name, summary, usage, handler, aliases)
        self.commands.append(command)
        self._index[name] = command
        for alias in aliases:
            self._index[alias] = command

    def _register_all(self):
        self._register("help", "List every command.", "/help", self.cmd_help, ("h", "?"))
        self._register("status", "Show the current setup at a glance.", "/status",
                       self.cmd_status, ("st",))
        self._register("check", "Verify token, repository and contribution rules.",
                       "/check", self.cmd_check, ("doctor",))
        self._register("setup", "Guided first-time setup, start to finish.", "/setup",
                       self.cmd_setup)
        self._register("login", "Sign in to GitHub and save a token.", "/login",
                       self.cmd_login)
        self._register("logout", "Forget the saved token.", "/logout", self.cmd_logout)
        self._register("repos", "List repositories you can push to.", "/repos",
                       self.cmd_repos)
        self._register("select", "Choose the target repository.", "/select [owner/repo]",
                       self.cmd_select, ("use",))
        self._register("new", "Create a repository and select it.",
                       "/new <name> [--public]", self.cmd_new)
        self._register("config", "Show every setting.", "/config", self.cmd_config,
                       ("settings",))
        self._register("set", "Change one setting.", "/set <key> <value>", self.cmd_set)
        self._register("plan", "Preview a plan without committing.", "/plan [days]",
                       self.cmd_plan, ("preview",))
        self._register("run", "Create the commits and push them.", "/run [days]",
                       self.cmd_run)
        self._register("schedule", "Install the daily run.", "/schedule [HH:MM] [jitter]",
                       self.cmd_schedule)
        self._register("unschedule", "Remove the daily run.", "/unschedule",
                       self.cmd_unschedule)
        self._register("log", "Show recent runs.", "/log [count]", self.cmd_log)
        self._register("clear", "Clear the screen.", "/clear", self.cmd_clear, ("cls",))
        self._register("quit", "Leave the console.", "/quit", self.cmd_quit,
                       ("exit", "q"))

    @property
    def names(self):
        return [command.name for command in self.commands]

    # -- dispatch ---------------------------------------------------------
    def execute(self, line: str) -> bool:
        """Run one input line. Returns False when the console should stop."""
        text = (line or "").strip()
        if not text:
            return self.running
        if text.startswith("/"):
            text = text[1:].strip()
        if not text:
            return self.running

        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        name, args = parts[0].lower(), parts[1:]

        command = self._index.get(name)
        if not command:
            ui.fail("Unknown command: /{0}".format(name))
            close = difflib.get_close_matches(name, list(self._index), n=1)
            if close:
                ui.hint("Did you mean /{0}?".format(close[0]))
            else:
                ui.hint("Type /help to see everything.")
            return self.running

        try:
            command.handler(args)
        except cli.CliError as exc:
            ui.fail(str(exc))
        except (GitHubError, GitError, schedule.ScheduleError, ValueError) as exc:
            ui.fail(str(exc))
        except KeyboardInterrupt:
            ui.say()
            ui.info("Cancelled.")
        return self.running

    # -- the loop ---------------------------------------------------------
    def _install_completer(self):  # pragma: no cover - needs a real terminal
        if readline is None:
            return
        options = ["/" + name for name in self._index]

        def complete(text, state):
            matches = [name for name in options if name.startswith(text)]
            return matches[state] if state < len(matches) else None

        try:
            readline.set_completer(complete)
            readline.set_completer_delims(" \t\n")
            if "libedit" in (getattr(readline, "__doc__", "") or ""):
                readline.parse_and_bind("bind ^I rl_complete")
            else:
                readline.parse_and_bind("tab: complete")
        except Exception:
            pass

    def loop(self) -> int:
        self._install_completer()
        ui.clear_screen()
        self.cmd_status([])
        ui.say()
        ui.hint("Type /help for commands, /setup to configure everything, /quit to leave.")

        prompt = "\n{0} {1} ".format(
            ui.paint(PROMPT_NAME, "magenta", "bold"), ui.paint(ui.glyphs()["arrow"], "grey")
        )
        while self.running:
            try:
                line = input(prompt)
            except EOFError:
                ui.say()
                break
            except KeyboardInterrupt:
                ui.say()
                ui.hint("Type /quit to leave.")
                continue
            self.execute(line)
        return 0

    # -- commands ---------------------------------------------------------
    def cmd_help(self, args):
        ui.box_title("COMMANDS", "autocommit " + __version__)
        for command in self.commands:
            aliases = ""
            if command.aliases:
                aliases = ui.paint("  (/{0})".format(", /".join(command.aliases)), "grey")
            print("  {0}{1}".format(ui.paint(command.usage.ljust(28), "cyan"), command.summary))
            if aliases:
                print("  {0}{1}".format(" " * 28, aliases.strip()))

    def cmd_status(self, args):
        render_status(self.token)

    def cmd_check(self, args):
        settings = config.load()
        ui.box_title("CHECKS")

        try:
            ui.bullet("git " + git_version().replace("git version ", ""), "ok")
        except GitError as exc:
            ui.bullet(str(exc), "bad")

        info = auth.resolve(self.token)
        if not info:
            ui.bullet("No token. Run /login.", "bad")
            return
        client = GitHubClient(info.value)
        try:
            user = client.whoami()
        except GitHubError as exc:
            ui.bullet(str(exc), "bad")
            return
        ui.bullet("Token valid, signed in as {0} (from {1}).".format(user.login, info.source), "ok")

        scopes = client.token_scopes()
        if auth.missing_scope(scopes):
            ui.bullet("Token scopes [{0}] cannot push.".format(", ".join(scopes)), "bad")
        elif scopes:
            ui.bullet("Token scopes: {0}.".format(", ".join(scopes)), "ok")
        else:
            ui.bullet("Fine-grained token: make sure it grants Contents: Read and write.", "warn")

        if not settings.repo.is_set():
            ui.bullet("No repository selected. Run /select.", "bad")
            return
        try:
            repo = client.get_repo(settings.repo.owner, settings.repo.name)
        except GitHubError as exc:
            ui.bullet(str(exc), "bad")
            return

        ui.bullet("Repository {0} is reachable.".format(repo.full_name), "ok")
        ui.bullet("Push access." if repo.can_push else "No push access to this repository.",
                  "ok" if repo.can_push else "bad")
        if repo.fork:
            ui.bullet("This repository is a fork; commits in forks never count.", "bad")
        else:
            ui.bullet("Not a fork.", "ok")
        if repo.default_branch != settings.repo.branch:
            ui.bullet("Configured branch '{0}' is not the default branch '{1}'; "
                      "only the default branch counts.".format(
                          settings.repo.branch, repo.default_branch), "warn")
        else:
            ui.bullet("Committing to the default branch '{0}'.".format(repo.default_branch), "ok")
        if repo.private:
            ui.bullet("Private repository: enable 'Include private contributions on my "
                      "profile' in your GitHub profile settings.", "warn")

        if settings.author_email == user.noreply_email:
            ui.bullet("Author email is your GitHub noreply address; it always counts.", "ok")
        else:
            ui.bullet("Author email {0} must be listed under Settings > Emails to count.".format(
                settings.author_email or "(unset)"), "warn")

    def cmd_setup(self, args):
        ui.box_title("SETUP", "step 1 of 4")
        if not auth.resolve(self.token):
            self.cmd_login([])
        else:
            ui.ok("Already signed in.")

        settings = config.load()
        ui.box_title("SETUP", "step 2 of 4")
        if settings.repo.is_set():
            ui.info("Current target: {0}".format(settings.repo.full_name))
            if ui.confirm("Keep it?", default=True):
                pass
            else:
                self.cmd_select([])
        else:
            self.cmd_select([])

        ui.box_title("SETUP", "step 3 of 4")
        cli.cmd_config(_ns(show=False))

        ui.box_title("SETUP", "step 4 of 4")
        if ui.confirm("Install a daily scheduled run?", default=True):
            self.cmd_schedule([])
        ui.say()
        ui.ok("Setup complete.")
        ui.hint("Try /plan 30 for a preview, then /run.")
        self.cmd_status([])

    def cmd_login(self, args):
        cli.cmd_login(_ns(token=self.token, token_only="--token-only" in args))

    def cmd_logout(self, args):
        cli.cmd_logout(_ns())

    def cmd_repos(self, args):
        cli.cmd_repos(_ns(token=self.token))

    def cmd_select(self, args):
        target = args[0] if args else ""
        cli.cmd_select(_ns(token=self.token, repository=target, create="", public=False))

    def cmd_new(self, args):
        if not args:
            raise cli.CliError("Usage: /new <name> [--public]")
        name = args[0]
        cli.cmd_select(_ns(token=self.token, repository="", create=name,
                           public="--public" in args))

    def cmd_config(self, args):
        cli.cmd_config(_ns(show=True))
        ui.hint("Change one with: /set <key> <value>")

    def cmd_set(self, args):
        if len(args) < 2:
            raise cli.CliError("Usage: /set <key> <value>   (see /config for the keys)")
        settings = config.load()
        key = args[0]
        value = " ".join(args[1:])
        config.apply_setting(settings, key, value)
        config.save(settings)
        ui.ok("{0} = {1}".format(key.lower(), getattr(settings, key.lower())))

    def _range_from_args(self, args):
        days = 1
        if args:
            try:
                days = int(args[0])
            except ValueError:
                raise cli.CliError("Expected a number of days, got '{0}'.".format(args[0]))
            if days < 1:
                raise cli.CliError("The number of days must be at least 1.")
        today = date.today()
        return today - timedelta(days=days - 1), today, days

    def cmd_plan(self, args):
        settings = config.load()
        cli._require_repo(settings)
        start, end, _ = self._range_from_args(args)
        plan = runner.build_plan(settings, start, end)
        cli._print_plan(plan, settings, start, end)
        ui.hint("This was a preview. /run creates them for real.")

    def cmd_run(self, args):
        _, _, days = self._range_from_args(args)
        cli.cmd_run(_ns(token=self.token, today=False, days=days, from_date="", to_date="",
                        seed=None, dry_run=False, no_push=False, jitter=0, yes=False,
                        quiet=False, workdir=None, remote=""))

    def cmd_schedule(self, args):
        at = args[0] if args else ""
        jitter = None
        if len(args) > 1:
            try:
                jitter = int(args[1])
            except ValueError:
                raise cli.CliError("The jitter must be a number of minutes.")
        cli.cmd_schedule(_ns(at=at, jitter=jitter, backend="auto", remove=False, status=False))

    def cmd_unschedule(self, args):
        cli.cmd_schedule(_ns(at="", jitter=None, backend="auto", remove=True, status=False))

    def cmd_log(self, args):
        count = 10
        if args:
            try:
                count = max(1, int(args[0]))
            except ValueError:
                raise cli.CliError("Expected a number, got '{0}'.".format(args[0]))
        path = paths.log_file()
        if not path.exists():
            ui.info("No runs recorded yet.")
            return
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            ui.info("No runs recorded yet.")
            return
        ui.box_title("RECENT RUNS", "{0} total".format(len(lines)))
        for line in lines[-count:]:
            parts = line.split("\t")
            stamp = parts[0].replace("T", " ")[:19]
            rest = "  ".join(part.replace("=", " ") for part in parts[1:])
            print("  {0}  {1}".format(ui.paint(stamp, "grey"), rest))

    def cmd_clear(self, args):
        ui.clear_screen()
        self.cmd_status([])

    def cmd_quit(self, args):
        self.running = False
        ui.say("Bye.")


def start(token: str = "") -> int:
    return Console(token=token).loop()
