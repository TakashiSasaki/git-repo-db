# Access A1 executable review receipt

This is a design-review fixture, not production Access or independent-agent approval.
Baseline design: `cf90c093089911acbfd3c8c2c7778a9ff8904bc6`.
Main baseline: `b2a87cfc6562413d9ecde7f4329e90c434ae9aad`.
Parent: [A1 contract](../access-a1-contract.md).

## Executed evidence

| Check | Result |
| --- | --- |
| Contract suite | 57 passed, 0 failed, 0 errors, 0 skipped |
| SQL mutation experiments | 6/6 detected: five invariant assertion failures and one FK defense |
| Contract run UTC | 2026-10-17T11:32:38.584928+00:00 to 2026-10-17T11:32:38.744420+00:00 |
| Python | 3.13.5 |
| SQLite binding | 3.46.1 (below product P1 minimum 3.51.3) |
| WAL/backup case | Actual disposable file-backed WAL snapshot and Backup API, history preservation and grant removal |
| Product runtime / network / credentials | Not invoked |

The earlier 51-case run passed. Six additional cases cover atomic registration/
control insertion, reapproval, full preference parents, missing assignments, no-op
updates and REPLACE. Mutation run 1 found five assertion detections plus a FK
rejection, initially classified as an error rather than an assertion detection.
Run 2 explicitly classifies that redundant FK barrier; it does not hide or alter
the initial receipt and does not claim a production bug was fixed.

| Source file | SHA-256 |
| --- | --- |
| `schema_probe.sql` | `183d530bdea93fc0fa0d671076179ecc12f6be27fa14ef82fed59acd9e7a197b` |
| `contract_probe.py` | `cc2fae1df9df728f71d4a72d4e4a06a299270365fda16c215f91491d01ada9a0` |
| `mutation_probe.py` | `13aaedfffd258f1186c606105d71fecb245bec86c6890248023206d59a86ef32` |

Reproduce using the commands in the A1 contract. The scripts write optional JSON
and JUnit evidence to caller-selected output paths; those outputs are not normal
product state. Standard-library unittest tests are explicitly invoked, not added
to the product default suite. They do not import `repo_catalog` or packaged DDL.

## Limits and unexecuted work

Local clone failed DNS resolution. The starting three documents were verified
against known Git blobs from PR metadata, not a full source checkout. This SQLite
version validates the modeled relational behavior only: no supported-P1 PASS,
performance budget, crash/power-loss durability, actual transport sandbox, proper
credential resolution, process authentication or human approval UI is claimed.
The external activation boolean and fixture JSON are stand-ins, not secure product
APIs. No broad pytest, full-checkout MkDocs, wheel/sdist or independent agent ran.
Final hosted CI is separately checked against the published commit.

The author performed source review, SQL/probe implementation and mutation analysis.
A different test entry point does not make that review independent. See the
[review handoff](../access-adr-replacement-review.md#independent-review-work-packet).
