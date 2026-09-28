#!/bin/sh
# Start Smart Explorer from source. The first run sets up .venv and downloads
# the libraries; later runs go straight to starting the app.
cd "$(dirname "$0")" || exit 1

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  echo "Smart Explorer needs Python 3.9 or newer. On a Mac, run: xcode-select --install" >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "Creating .venv..."
  python3 -m venv .venv || exit 1
fi

# Install only when requirements.txt changed since the last good install.
if ! cmp -s requirements.txt .venv/installed-requirements.txt; then
  echo "Installing libraries (about 40 MB the first time, so give it a few minutes)..."
  # A current pip, and ready-made wheels over newer source releases. Apple's
  # Python 3.9 ships pip 21, which otherwise tries to compile pyobjc and fails.
  if .venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip &&
    .venv/bin/python -m pip install --disable-pip-version-check --prefer-binary -r requirements.txt; then
    cp requirements.txt .venv/installed-requirements.txt
  else
    echo "Installing libraries failed (see above), so Smart Explorer was not started." >&2
    exit 1
  fi
fi

echo "Starting Smart Explorer..."
exec .venv/bin/python desktop.py
