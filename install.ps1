# Install autocommit on Windows.
#
#   powershell -ExecutionPolicy Bypass -File .\install.ps1

$ErrorActionPreference = "Stop"

function Say  ($text) { Write-Host ":: $text" -ForegroundColor Green }
function Warn ($text) { Write-Host "!! $text" -ForegroundColor Yellow }
function Die  ($text) { Write-Host "XX $text" -ForegroundColor Red; exit 1 }

Set-Location -Path $PSScriptRoot

# ----------------------------------------------------------------- checks --
$probe = "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"
$python = $null

foreach ($candidate in @(
    @{ Exe = "py";      Prefix = @("-3") },
    @{ Exe = "python";  Prefix = @() },
    @{ Exe = "python3"; Prefix = @() }
)) {
    $command = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
    if (-not $command) { continue }
    & $command.Source @($candidate.Prefix + @("-c", $probe))
    if ($LASTEXITCODE -eq 0) {
        $python = @{ Exe = $command.Source; Prefix = $candidate.Prefix }
        break
    }
}

if (-not $python) { Die "Python 3.8 or newer is required. Install it from python.org and retry." }

function Invoke-Python {
    param([string[]] $Arguments)
    & $python.Exe @($python.Prefix + $Arguments)
}

Say "Using $(Invoke-Python @('--version'))"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Die "git is required. Install Git for Windows (https://git-scm.com) and retry."
}
Say "Using $(git --version)"

# ---------------------------------------------------------------- install --
Say "Installing with pip (--user)..."
Invoke-Python @("-m", "pip", "install", "--user", "--upgrade", ".")
if ($LASTEXITCODE -ne 0) {
    Die "pip failed. Run 'python -m ensurepip --upgrade' and try again."
}

# ------------------------------------------------------------------- done --
if (Get-Command autocommit -ErrorAction SilentlyContinue) {
    Say (autocommit --version)
} else {
    $scripts = Invoke-Python @("-c", "import site, os; print(os.path.join(site.USER_BASE, 'Scripts'))")
    Warn "autocommit is not on your PATH yet. Add this folder to PATH:"
    Write-Host ""
    Write-Host "    $scripts"
    Write-Host ""
    Warn "Until then you can run it as: python -m autocommit"
}

Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Host "    autocommit login      # sign in with a GitHub token (or reuse the gh CLI)"
Write-Host "    autocommit select     # pick or create the repository to commit into"
Write-Host "    autocommit run --dry-run --days 14"
Write-Host "    autocommit schedule --at 20:00 --jitter 90"
Write-Host ""
