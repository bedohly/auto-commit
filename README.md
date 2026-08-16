<p align="center">
  <img src="assets/banner.webp" alt="auto commit" width="100%">
</p>

<h1 align="center">autocommit</h1>

<p align="center">
  <a href="https://github.com/Bedohly/auto-commit/actions/workflows/ci.yml"><img src="https://github.com/Bedohly/auto-commit/actions/workflows/ci.yml/badge.svg" alt="tests"></a>
  <img src="https://img.shields.io/badge/python-3.8%2B-blue" alt="python 3.8+">
  <img src="https://img.shields.io/badge/platforms-linux%20%7C%20macos%20%7C%20windows-lightgrey" alt="platforms">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license">
</p>

> **Built to teach, not to impress anyone.** This project exists to show how the
> GitHub API, git plumbing, backdated commits and cross-platform schedulers fit
> together. It inflates your own contribution graph with activity that is not
> real work, and anyone who opens a green square will see exactly that. Use it
> at your own risk: you are responsible for what it does to your account, and
> for staying inside [GitHub's Acceptable Use Policies](https://docs.github.com/site-policy/acceptable-use-policies/github-acceptable-use-policies).
> Point it at a repository you own and nothing else.

Create randomized, backdated commits in a GitHub repository you own — on a
schedule, on Linux, macOS and Windows.

You sign in once, pick (or create) a target repository, and the tool appends a
line to a log file and commits it a few times a day. Days are picked at random,
so the result is not a perfectly uniform block of green.

```
╭────────────────────────────────────────────────────────────╮
│  AUTOCOMMIT                                        v1.1.0  │
╰────────────────────────────────────────────────────────────╯
  account      ● bedohly  (github cli)
  repository   ● bedohly/activity-log  branch main
  author       ● Bedo <219016287+bedohly@users.noreply.github.com>
  cadence        1-6 commits/day · weekdays 85% · weekends 45%
  window         09:00-23:00 local · activity.md
  schedule     ● daily 20:00 (+90m) via schtasks
  last run     ● 2026-08-16 20:41 · commits 4 · days 1 · pushed yes

   Type /help for commands, /setup to configure everything, /quit to leave.

autocommit ›
```

- **More than commits.** Optionally opens issues and pull requests, reviews
  them and merges them — all in a repository you own, never anyone else's.
- **A console, not just flags.** Slash commands with a live status panel,
  tab completion and history — or plain subcommands when you are scripting.
- **No dependencies.** Python standard library only.
- **One codebase, three platforms.** Task Scheduler on Windows, systemd timers
  or cron on Linux and macOS.
- **Your token stays local.** Reads the `gh` CLI login if you have one, or
  stores a token with owner-only permissions. It is never written into
  `.git/config` or a command line.
- **Dry runs first.** `--dry-run` prints the plan and changes nothing.

---

## Requirements

| | |
|---|---|
| Python | 3.8 or newer |
| git | any recent version, on `PATH` |
| A GitHub token | classic with the `repo` scope, or fine-grained with **Contents: Read and write** on the target repository |

The [GitHub CLI](https://cli.github.com) is optional. If you are already logged
in with `gh auth login`, autocommit reuses that token and stores nothing.

## Install

### Linux / macOS

```bash
git clone https://github.com/Bedohly/auto-commit.git
cd auto-commit
./install.sh
```

The installer tries `pipx`, then `pip install --user`, then falls back to a
private virtualenv in `~/.local/share/autocommit/venv` (useful on Debian and
Ubuntu, where the system Python is externally managed).

### Windows

```powershell
git clone https://github.com/Bedohly/auto-commit.git
cd auto-commit
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

If `autocommit` is not on your `PATH` afterwards, either add the printed
`Scripts` folder to `PATH` or run the tool as `python -m autocommit`.

### Without installing

```bash
python -m autocommit --help
```
from the cloned folder works too.

## Quick start

Run `autocommit` with no arguments and let the console walk you through it:

```
autocommit › /setup
```

`/setup` signs you in, picks or creates the target repository, walks the
settings and offers to install the daily schedule — four steps, then you are
done.

Or drive it with subcommands, which is what you want in scripts:

```bash
autocommit login                      # sign in (or reuse the gh CLI login)
autocommit select                     # pick or create the target repository
autocommit run --dry-run --days 30    # preview a month, change nothing
autocommit run                        # commit and push today's batch
autocommit schedule --at 20:00 --jitter 90
```

## The console

`autocommit` (or `autocommit console`) opens a slash-command shell. It prints
the status panel above on entry and after every `/clear`, so you always know
what is configured.

| Command | What it does |
|---|---|
| `/help` | Every command, with aliases. |
| `/status` | The status panel. |
| `/check` | Live verification: token, scopes, push access, fork, default branch, author email. |
| `/setup` | Guided four-step setup. |
| `/login` · `/logout` | Sign in, or forget the saved token. |
| `/repos` | List repositories you can push to. |
| `/select [owner/repo]` | Pick the target. No argument opens a numbered picker. |
| `/new <name> [--public]` | Create a repository and select it. |
| `/config` · `/set <key> <value>` | Show settings, change one. |
| `/plan [days]` | Preview a plan without committing. |
| `/run [days]` | Create the commits and push. |
| `/activity [dry]` | Open issues and pull requests, review and merge them. |
| `/schedule [HH:MM] [jitter]` · `/unschedule` | Manage the daily run. |
| `/log [count]` | Recent runs. |
| `/clear` · `/quit` | Redraw, or leave. |

The leading slash is optional (`status` works too), aliases are short
(`/st`, `/q`, `/cls`), and a typo gets a suggestion rather than an error dump.
On Linux and macOS `readline` gives you tab completion and history; on Windows
the console host provides its own line editing.

Box drawing falls back to ASCII automatically when the console encoding cannot
represent it, and colors switch off when the output is piped. Set
`AUTOCOMMIT_ASCII=1` to force the plain look, `NO_COLOR=1` to drop colors.

## Commands

| Command | What it does |
|---|---|
| `autocommit` / `autocommit console` | Open the interactive console. |
| `autocommit login` | Verify a token and save it. `--token-only` skips the `gh` CLI. |
| `autocommit logout` | Delete the saved token. |
| `autocommit status` | Token, repository, settings, schedule and health checks. |
| `autocommit repos` | List repositories you can push to. |
| `autocommit select [owner/repo]` | Choose the target. `--create NAME` makes a new one (`--public` to make it public). |
| `autocommit config` | Edit settings interactively. `--show` prints them. |
| `autocommit run` | Build a plan, create the commits, push. |
| `autocommit activity` | Open issues and pull requests, review and merge them. |
| `autocommit schedule` | Install the daily run. `--remove`, `--status`. |

### `run` options

| Flag | Meaning |
|---|---|
| `--today` | Today only. This is the default. |
| `--days N` | Fill the last N days, today included. |
| `--from YYYY-MM-DD --to YYYY-MM-DD` | An explicit range (backfilling works). |
| `--dry-run` | Print the plan, touch nothing. |
| `--no-push` | Commit into the local working copy only. |
| `--seed N` | Fixed random seed, so a preview matches the real run. |
| `--jitter MIN` | Sleep a random 0–MIN minutes first. Used by the scheduler. |
| `--quiet` | No output on success. Used by the scheduler. |
| `--yes` | Do not ask for confirmation on large plans. |

## Settings

`autocommit config` edits these; they live in `config.json` (see
[Where things are stored](#where-things-are-stored)).

| Setting | Default | Meaning |
|---|---|---|
| `commit_file` | `activity.md` | Relative path inside the repo that gets appended to. |
| `min_commits` / `max_commits` | `1` / `6` | Commits per **active** day. Skewed towards the lower end. |
| `weekday_active_chance` | `0.85` | Probability that a given weekday gets any commits. |
| `weekend_active_chance` | `0.45` | Same, for Saturday and Sunday. |
| `active_hour_start` / `active_hour_end` | `9` / `23` | Local-time window the commit timestamps fall into. |
| `message_style` | `mixed` | `casual`, `conventional` or `mixed`. |
| `author_name` / `author_email` | from your GitHub profile | Defaults to your `@users.noreply.github.com` address. |

## Issues, pull requests and reviews

The contribution graph counts more than commits: opening an issue, opening a
pull request and submitting a review all show up. `autocommit activity` does
those too.

One round looks like this:

1. Branch off the default branch as `autocommit/<word>-<date>-<n>`.
2. Put one to three commits on it and push the branch.
3. Open a pull request from that branch.
4. Submit a review on it.
5. Merge it and delete the branch.
6. Open an issue or two, and close them again.

```bash
autocommit activity --dry-run          # show what a round would do
autocommit activity --pulls 1 --issues 2
autocommit activity --no-merge         # leave the pull requests open
```

In the console it is `/activity` (or `/activity dry` for a preview).

**Read this part before turning it on:**

- **Only repositories you own.** The tool checks that the target belongs to the
  signed-in account and refuses otherwise. Automated issues and pull requests
  in somebody else's project are spam, and that is not a line worth crossing
  for a green square.
- **None of it can be backdated.** GitHub stamps issues and pull requests when
  they are created, so `--days 30` has no equivalent here — an activity round
  only ever affects today.
- **You cannot approve your own pull request.** GitHub rejects it, so reviews
  are submitted as comments. A comment review on your own pull request may not
  register as a contribution at all; commits, issues and opened pull requests
  are the reliable part.
- **It is visible.** These items sit in the Issues and Pull requests tabs with
  obviously generated titles. A dedicated repository is the right place for it.

To include the round in the daily scheduled run:

```bash
autocommit config              # or: /set activity_enabled true
```

| Setting | Default | Meaning |
|---|---|---|
| `activity_enabled` | `false` | Whether `autocommit run` also does an activity round. `autocommit activity` runs regardless. |
| `activity_chance` | `0.5` | Probability that a round does anything at all. |
| `issues_min` / `issues_max` | `0` / `1` | Issues opened per round. |
| `pulls_min` / `pulls_max` | `0` / `1` | Pull requests opened per round. |
| `pull_commits_min` / `pull_commits_max` | `1` / `3` | Commits on each pull request branch. |
| `review_pulls` | `true` | Submit a comment review on each pull request. |
| `merge_pulls` | `true` | Merge the pull request and delete its branch. |
| `close_issues` | `true` | Close each issue after opening it. |

## Scheduling

```bash
autocommit schedule --at 20:00 --jitter 90   # install
autocommit schedule --status                 # inspect
autocommit schedule --remove                 # uninstall
```

`--jitter` spreads the actual start time over a random window after `--at`, so
the commits do not land at exactly the same second every day.

| Platform | Backend | Where it lives |
|---|---|---|
| Windows | Task Scheduler | task `AutoCommit` (`schtasks /Query /TN AutoCommit`) |
| Linux with systemd | user timer | `~/.config/systemd/user/autocommit.timer` |
| Linux / macOS otherwise | cron | a line tagged `# autocommit` in your crontab |

Two things worth knowing:

- A scheduled run has no terminal, so it needs a **saved** token — run
  `autocommit login` and let it store one (or keep `gh` logged in).
- With systemd, run `loginctl enable-linger $USER` if you want the timer to
  fire while you are logged out.

## How the contribution graph actually counts commits

Getting this wrong is the usual reason the squares stay grey:

1. **The author email must belong to your GitHub account.** autocommit defaults
   to `ID+login@users.noreply.github.com`, which always does. If you override
   `author_email`, use an address listed under *Settings → Emails*.
2. **Commits must land on the default branch** (or `gh-pages`) of the
   repository. The tool pushes to the repository's default branch.
3. **The repository must not be a fork.** Commits in forks never count.
4. **Private repositories count only if** *Settings → Profile → Include private
   contributions on my profile* is enabled.
5. **Backdating works**, because git records the author date and GitHub renders
   the graph from it. Commits dated in a previous year show up in that year's
   graph, not today's.
6. **Issues and opened pull requests count** in the repositories you own.
   Reviews of your own pull requests are unreliable; see the section above.
7. The graph is cached; give it a few minutes.

`autocommit status` warns you about most of these.

## Where things are stored

| | Linux / macOS | Windows |
|---|---|---|
| Config | `~/.config/autocommit/config.json` | `%APPDATA%\autocommit\config.json` |
| Token | `~/.config/autocommit/token` (mode `600`) | `%APPDATA%\autocommit\token` (owner-only ACL) |
| Working copies | `~/.local/share/autocommit/repos/` | `%LOCALAPPDATA%\autocommit\repos\` |
| Run log | `~/.local/share/autocommit/run.log` | `%LOCALAPPDATA%\autocommit\run.log` |

Set `AUTOCOMMIT_HOME` to put all of it somewhere else. `AUTOCOMMIT_TOKEN`,
`GITHUB_TOKEN` or `GH_TOKEN` override the stored token for a single run.

The target repository is cloned shallow (`--depth 1`) into the working-copy
folder, so a large repository does not cost you a full history download.

## Development

```bash
python -m unittest discover -s tests -t . -v
```

116 tests covering the planner, config, token handling, the GitHub client, the
schedulers, console dispatch and panel rendering, the ownership guard, and full
end-to-end runs — commit, push, re-clone, re-sync, branch, pull request — against
a local bare repository with a recording fake in place of the GitHub API. Nothing
in the suite talks to github.com. CI runs the same suite on Ubuntu, Windows and
macOS, on Python 3.9 and 3.13.

## License

MIT — see [LICENSE](LICENSE).
