# Verified procedural lessons and recommended skill maintenance

The frozen reviewed product, Accepted ADRs, historical evidence and existing
skills are unchanged. This independent review recommends the following addition
to `.agents/skills/ci-final-tree-verification/SKILL.md`; the current review does
not claim an Author correction or silently rewrite older SQLite recipes. ADR0032
governs this execution, including where older skill examples select an engine.

## Complementary missing chunks in two GitHub log views

The #151 Access run's downloaded log ZIP contains a combined log and the actual
receipt-emission step log. Each omits a different 120-character base64 DATA
chunk. Each individually decodes to 1,947,999 bytes rather than the original
1,948,089 bytes; neither has the declared digest. Do not accept either stream,
guess the missing characters or merely tolerate a byte/hash mismatch.

For an already-readable supported log ZIP, compare the ordered DATA sequences
from the combined and step views. Only insert an actually observed chunk at an
unambiguous matching boundary; reject conflicting replacements. Require equal
BEGIN/END claims, the original declared length and SHA256, and every indexed
member length/hash before using the recovered receipt. Do not call this a
successful download of the larger artifact.

`recover_access_receipt.py.txt` independently implements this procedure and
recovers the original receipt SHA256
`0847e6e5445d0d3726bda2020b2438a1b7ee2ac85da4931aced08055fc6199ea`.
All 121 indexed payloads match. `test_receipt_recovery.py.txt` separately refuses
a chunk absent from both views, a conflicting observed chunk and a false original
hash; `ci/receipt-recovery-negative-controls.json` retains all three actual exits.
`ci/author-access-marker-integrity.json` keeps the two original failed verifications.
The procedure is unsuitable when both views lack the same chunk, any conflict is
ambiguous, or the final original digest does not match.

## Contract checks before normalizing or performing preparatory work

For codec review, compute the canonical received dictionary digest independently
before invoking domain constructors. Mutate set-array duplicates and ordering
with an unchanged digest across decoded/text/byte carriers. An internal roundtrip
through the same normalizing serializer cannot expose M02.

For planner review, provide already validated but entirely unselected rows with
zero and exhausted cumulative budgets. Instrument actual embedded-parser calls,
not only emitted unit counters. The 24 measurements and three failed assertions
under `planner/` expose M01 despite globally finite hard caps. These are verified
diagnostic lessons, not a verified product fix or authority to relax R04.

## Keep receipt instrumentation independent of test monkeypatches

This runtime embeds `_sqlite3`, so `__file__` is absent; record `__spec__.origin`
and its actual `sqlite_source_id()` rather than obtaining another engine.
Tests can temporarily patch shared `json.dumps`; a report hook that invokes that
patched symbol may fail after the test's call phase and before fixture teardown.
Bind the observer's original serializer before tests run, verify the affected
controls, retain interrupted receipts, and rerun the complete invocation. Partial
JUnit files and progress counts do not establish a completed ordinary run.
