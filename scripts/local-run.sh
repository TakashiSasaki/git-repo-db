#!/usr/bin/env bash
# Run any command with the verified project Python first and only on PATH.
# Usage: scripts/local-run.sh pytest tests/unit/test_ci_plan.py -q
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
if [ ! -x "$root/.venv/bin/python" ]; then
    echo "local-run: no .venv; run ./scripts/setup-local-python.sh first" >&2
    exit 3
fi
exec "$root/.venv/bin/python" -I "$root/scripts/local_env.py" run -- "$@"
