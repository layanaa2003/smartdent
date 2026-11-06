#!/usr/bin/env bash
# SmartDent - one-command start for Mac and Linux:   ./start.sh   (or: bash start.sh)
# First run: creates .venv, installs the packages (needs internet, about 1 GB, 5-15 minutes),
# creates the database with demo logins, then opens SmartDent in your browser.
# Later runs start in a few seconds and work offline.
set -e
cd "$(dirname "$0")"

echo
echo "  SmartDent - AI assistant for panoramic dental X-rays"
echo "  ----------------------------------------------------"
echo

fail() { echo; echo "  $1"; echo; exit 1; }

# 1. Find Python 3.10 or newer (tested versions first).
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3.14 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
[ -n "$PY" ] || fail "Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ and run ./start.sh again."

# 2. Create the private Python environment (.venv) the first time.
if [ ! -x .venv/bin/python ]; then
  echo "  [1/4] Creating the Python environment with $PY ($("$PY" --version 2>&1))"
  "$PY" -m venv .venv || fail "Could not create .venv. On Ubuntu/Debian run: sudo apt install python3-venv"
else
  echo "  [1/4] Python environment found."
fi
.venv/bin/python -c "import sys" >/dev/null 2>&1 ||
  fail "The .venv folder is broken (perhaps copied from another computer). Delete it and run ./start.sh again."

# 3. Install the packages, only when requirements.txt changed since the last install.
if ! cmp -s requirements.txt .venv/requirements.installed; then
  echo "  [2/4] Installing packages. The first time this downloads about 1 GB and can take 5-15 minutes..."
  EXTRA=""
  # On Linux the default PyTorch download includes large GPU libraries; the CPU build is enough.
  [ "$(uname -s)" = "Linux" ] && EXTRA="--extra-index-url https://download.pytorch.org/whl/cpu"
  .venv/bin/python -m pip install --upgrade pip --disable-pip-version-check -q || true
  .venv/bin/python -m pip install -r requirements.txt --disable-pip-version-check $EXTRA ||
    fail "Installing the packages failed. Check the internet connection and run ./start.sh again. See Troubleshooting in README.md."
  cp requirements.txt .venv/requirements.installed
else
  echo "  [2/4] Packages already installed."
fi

# 4. Create the database, with demo logins if it is empty.
echo "  [3/4] Preparing the database..."
.venv/bin/python scripts/seed.py --demo

# 5. Start SmartDent and open it in the browser.
echo "  [4/4] Starting SmartDent. Demo logins are in README.md. Press Ctrl+C to stop."
exec .venv/bin/python run.py --open
