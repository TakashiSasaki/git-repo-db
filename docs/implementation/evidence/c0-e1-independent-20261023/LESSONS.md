# Proposed lesson for ci-final-tree-verification

This is a recommendation for a later skill update; the reviewed tree and existing
skills remain unchanged. The repository `lessons-to-skills` procedure was applied.

To test an exact compressed receipt boundary without replacing the ZIP writer,
vary synthetic input bytes and observe the actual production `body` after its ZIP
context closes. Require the archive handle to be closed, valid DEFLATED members,
CRC, exact measured length, index/hash and binding. Then execute the complete CLI
and separately inspect process exit, stdout and stderr. A construction probe that
stops before the size predicate must never count as a boundary verdict.

Input-prefix length does not map monotonically one-to-one to final ZIP length:
the member digest and compressed JSON index change too. The first attempt here
exhausted a length-only search at limit+1. The working search changes a recorded
random seed on cycles and then tunes length again. Calibration exit 99 is explicit
and separate from the final full CLI observations. No ZIP comments, padding,
length mocks, limit changes or patched archive writers are involved.

A target-only Python trace must return its local trace on the target frame's
**call** event before it can observe line events. Returning None there caused the
second helper attempt to miss `body`; it did not establish a product failure. Avoid
tracing every line of base64/textwrap internals. The final helper uses a read-only
observer during full CLI execution and includes an uninstrumented overflow control.

Reproduce with `verify_boundaries.py --output NEW_EMPTY_DIRECTORY` from the pinned
review checkout. `raw/boundaries/measurements.json` records every successful final
observation, seed/length calibration attempts and the direct CLI control. Failed
helpers and their logs remain under `raw/`. This technique applies to this emitter's
stdlib ZIP path; it is neither general authenticity proof nor hosted overflow or
artifact-upload execution evidence. Never apply it to real private input artifacts.
