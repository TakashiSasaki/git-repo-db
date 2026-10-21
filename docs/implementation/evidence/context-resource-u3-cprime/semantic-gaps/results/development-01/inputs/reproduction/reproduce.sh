#!/bin/sh
# Reproduce both baseline and candidate on two real SQLite runtimes.
# Runtime distributions and databases stay outside the repository.
set -eu
u3_repo=$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.." && pwd)
u3_output=${1:?usage: sh reproduce.sh /absolute/external/output-directory}
mkdir -p "$u3_output"
u3_output=$(CDPATH= cd -- "$u3_output" && pwd)
case "$u3_output/" in "$u3_repo/"*)
  echo 'Use an output directory outside the repository.' >&2
  exit 2 ;;
esac
u3_runtime=${U3_MIN_RUNTIME:-/tmp/u3-sqlite-runtime}
u3_current_python=${U3_CURRENT_PYTHON:-python}
u3_min_python=${U3_MIN_PYTHON:-/usr/bin/python3}
u3_scripts="$u3_repo/docs/implementation/evidence/context-resource-u3-cprime/reproduction"
cd "$u3_repo"
if [ ! -f "$u3_runtime/minimum/lib/libsqlite3.so" ]; then
  sh "$u3_scripts/baseline-build-minimum.sh" "$u3_runtime" > "$u3_output/runtime-build.log" 2>&1
fi
export PYTHONPATH="$u3_repo/src${PYTHONPATH:+:$PYTHONPATH}"
"$u3_current_python" "$u3_scripts/baseline-runtime.py" > "$u3_output/baseline-current.json"
"$u3_current_python" "$u3_scripts/run.py" --output "$u3_output/current"
LD_LIBRARY_PATH="$u3_runtime/minimum/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$u3_min_python" -c 'import sqlite3; assert sqlite3.sqlite_version == "3.51.3", sqlite3.sqlite_version'
LD_LIBRARY_PATH="$u3_runtime/minimum/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$u3_min_python" "$u3_scripts/baseline-runtime.py" > "$u3_output/baseline-minimum.json"
LD_LIBRARY_PATH="$u3_runtime/minimum/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$u3_min_python" "$u3_scripts/run.py" --output "$u3_output/minimum"
