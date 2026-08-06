#!/bin/bash
# CapyGo Bot launcher.
#   ./run.sh                        -> open the app (GUI)
#   ./run.sh pet-armament-chest ... -> run a task on the command line
# On first run it creates .venv and installs dependencies.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "First run: setting up .venv and installing dependencies..."
  python3 -m venv .venv
  ./.venv/bin/python -m pip install -q --upgrade pip
  ./.venv/bin/python -m pip install -q -r requirements.txt
fi

if [ "$#" -eq 0 ]; then
  exec ./.venv/bin/python -m ui.app       # no args -> launch the GUI
else
  exec ./.venv/bin/python run.py "$@"      # args  -> run a task via the CLI
fi
