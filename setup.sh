#!/usr/bin/env bash
# FireWatch environment setup (Mac/Linux).
# Creates a Python 3.11 venv and installs requirements.txt.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "python3.11 not found. Install Python 3.10 or 3.11 (plan.md section 4.1 — not 3.12)." >&2
    exit 1
fi

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Setup complete. Activate with: source .venv/bin/activate"
echo "Then verify with: python scripts/verify_env.py"
