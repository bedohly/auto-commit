# Reference

Everything the [README](../README.md) leaves out. You do not need any of this
to use the tool.

- [Requirements](#requirements)
- [Installing without the script](#installing-without-the-script)
- [Command line](#command-line)
- [The console](#the-console)
- [Profiles and the ramp](#profiles-and-the-ramp)
- [Settings](#settings)
- [Scheduling](#scheduling)
- [Issues, pull requests and reviews](#issues-pull-requests-and-reviews)
- [Tokens and what is stored where](#tokens-and-what-is-stored-where)
- [How contributions are counted](#how-contributions-are-counted)
- [Development](#development)

---

## Requirements

| | |
|---|---|
| Python | 3.8 or newer |
| git | any recent version, on `PATH` |
| A GitHub token | classic with the `repo` scope, or fine-grained with **Contents: Read and write** on the target repository. Add **Issues: Read and write** and **Pull requests: Read and write** if you want the activity round. |

The [GitHub CLI](https://cli.github.com) is optional. If you are already logged
in with `gh auth login`, the tool reuses that token and stores nothing itself.

## Installing without the script

```bash
pip install --user .        # or: pipx install .
```

On Debian and Ubuntu the system Python is externally managed and `pip --user`
refuses to install. `install.sh` handles that by falling back to a private
virtualenv at `~/.local/share/autocommit/venv` and symlinking the entry point
into `~/.local/bin`.

Running from a clone without installing works too:

```bash
python -m autocommit --help
```

## Command line

| Command | What it does |
|---|---|
| `autocommit` | Open the console (or print help when the output is piped) |
| `autocommit console` | Open the console explicitly, even when piped |
| `autocommit login` | Verify a token and save it. `--token-only` skips the `gh` CLI |
| `autocommit logout` | Delete the saved token |
| `autocommit status` | Configuration, schedule, last run, health checks |
| `autocommit check` | Live verification against the GitHub API |
| `autocommit repos` | List repositories you can push to |
| `autocommit select [owner/repo]` | Choose the target. `--create NAME` makes a new one, `--public` to make it public |
| `autocommit profile [name]` | List profiles, or apply one |
| `autocommit config` | Edit settings interactively. `--show` prints them |
| `autocommit run` | Build a plan, create the commits, push |
| `autocommit activity` | Open issues and pull requests, review and merge them |
| `autocommit schedule` | Install the daily run. `--remove`, `--status` |

`--token TOKEN` works on any command and overrides the stored one for that call.

### `run`

| Flag | Meaning |
|---|---|
| `--today` | Today only. This is the default |
| `--days N` | Fill the last N days, today included |
| `--from YYYY-MM-DD --to YYYY-MM-DD` | An explicit range. Backfilling works |
| `--dry-run` | Print the plan, touch nothing |
| `--no-push` | Commit into the local working copy only |
| `--seed N` | Fixed random seed, so a preview matches the real run |
| `--jitter MIN` | Sleep a random 0–MIN minutes first |
| `--activity` / `--no-activity` | Force the issue and pull request round on or off for this call |
| `--quiet` | No output on success |
| `--yes` | Do not ask for confirmation on large plans |
| `--workdir PATH` / `--remote URL` | Advanced: use a different working copy or push somewhere other than github.com. A non-github remote also disables the activity round |

### `activity`

| Flag | Meaning |
|---|---|
| `--issues N` / `--pulls N` | Create exactly N instead of rolling for it |
| `--no-review` | Do not review the pull requests |
| `--no-merge` | Leave the pull requests open |
| `--dry-run` | Show the plan, create nothing |
| `--seed N` | Fixed random seed |

`autocommit activity` runs whether or not `activity_enabled` is set. That
setting only controls whether `autocommit run` includes the round.

## The console

`autocommit` with no arguments opens a slash-command shell. The leading slash
is optional, aliases are in brackets, and a typo gets a suggestion.

| Command | What it does |
|---|---|
| `/help` (`/h`, `/?`) | Every command |
| `/status` (`/st`) | The status panel |
| `/check` (`/doctor`) | Live verification: token, scopes, push access, fork, default branch, author email |
| `/setup` | Guided four-step setup |
| `/login` · `/logout` | Sign in, or forget the saved token |
| `/repos` | Repositories you can push to |
| `/select [owner/repo]` (`/use`) | Pick the target. No argument opens a picker |
| `/new <name> [--public]` | Create a repository and select it |
| `/profile [name]` | List profiles, or apply one |
| `/config` (`/settings`) · `/set <key> <value>` | Show settings, change one |
| `/plan [days]` (`/preview`) | Preview a plan without committing |
| `/run [days]` | Create the commits and push |
| `/activity [dry]` (`/pr`) | Issues and pull requests |
| `/schedule [HH:MM] [jitter]` · `/unschedule` | Manage the daily run |
| `/log [count]` | Recent runs |
| `/clear` (`/cls`) · `/quit` (`/exit`, `/q`) | Redraw, or leave |

On Linux and macOS the stdlib `readline` module supplies tab completion and
history. On Windows the console host provides its own line editing.

Box drawing falls back to ASCII when the console encoding cannot represent it,
and colors switch off when the output is piped. `AUTOCOMMIT_ASCII=1` forces the
plain look, `NO_COLOR=1` drops colors.

## Profiles and the ramp

A profile is a bundle of settings. Applying one overwrites those settings and
restarts the ramp from today.

| Profile | commits/day | weekdays | weekends | hours | ramp | activity |
|---|---|---|---|---|---|---|
| `starter` | 1–2 | 45% | 15% | 10:00–22:00 | 30 days | off |
| `casual` | 1–3 | 60% | 25% | 09:00–23:00 | 14 days | off |
| `steady` | 1–4 | 80% | 40% | 09:00–23:00 | 7 days | on, 25% of days |
| `heavy` | 2–8 | 95% | 80% | 08:00–24:00 | none | on, 60% of days |

A fresh install already carries the `starter` values.

### How the ramp works

For each day being planned:

```
factor  = clamp((day - started_on) / ramp_days, 0, 1)
max     = min_commits + round((max_commits - min_commits) * factor)
chance  = configured_chance * (0.35 + 0.65 * factor)
```

So on day one the ceiling is `min_commits` and the odds of an active day are a
third of the configured value; by the end of the ramp both are at full value.
`ramp_days = 0` or an empty `started_on` means no ramp — the factor is always
1.0, which is what every hand-tuned setup gets.

`started_on` is set when you apply a profile, or when you first select a
repository.

## Settings

`autocommit config` edits these interactively, `/set <key> <value>` changes one,
and `autocommit config --show` prints the lot. Values are type-checked and
rolled back if the result would be invalid.

### Commits

| Setting | Default | Meaning |
|---|---|---|
| `commit_file` | `activity.md` | Relative path inside the repo that gets appended to |
| `min_commits` / `max_commits` | `1` / `2` | Commits per active day. Skewed towards the lower end |
| `weekday_active_chance` | `0.45` | Probability a given weekday gets any commits |
| `weekend_active_chance` | `0.15` | Same, for Saturday and Sunday |
| `active_hour_start` / `active_hour_end` | `10` / `22` | Local-time window the timestamps fall into |
| `message_style` | `mixed` | `casual`, `conventional` or `mixed` |
| `author_name` / `author_email` | from your GitHub profile | Defaults to your `@users.noreply.github.com` address |

### Ramp

| Setting | Default | Meaning |
|---|---|---|
| `ramp_days` | `30` | Days to reach the full rate. `0` disables the ramp |
| `started_on` | set on first use | Date the ramp counts from (`YYYY-MM-DD`) |
| `profile` | `starter` | Which preset was applied last |

### Issues and pull requests

| Setting | Default | Meaning |
|---|---|---|
| `activity_enabled` | `false` | Whether `autocommit run` also does an activity round |
| `activity_chance` | `0.5` | Probability a round does anything at all |
| `issues_min` / `issues_max` | `0` / `1` | Issues opened per round |
| `pulls_min` / `pulls_max` | `0` / `1` | Pull requests opened per round |
| `pull_commits_min` / `pull_commits_max` | `1` / `3` | Commits on each pull request branch |
| `review_pulls` | `true` | Submit a comment review on each pull request |
| `merge_pulls` | `true` | Merge the pull request and delete its branch |
| `close_issues` | `true` | Close each issue after opening it |

### Other

| Setting | Default | Meaning |
|---|---|---|
| `jitter_minutes` | `0` | Stored default for `--jitter` |

## Scheduling

```bash
autocommit schedule --at 20:00 --jitter 90   # install
autocommit schedule --status                 # inspect
autocommit schedule --remove                 # uninstall
```

`--jitter` spreads the real start time over a random window after `--at`, so
the commits do not land at the same second every day.

| Platform | Backend | Where it lives |
|---|---|---|
| Windows | Task Scheduler | task `AutoCommit` — `schtasks /Query /TN AutoCommit` |
| Linux with systemd | user timer | `~/.config/systemd/user/autocommit.timer`, with `RandomizedDelaySec` |
| Linux / macOS otherwise | cron | a line tagged `# autocommit` in your crontab |

The installed command is `autocommit run --today --quiet [--jitter N]`, using
the absolute path to the entry point (or `pythonw.exe -m autocommit` on Windows
when the console script is not on `PATH`, so no window flashes up).

Two things worth knowing:

- A scheduled run has no terminal, so it needs a **saved** token. Run
  `autocommit login` and let it store one, or keep `gh` logged in.
- With systemd, `loginctl enable-linger $USER` makes the timer fire while you
  are logged out.

## Issues, pull requests and reviews

One round is:

1. Branch off the default branch as `autocommit/<word>-<date>-<n>`.
2. Put `pull_commits_min`–`pull_commits_max` commits on it and push the branch.
3. Open a pull request from that branch.
4. Submit a review on it.
5. Merge it and delete the branch.
6. Open `issues_min`–`issues_max` issues and close them.

Constraints worth repeating:

- **Only repositories you own.** The tool compares the repository owner against
  the signed-in account and refuses otherwise. Automated issues and pull
  requests in someone else's project are spam.
- **No backdating.** GitHub stamps issues and pull requests at creation time,
  so an activity round only ever affects today. `--days` has no equivalent.
- **No self-approval.** GitHub rejects approving your own pull request, so
  reviews are submitted as comments, and a comment review on your own pull
  request may not register as a contribution at all.
- **It is visible.** These items sit in the Issues and Pull requests tabs with
  obviously generated titles.

If the repository has no commits yet there is nothing to branch from, so the
pull request half is skipped and only issues are opened.

## Tokens and what is stored where

Token resolution order:

1. `--token` on the command line
2. `AUTOCOMMIT_TOKEN`, `GITHUB_TOKEN` or `GH_TOKEN` in the environment
3. the token saved by `autocommit login`
4. `gh auth token`, when the GitHub CLI is installed and logged in

A token from `gh` is never copied to disk. A token you paste is written to the
token file with owner-only permissions — mode `600` on Unix, a restricted ACL
via `icacls` on Windows.

Git never sees the token in `argv` or in `.git/config`. It is passed through a
one-shot `credential.helper` that reads it from an environment variable, and
any git error text is scrubbed of the token before being shown.

| | Linux / macOS | Windows |
|---|---|---|
| Config | `~/.config/autocommit/config.json` | `%APPDATA%\autocommit\config.json` |
| Token | `~/.config/autocommit/token` | `%APPDATA%\autocommit\token` |
| Working copies | `~/.local/share/autocommit/repos/` | `%LOCALAPPDATA%\autocommit\repos\` |
| Run log | `~/.local/share/autocommit/run.log` | `%LOCALAPPDATA%\autocommit\run.log` |

`AUTOCOMMIT_HOME` moves all of it somewhere else, which is also how the tests
keep out of your real configuration.

The target repository is cloned shallow (`--depth 1`), so a large repository
does not cost a full history download.

## How contributions are counted

1. **The author email must belong to your GitHub account.** The default is
   `ID+login@users.noreply.github.com`, which always does. If you override
   `author_email`, use an address listed under *Settings → Emails*.
2. **Commits must land on the default branch** (or `gh-pages`).
3. **The repository must not be a fork.** Commits in forks never count.
4. **Private repositories count only if** *Settings → Profile → Include private
   contributions on my profile* is enabled.
5. **Backdating works** for commits, because git records the author date and
   GitHub renders the graph from it. Commits dated in a previous year show up
   in that year's graph, not today's.
6. **Issues and opened pull requests count** in repositories you own. Reviews
   of your own pull requests are unreliable.
7. The graph is cached; give it a few minutes.

`autocommit check` verifies 1–4 against the API.

## Development

```bash
python -m unittest discover -s tests -t . -v
```

137 tests, no dependencies and no network. They cover the planner and its ramp,
profiles, settings validation, token handling, the GitHub client's parsing and
error messages, all three schedulers, console dispatch and panel rendering, the
ownership guard, and full end-to-end runs — commit, push, re-clone, re-sync,
branch, pull request — against a local bare repository, with a recording fake
standing in for the GitHub API.

CI runs the same suite on Ubuntu, Windows and macOS, on Python 3.9 and 3.13,
then installs the package and drives a real console session through the
installed entry point on each platform.

Layout:

```
autocommit/
  cli.py        argument parsing and the command implementations
  console.py    the slash-command shell and the status panel
  profiles.py   the four presets
  planner.py    dates, counts and the ramp
  runner.py     turns a plan into commits
  activity.py   issues, pull requests, reviews, and the ownership guard
  gitrepo.py    the git binary, the credential helper, branches
  github.py     the REST client
  schedule.py   Task Scheduler, systemd, cron
  config.py     settings, validation, persistence
  auth.py       token discovery and storage
  paths.py      per-platform locations
  ui.py         colors, prompts, panels
```
