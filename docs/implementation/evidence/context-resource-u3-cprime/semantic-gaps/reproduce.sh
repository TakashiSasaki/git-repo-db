#!/bin/sh
# Full prior author/baseline scenarios plus focused semantic-gap cases.
set -eu
gap_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
gap_output=${1:?usage: sh reproduce.sh /absolute/external/output-directory}
sh "$gap_dir/../reproduction/reproduce.sh" "$gap_output"
gap_runtime=${U3_MIN_RUNTIME:-/tmp/u3-sqlite-runtime}
gap_python=${U3_CURRENT_PYTHON:-python}
gap_min_python=${U3_MIN_PYTHON:-/usr/bin/python3}
"$gap_python" "$gap_dir/probe.py" --output "$gap_output/focused-current"
LD_LIBRARY_PATH="$gap_runtime/minimum/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$gap_min_python" "$gap_dir/probe.py" --output "$gap_output/focused-minimum"
