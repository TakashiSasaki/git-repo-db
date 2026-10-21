#!/bin/sh
# Optional external runtime setup; no repository dependency/runtime modification.
set -eu
u3_runtime_dir=${1:-/tmp/u3-sqlite-runtime}
mkdir -p "$u3_runtime_dir"
curl --fail --location --silent --show-error \
  https://www.sqlite.org/2026/sqlite-autoconf-3510300.tar.gz \
  -o "$u3_runtime_dir/sqlite-autoconf-3510300.tar.gz"
printf '%s  %s\n' \
  81f5be397049b0cae1b167f2225af7646fc0f82e4a9b3c48c9ea3a533e21d77a \
  "$u3_runtime_dir/sqlite-autoconf-3510300.tar.gz" | sha256sum -c -
tar -xzf "$u3_runtime_dir/sqlite-autoconf-3510300.tar.gz" -C "$u3_runtime_dir"
cd "$u3_runtime_dir/sqlite-autoconf-3510300"
./configure --prefix="$u3_runtime_dir/minimum" --enable-threadsafe --enable-shared --disable-static
make -j2
make install
"$u3_runtime_dir/minimum/bin/sqlite3" --version
LD_LIBRARY_PATH="$u3_runtime_dir/minimum/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  /usr/bin/python3 -c 'import sqlite3; assert sqlite3.sqlite_version == "3.51.3", sqlite3.sqlite_version; print(sqlite3.sqlite_version)'
