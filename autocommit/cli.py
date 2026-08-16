"""Command line entry points for autocommit."""

from __future__ import annotations

import argparse
import getpass
import random
import sys
import time
from datetime import date, datetime, timedelta

from autocommit import (__version__, activity, auth, config, paths, planner, runner,
                        schedule, ui)
from autocommit.config import Settings
from autocommit.github import GitHubClient, GitHubError
from autocommit.gitrepo import GitError, git_version

BIG_PLAN = 150


class CliError(Exception):
    """Anything the user can fix, reported without a traceback."""


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
def _token_info(explicit: str = ""):
    info = auth.resolve(explicit)
    if not info:
        raise CliError(
            "Not signed in. Run 'autocommit login', or set GITHUB_TOKEN in the environment."
        )
    return info


def _client(explicit: str = ""):
    info = _token_info(explicit)
    return GitHubClient(info.value), info


def _require_repo(settings: Settings):
    if not settings.repo.is_set():
        raise CliError("No repository selected yet. Run 'autocommit select' first.")


def _parse_day(raw: str) -> date:
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise CliError("Dates must look like YYYY-MM-DD (got '{0}').".format(raw))


def _resolve_range(args):
    today = date.today()
    if getattr(args, "today", False):
        return today, today
    if args.from_date or args.to_date:
        start = _parse_day(args.from_date) if args.from_date else today
        end = _parse_day(args.to_date) if args.to_date else today
        if end < start:
            raise CliError("--to cannot be earlier than --from.")
        return start, end
    if args.days and args.days > 1:
        return today - timedelta(days=args.days - 1), today
    return today, today


def _apply_identity(settings: Settings, client: GitHubClient) -> None:
    user = client.whoami()
    settings.account = user.login
    if not settings.author_name:
        settings.author_name = user.display_name
    if not settings.author_email:
        settings.author_email = user.noreply_email
    return user


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_login(args) -> int:
    settings = config.load()
    token = (args.token or "").strip()
    source = "argument"

    if not token and not args.token_only:
        cli_token = auth.gh_token()
        if cli_token:
            ui.info("Found a token from the GitHub CLI (gh).")
            if ui.is_interactive():
                use_it = ui.confirm("Use the GitHub CLI login?", default=True)
            else:
                use_it = True
            if use_it:
                token, source = cli_token, "github cli"

    if not token:
        if not ui.is_interactive():
            raise CliError("No token available. Pass --token or set GITHUB_TOKEN.")
        ui.say()
        ui.say("Create a token at: https://github.com/settings/tokens")
        ui.hint("Classic token: tick the 'repo' scope.")
        ui.hint("Fine-grained token: give it 'Contents: Read and write' on the target repository.")
        token = getpass.getpass("Paste your token (input hidden): ").strip()
        source = "manual entry"
    if not token:
        raise CliError("No token entered.")

    client = GitHubClient(token)
    user = client.whoami()
    scopes = client.token_scopes()
    if auth.missing_scope(scopes):
        ui.warn("This token has scopes [{0}] and probably cannot push.".format(", ".join(scopes)))

    if source != "github cli":
        auth.store_token(token)
        ui.ok("Token saved to {0}".format(paths.token_file()))
    else:
        ui.ok("Using the GitHub CLI token (nothing stored on disk).")

    _apply_identity(settings, client)
    config.save(settings)
    ui.ok("Signed in as {0} ({1}).".format(user.login, user.display_name))
    ui.info("Commits will be authored as: {0} <{1}>".format(
        settings.author_name, settings.author_email))
    return 0


def cmd_logout(args) -> int:
    if auth.forget_token():
        ui.ok("Stored token removed.")
    else:
        ui.info("No stored token found.")
    if auth.env_token():
        ui.warn("A token is still present in the environment (GITHUB_TOKEN / AUTOCOMMIT_TOKEN).")
    if auth.gh_token():
        ui.warn("The GitHub CLI is still logged in; run 'gh auth logout' to clear it.")
    return 0


def cmd_status(args) -> int:
    from autocommit import console  # imported late: console imports cli

    console.render_status(args.token)

    try:
        ui.field("git", git_version().replace("git version ", ""), "ok")
    except GitError as exc:
        ui.field("git", str(exc), "bad")
    ui.field("config", str(paths.config_file()))
    ui.field("workdir", str(paths.repos_dir()))
    return 0


