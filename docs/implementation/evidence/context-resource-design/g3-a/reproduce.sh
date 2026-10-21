#!/bin/sh
# Fresh disposable execution only; never opens a user's catalog.
set -eu
g3_output=${1:?usage: reproduce.sh NEW_OUTPUT_DIR}
g3_here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ -e "$g3_output" ]; then
  printf '%s\n' 'output must not already exist' >&2
  exit 2
fi
: "${G3_MIN_SQLITE_LIB:?set to external SQLite 3.51.3 shared-library directory}"
g3_min_python=${G3_MIN_PYTHON:-/usr/bin/python3}
g3_new_python=${G3_NEW_PYTHON:-python}
LD_LIBRARY_PATH="$G3_MIN_SQLITE_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
 "$g3_min_python" -c 'import sqlite3; assert sqlite3.sqlite_version == "3.51.3", sqlite3.sqlite_version'
"$g3_new_python" -c 'import sqlite3; assert sqlite3.sqlite_version_info >= (3,53,1), sqlite3.sqlite_version'
mkdir -p "$g3_output"
LD_LIBRARY_PATH="$G3_MIN_SQLITE_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
 "$g3_min_python" "$g3_here/run.py" --output "$g3_output/sqlite3513" > "$g3_output/sqlite3513.log" 2>&1
"$g3_new_python" "$g3_here/run.py" --output "$g3_output/sqlite-newer" > "$g3_output/sqlite-newer.log" 2>&1
