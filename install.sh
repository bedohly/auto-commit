#!/usr/bin/env sh
# Install autocommit on Linux or macOS.
#
#   ./install.sh
#
# Tries pipx first, then "pip install --user", then a private virtualenv.

set -e

RED=""
GREEN=""
YELLOW=""
RESET=""
if [ -t 1 ]; then
  RED="$(printf '\033[31m')"
  GREEN="$(printf '\033[32m')"
  YELLOW="$(printf '\033[33m')"
  RESET="$(printf '\033[0m')"
fi

say()  { printf '%s:: %s%s\n' "$GREEN" "$1" "$RESET"; }
warn() { printf '%s!! %s%s\n' "$YELLOW" "$1" "$RESET"; }
die()  { printf '%sXX %s%s\n' "$RED" "$1" "$RESET" >&2; exit 1; }

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------- checks ---
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
      PYTHON="$candidate"
      break
    fi
  fi
done
[ -n "$PYTHON" ] || die "Python 3.8 or newer is required. Install it and run this script again."
say "Using $($PYTHON --version 2>&1)"

command -v git >/dev/null 2>&1 || die "git is required. Install it and run this script again."
say "Using $(git --version)"

# --------------------------------------------------------------- install ---
INSTALLED=""

if command -v pipx >/dev/null 2>&1; then
  say "Installing with pipx..."
  if pipx install --force .; then
    INSTALLED="pipx"
  else
    warn "pipx failed, falling back to pip."
  fi
fi

if [ -z "$INSTALLED" ]; then
  say "Installing with pip (--user)..."
  if "$PYTHON" -m pip install --user --upgrade . 2>/dev/null; then
    INSTALLED="pip"
  else
    warn "pip refused to install into the user site (PEP 668 or no pip)."
  fi
fi

if [ -z "$INSTALLED" ]; then
  VENV="${XDG_DATA_HOME:-$HOME/.local/share}/autocommit/venv"
  say "Creating a private virtualenv at $VENV..."
  "$PYTHON" -m venv "$VENV" || die "Could not create a virtualenv. Install python3-venv and retry."
  "$VENV/bin/pip" install --upgrade pip >/dev/null
  "$VENV/bin/pip" install --upgrade . || die "Installation failed."
  mkdir -p "$HOME/.local/bin"
  ln -sf "$VENV/bin/autocommit" "$HOME/.local/bin/autocommit"
  INSTALLED="venv"
fi

# ------------------------------------------------------------------ done ---
say "Installed via $INSTALLED."

if command -v autocommit >/dev/null 2>&1; then
  say "$(autocommit --version)"
else
  warn "autocommit is not on your PATH yet."
  warn "Add this to your shell profile, then open a new shell:"
  printf '\n    export PATH="$HOME/.local/bin:$PATH"\n\n'
fi

cat <<'NEXT'
Next steps:

    autocommit login      # sign in with a GitHub token (or reuse the gh CLI)
    autocommit select     # pick or create the repository to commit into
    autocommit run --dry-run --days 14
    autocommit schedule --at 20:00 --jitter 90

NEXT