def cmd_repos(args) -> int:
    client, _ = _client(args.token)
    repos = client.list_repos()
    if not repos:
        ui.warn("No repositories found for this token.")
        return 0
    ui.banner("YOUR REPOSITORIES", "{0} found".format(len(repos)))
    for repo in repos:
        flags = []
        if repo.private:
            flags.append("private")
        if repo.fork:
            flags.append("fork")
        if not repo.can_push:
            flags.append("read-only")
        suffix = "  [{0}]".format(", ".join(flags)) if flags else ""
        ui.say("  {0}  (branch: {1}){2}".format(repo.full_name, repo.default_branch, suffix))
    return 0


def _adopt_repo(settings: Settings, repo, client: GitHubClient) -> None:
    if not repo.can_push:
        raise CliError("You do not have push access to {0}.".format(repo.full_name))
    if repo.fork:
        ui.warn("{0} is a fork. Commits in forks do not count towards contributions.".format(
            repo.full_name))
    settings.repo.owner = repo.owner
    settings.repo.name = repo.name
    settings.repo.branch = repo.default_branch
    settings.repo.private = repo.private
    _apply_identity(settings, client)
    config.save(settings)
    ui.ok("Target repository: {0} (branch {1})".format(
        settings.repo.full_name, settings.repo.branch))
    if repo.private:
        ui.hint("Private repository: enable Settings > Profile > 'Include private contributions "
                "on my profile' for the graph to show them.")


def cmd_select(args) -> int:
    settings = config.load()
    client, _ = _client(args.token)

    if args.create:
        repo = client.create_repo(
            name=args.create, private=not args.public,
            description="Activity log managed by autocommit",
        )
        ui.ok("Created {0}.".format(repo.full_name))
        _adopt_repo(settings, repo, client)
        return 0

    if args.repository:
        if "/" in args.repository:
            owner, _, name = args.repository.partition("/")
        else:
            owner, name = client.whoami().login, args.repository
        repo = client.get_repo(owner, name)
        _adopt_repo(settings, repo, client)
        return 0

    if not ui.is_interactive():
        raise CliError("Pass a repository name, for example: autocommit select owner/repo")

    return _interactive_select(settings, client)


def _interactive_select(settings: Settings, client: GitHubClient) -> int:
    ui.info("Loading your repositories...")
    repos = client.list_repos()
    writable = [repo for repo in repos if repo.can_push]
    labels = []
    for repo in writable:
        marks = []
        if repo.private:
            marks.append("private")
        if repo.fork:
            marks.append("fork")
        labels.append("{0}{1}".format(
            repo.full_name, "  [{0}]".format(", ".join(marks)) if marks else ""))
    labels.append("+ Create a new repository")
    labels.append("> Type a repository name manually")

    index = ui.choose("Select the repository to commit into:", labels)
    if index is None:
        return 0
    if index == len(labels) - 2:
        name = ui.ask("New repository name", "activity-log")
        private = ui.confirm("Make it private?", default=True)
        repo = client.create_repo(name=name, private=private,
                                 description="Activity log managed by autocommit")
        ui.ok("Created {0}.".format(repo.full_name))
        _adopt_repo(settings, repo, client)
        return 0
    if index == len(labels) - 1:
        raw = ui.ask("Repository (owner/name)")
        if not raw:
            return 0
        owner, _, name = raw.partition("/")
        repo = client.get_repo(owner or client.whoami().login, name or owner)
        _adopt_repo(settings, repo, client)
        return 0

    _adopt_repo(settings, writable[index], client)
    return 0


def cmd_config(args) -> int:
    settings = config.load()
    if args.show or not ui.is_interactive():
        ui.banner("SETTINGS")
        for key, value in sorted(settings.to_dict().items()):
            ui.say("  {0:<24} {1}".format(key, value))
        ui.info("Stored in {0}".format(paths.config_file()))
        return 0

    ui.banner("SETTINGS", "press Enter to keep the current value")
    settings.commit_file = ui.ask("File to append to", settings.commit_file)
    settings.min_commits = ui.ask_int("Minimum commits per active day", settings.min_commits, 1, 100)
    settings.max_commits = ui.ask_int(
        "Maximum commits per active day", max(settings.max_commits, settings.min_commits),
        settings.min_commits, 100)
    settings.weekday_active_chance = ui.ask_float(
        "Chance a weekday is active (0-1)", settings.weekday_active_chance)
    settings.weekend_active_chance = ui.ask_float(
        "Chance a weekend day is active (0-1)", settings.weekend_active_chance)
    settings.active_hour_start = ui.ask_int(
        "Earliest hour (0-23)", settings.active_hour_start, 0, 23)
    settings.active_hour_end = ui.ask_int(
        "Latest hour (1-24)", settings.active_hour_end, settings.active_hour_start + 1, 24)
    style = ui.ask("Message style (casual/conventional/mixed)", settings.message_style)
    settings.message_style = style if style in ("casual", "conventional", "mixed") else "mixed"
    settings.author_name = ui.ask("Author name", settings.author_name)
    settings.author_email = ui.ask("Author email", settings.author_email)

    try:
        config.save(settings)
    except ValueError as exc:
        raise CliError(str(exc))
    ui.ok("Settings saved to {0}".format(paths.config_file()))
    return 0


