# autocommit

[![tests](https://github.com/Bedohly/auto-commit/actions/workflows/ci.yml/badge.svg)](https://github.com/Bedohly/auto-commit/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.8%2B-blue)
![platforms](https://img.shields.io/badge/platforms-linux%20%7C%20macos%20%7C%20windows-lightgrey)

Create randomized, backdated commits in a GitHub repository you own — on a
schedule, on Linux, macOS and Windows.

You sign in once, pick (or create) a target repository, and the tool appends a
line to a log file and commits it a few times a day. Days are picked at random,
so the result is not a perfectly uniform block of green.

```
:: PLAN  2026-08-01 -> 2026-08-14
   2026-08-01    3  ###
   2026-08-02    1  #
   2026-08-04    5  #####
   2026-08-05    2  ##
   ...
   28 commits across 11 active day(s) out of 14
```

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

```bash
autocommit login                      # sign in (or reuse the gh CLI login)
autocommit select                     # pick or create the target repository
autocommit run --dry-run --days 30    # preview a month, change nothing
autocommit run                        # commit and push today's batch
autocommit schedule --at 20:00 --jitter 90
```

Running `autocommit` with no arguments opens an interactive menu with the same
actions.

## Commands

| Command | What it does |
|---|---|
| `autocommit login` | Verify a token and save it. `--token-only` skips the `gh` CLI. |
| `autocommit logout` | Delete the saved token. |
| `autocommit status` | Token, repository, settings, schedule and health checks. |
| `autocommit repos` | List repositories you can push to. |
| `autocommit select [owner/repo]` | Choose the target. `--create NAME` makes a new one (`--public` to make it public). |
| `autocommit config` | Edit settings interactively. `--show` prints them. |
| `autocommit run` | Build a plan, create the commits, push. |
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
6. The graph is cached; give it a few minutes.

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

62 tests covering the planner, config, token handling, the GitHub client, the
schedulers, and a full end-to-end run — commit, push, re-clone and re-sync —
against a local bare repository. Nothing in the suite talks to github.com. CI
runs the same suite on Ubuntu, Windows and macOS.

## A note on what this is

This inflates your own contribution graph with commits that are not real work.
Anyone who clicks a green square sees a log file with one-line edits, so treat
it as decoration, not as a portfolio. Point it at a repository you own, and
don't use it against a repository somebody else relies on.

## License

MIT — see [LICENSE](LICENSE).
