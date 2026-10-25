#!/usr/bin/env bash
# One-command local setup: verified complete Python + project .venv + receipt.
# The starting python3 only orchestrates (stdlib, 3.9+); it never runs product code.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
starter=${GIT_REPO_DB_BOOTSTRAP_PYTHON:-$(command -v python3 || true)}
if [ -z "$starter" ] || ! "$starter" -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
    echo "setup-local-python: a python3 >= 3.9 is needed only to start the bootstrap" >&2
    exit 2
fi
exec "$starter" -I "$root/scripts/setup_local_python.py" "$@"