def _print_plan(plan, settings: Settings, start: date, end: date) -> None:
    summary = planner.summarize(plan)
    ui.banner("PLAN", "{0} -> {1}".format(start.isoformat(), end.isoformat()))
    for day in summary:
        bar = "#" * min(day.count, 40)
        ui.say("  {0}  {1:>3}  {2}".format(day.day.isoformat(), day.count, ui.paint(bar, "green")))
    total_days = (end - start).days + 1
    ui.rule()
    ui.say("  {0} commits across {1} active day(s) out of {2}".format(
        len(plan), len(summary), total_days))
    ui.say("  Repository: {0} (branch {1})".format(settings.repo.full_name, settings.repo.branch))
    ui.say("  Author:     {0} <{1}>".format(settings.author_name, settings.author_email))
    ui.say("  File:       {0}".format(settings.commit_file))


def cmd_run(args) -> int:
    settings = config.load()
    _require_repo(settings)
    try:
        settings.validate()
    except ValueError as exc:
        raise CliError(str(exc))

    start, end = _resolve_range(args)
    plan = runner.build_plan(settings, start, end, seed=args.seed)

    if not args.quiet:
        _print_plan(plan, settings, start, end)

    if not plan:
        if not args.quiet:
            ui.info("Nothing to do today - the dice picked a rest day.")
        return 0

    if args.dry_run:
        ui.info("Dry run: no commits were created.")
        return 0

    if len(plan) > BIG_PLAN and not args.yes and ui.is_interactive():
        if not ui.confirm("That is {0} commits. Continue?".format(len(plan)), default=False):
            ui.info("Cancelled.")
            return 0

    # A token is only needed to push over https to github.com.
    destination = args.remote or settings.repo.clone_url
    if args.no_push or not destination.lower().startswith("http"):
        token = args.token or ""
    else:
        token = _token_info(args.token).value

    if args.jitter:
        delay = random.randint(0, args.jitter * 60)
        if not args.quiet:
            ui.info("Waiting {0}m {1}s before starting (jitter).".format(delay // 60, delay % 60))
        time.sleep(delay)

    live = bool(getattr(sys.stdout, "isatty", lambda: False)())

    def progress(index, total, item):
        if args.quiet:
            return
        if live:
            sys.stdout.write("\r  committing {0}/{1} ...".format(index, total))
            sys.stdout.flush()
        elif index == total or index % 25 == 0:
            print("  committing {0}/{1}".format(index, total))

    try:
        result = runner.execute(
            settings=settings,
            plan=plan,
            token=token,
            push=not args.no_push,
            workdir=args.workdir,
            remote_url=args.remote or "",
            on_progress=progress,
        )
    except GitError as exc:
        raise CliError(str(exc))

    if not args.quiet:
        if live:
            sys.stdout.write("\r" + " " * 40 + "\r")
        ui.ok("{0} commit(s) created in {1} ({2}).".format(
            result.created, result.workdir, result.repo_status))
        if result.pushed:
            ui.ok("Pushed to {0} ({1}).".format(settings.repo.full_name, settings.repo.branch))
        else:
            ui.warn("Not pushed (--no-push). Nothing reached GitHub.")

    runner.append_run_log(result, settings, datetime.now())

    # Issues and pull requests only make sense against the real repository on
    # github.com, so a local --remote or a --no-push run skips them.
    wants_activity = settings.activity_enabled or args.activity
    if wants_activity and not args.no_activity and not args.no_push and not args.remote:
        ui.rule("activity")
        _run_activity(settings, args, token=token)
    return 0


def _run_activity(settings: Settings, args, client=None, token: str = "") -> None:
    """Shared by `autocommit activity` and the tail of `autocommit run`."""
    rng = random.Random(args.seed) if getattr(args, "seed", None) is not None else random.Random()
    plan = activity.build_plan(settings, rng)

    for name, value in (("issues", getattr(args, "issues", None)),
                        ("pulls", getattr(args, "pulls", None))):
        if value is not None:
            setattr(plan, name, value)
    if getattr(args, "no_review", False):
        plan.review = False
    if getattr(args, "no_merge", False):
        plan.merge = False
    if plan.pulls and len(plan.pull_commits) != plan.pulls:
        plan.pull_commits = [
            rng.randint(settings.pull_commits_min, settings.pull_commits_max)
            for _ in range(plan.pulls)
        ]

    if not args.quiet:
        ui.info("Activity plan: {0}".format(plan.describe()))

    if plan.is_empty:
        return
    if getattr(args, "dry_run", False):
        if not args.quiet:
            ui.info("Dry run: no issues or pull requests were created.")
        return

    if client is None:
        client, _ = _client(args.token)
    user = client.whoami()
    try:
        activity.guard_ownership(settings, user.login)
    except activity.OwnershipError as exc:
        raise CliError(str(exc))

    if not token:
        token = _token_info(args.token).value

    def announce(text):
        if not args.quiet:
            ui.hint(text)

    result = activity.execute(
        settings=settings,
        plan=plan,
        client=client,
        token=token,
        workdir=getattr(args, "workdir", None),
        remote_url=getattr(args, "remote", "") or "",
        rng=rng,
        on_event=announce,
    )
    if result.skipped and not args.quiet:
        ui.warn(result.skipped)
    if not args.quiet:
        ui.ok("Opened {0} pull request(s) and {1} issue(s); {2} merged, {3} reviewed.".format(
            len(result.pulls), len(result.issues), result.merged, result.reviews))


def cmd_activity(args) -> int:
    settings = config.load()
    _require_repo(settings)
    try:
        settings.validate()
    except ValueError as exc:
        raise CliError(str(exc))
    _run_activity(settings, args)
    return 0


def cmd_schedule(args) -> int:
    if args.remove:
        removed = schedule.remove()
        if removed:
            ui.ok("Scheduled run removed.")
        else:
            ui.info("No scheduled run was installed.")
        return 0

    if args.status:
        state = schedule.status()
        if state.installed:
            ui.ok("Installed via {0}".format(state.backend))
            if state.detail:
                ui.hint(state.detail)
        else:
            ui.warn("No scheduled run installed.")
        return 0

    settings = config.load()
    _require_repo(settings)

    raw = args.at
    if not raw and ui.is_interactive():
        raw = ui.ask("Daily start time (HH:MM, local)", "20:00")
    raw = raw or "20:00"
    try:
        hour_text, _, minute_text = raw.partition(":")
        hour, minute = int(hour_text), int(minute_text or 0)
    except ValueError:
        raise CliError("Time must look like HH:MM (got '{0}').".format(raw))

    jitter = args.jitter
    if jitter is None and ui.is_interactive():
        jitter = ui.ask_int("Random delay after that time, in minutes", 90, 0, 600)
    jitter = jitter or 0

    if not auth.stored_token() and not auth.env_token() and not auth.gh_available():
        ui.warn("No token is available without a terminal. Run 'autocommit login' and save a "
                "token, otherwise the scheduled run cannot push.")

    try:
        state = schedule.install(hour, minute, jitter, backend=args.backend)
    except schedule.ScheduleError as exc:
        raise CliError(str(exc))

    ui.ok("Daily run installed via {0} at {1:02d}:{2:02d} (+ up to {3} min).".format(
        state.backend, hour, minute, jitter))
    if state.detail:
        ui.hint(state.detail)
    if state.backend == "systemd":
        ui.hint("Run 'loginctl enable-linger $USER' so the timer also fires when logged out.")
    return 0


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocommit",
        description="Create randomized commits in a GitHub repository you own.",
        epilog="Built as a teaching project. It fabricates activity on your own "
               "account; use it at your own risk and only on repositories you own.",
    )
    parser.add_argument("--version", action="version", version="autocommit " + __version__)
    parser.add_argument("--token", default="", help="GitHub token to use for this call only")
    sub = parser.add_subparsers(dest="command")

    login = sub.add_parser("login", help="sign in and store a GitHub token")
    login.add_argument("--token-only", action="store_true",
                       help="ignore the GitHub CLI and ask for a token")
    login.set_defaults(func=cmd_login)

    logout = sub.add_parser("logout", help="delete the stored token")
    logout.set_defaults(func=cmd_logout)

    status = sub.add_parser("status", help="show the current configuration and health checks")
    status.set_defaults(func=cmd_status)

    repos = sub.add_parser("repos", help="list repositories you can push to")
    repos.set_defaults(func=cmd_repos)

    select = sub.add_parser("select", help="choose the repository to commit into")
    select.add_argument("repository", nargs="?", default="", help="owner/name")
    select.add_argument("--create", default="", metavar="NAME",
                        help="create a new repository and select it")
    select.add_argument("--public", action="store_true",
                        help="make the created repository public")
    select.set_defaults(func=cmd_select)

    cfg = sub.add_parser("config", help="view or edit settings")
    cfg.add_argument("--show", action="store_true", help="print settings and exit")
    cfg.set_defaults(func=cmd_config)

    run = sub.add_parser("run", help="generate commits and push them")
    run.add_argument("--today", action="store_true", help="only today (default)")
    run.add_argument("--days", type=int, default=1,
                     help="fill the last N days, today included")
    run.add_argument("--from", dest="from_date", default="", metavar="YYYY-MM-DD")
    run.add_argument("--to", dest="to_date", default="", metavar="YYYY-MM-DD")
    run.add_argument("--seed", type=int, default=None,
                     help="fixed random seed, useful for previews")
    run.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    run.add_argument("--no-push", action="store_true",
                     help="commit locally without pushing to GitHub")
    run.add_argument("--jitter", type=int, default=0, metavar="MIN",
                     help="wait a random 0-MIN minutes before starting")
    run.add_argument("--yes", action="store_true", help="skip confirmation prompts")
    run.add_argument("--quiet", action="store_true", help="print nothing on success")
    run.add_argument("--workdir", default=None,
                     help="advanced: use this working copy instead of the cached one")
    run.add_argument("--remote", default="",
                     help="advanced: push to this URL instead of github.com")
    run.add_argument("--activity", action="store_true",
                     help="also open issues and pull requests, ignoring the setting")
    run.add_argument("--no-activity", action="store_true",
                     help="skip the issue and pull request round for this call")
    run.set_defaults(func=cmd_run, issues=None, pulls=None,
                     no_review=False, no_merge=False)

    act = sub.add_parser(
        "activity",
        help="open issues and pull requests, and review them",
        description="Runs whether or not activity_enabled is set; that setting only "
                    "controls whether `autocommit run` includes this round.",
    )
    act.add_argument("--issues", type=int, default=None, metavar="N",
                     help="open exactly N issues instead of rolling for it")
    act.add_argument("--pulls", type=int, default=None, metavar="N",
                     help="open exactly N pull requests instead of rolling for it")
    act.add_argument("--no-review", action="store_true", help="do not review the pull requests")
    act.add_argument("--no-merge", action="store_true", help="leave the pull requests open")
    act.add_argument("--seed", type=int, default=None, help="fixed random seed")
    act.add_argument("--dry-run", action="store_true", help="show the plan, create nothing")
    act.add_argument("--quiet", action="store_true", help="print nothing on success")
    act.add_argument("--workdir", default=None, help="advanced: use this working copy")
    act.add_argument("--remote", default="", help="advanced: push branches to this URL")
    act.set_defaults(func=cmd_activity)

    sched = sub.add_parser("schedule", help="install or remove the daily run")
    sched.add_argument("--at", default="", metavar="HH:MM", help="local start time")
    sched.add_argument("--jitter", type=int, default=None, metavar="MIN",
                       help="random delay added to the start time")
    sched.add_argument("--backend", default="auto",
                       choices=("auto", "cron", "systemd", "schtasks"))
    sched.add_argument("--remove", action="store_true", help="remove the scheduled run")
    sched.add_argument("--status", action="store_true", help="show the scheduled run")
    sched.set_defaults(func=cmd_schedule)

    console = sub.add_parser("console", aliases=["menu"],
                             help="open the interactive slash-command console")
    console.set_defaults(func=None)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command in ("console", "menu"):
            from autocommit import console  # imported late: console imports cli

            return console.start(args.token)
        if not args.command:
            # Bare `autocommit` opens the console, but only with a real terminal;
            # piped or scripted use gets the help text instead.
            if not ui.is_interactive():
                parser.print_help()
                return 0
            from autocommit import console

            return console.start(args.token)
        return args.func(args)
    except CliError as exc:
        ui.fail(str(exc))
        return 1
    except (GitHubError, GitError, schedule.ScheduleError) as exc:
        ui.fail(str(exc))
        return 1
    except ValueError as exc:
        ui.fail(str(exc))
        return 1
    except KeyboardInterrupt:
        ui.say()
        ui.info("Cancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
