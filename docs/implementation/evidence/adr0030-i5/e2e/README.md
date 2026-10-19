# Independent I5 synthetic end-to-end acceptance

Product input is HEAD `a54cb218226e3c91c44e979ee0df0543ea459502`, tree
`cc2eafaaeb8e3305270c17e74ae69edc42c0a50b`. The new independently authored
`tests/integration/i5/test_independent_e2e.py` SHA-256 is
`af34964d3c8ea508006dca403b825486d12e2acd74c622faf837c8314a240a26`.
No production file changed for these scenarios. Parent I5 submission and its final
commit/tree binding must be recorded separately after these files are committed.

`acceptance-02.xml` and `acceptance-02.log`: **20 collected, 20 executed,
20 passed, 0 failed, 0 error, 0 skip, 0 xfail, 0 xpass, 0 unexecuted**.
Python **3.13.5**, actual SQLite **3.51.3**; exact source ID, interpreter,
command and environment are in `acceptance-summary.json`. Ruff check and format
check passed. `collection.log` retains every collected node.

The new tests build an actual local synthetic Git repository with retained
commit/tree/notes and two Repository captures sharing OIDs, use new native
REST/GraphQL Provider payloads through I2, export/import v4 across different
Catalog seeds through I3, then read/search and fresh paired restore through I4.
Only the low-level native Git-object builder and store initializer are reused
from earlier tests. Assertions and payloads are I5-owned.

Coverage:

- Eight disjoint R/O/C combinations plus omitted-vs-explicit-empty/all selectors;
  selected Context and shared OID dependencies never register an unselected
  Repository even when receiver permission includes it. Source inventory adds
  an independent positive-membership and atomic Coverage selection probe.
- Conflicting Mapping ClaimKeys and each withdrawal/correction/dispute cross
  the wire. Sender qualification is compared with receiver qualification only
  when genuine transient evidence is supplied. Plain receiver/restore reads
  remain unconfirmed. Search built under a different qualification cannot alter
  the operation's current view. Complete Disposition and replacement keys persist.
- The newer unresolved Issue owner excludes the historical mapped Core owner
  from current Query filters while retaining that old Core relation. Explicit
  NULL and omitted ownership remain distinct. PR base/head remain independent.
- Genuine one-sided reports with the same Event Resource and different original
  observation/provenance do not mix endpoints. Two-ended Transfer is withheld
  whole under permission cuts; non-Transfer `labeled` creates no Transfer.
  GraphQL Node Repository identity stays unresolved despite a matching decimal
  `databaseId`; an explicit NULL opposite endpoint stays NULL. All EventReportKeys
  and endpoints survive full reception unchanged.
- Received Search is tested missing, invalid SQLite bytes, stale snapshot,
  forged text, and a same-count forged key on an actual matching candidate.
  Every affected search returns authority-scan results, rebuild restores a
  verified projection, Context stays byte-semantically identical, and derivative
  corruption never creates P7 Stop.
- The fresh paired restore probe populates **every one of 19 Context tables**,
  including correction/replacement, terminal collection Coverage, Source inventory
  Coverage, Source membership, Provider text, both PR OID references and Transfer.
  It compares all columns/generated columns, ordered full PK descriptors and full
  row multisets; it also compares all original Capture/Notes rowsets and retained
  commit bytes. FK/schema validation passes. Operational, Search and Access files
  are absent after restore, and the Access canary never appears in the backup.

Efficiency: two bounded xdist workers and a closed immutable synthetic template
copied per scenario avoid repeated Git acquisition while sharing no mutable
Catalog. Quiet output is retained in full logs; 35.57 seconds is a concurrent run,
not a sequential benchmark.

Historical `development-*` logs remain test-harness development records, not
product acceptance. They include wrong API/table assumptions, missing fixture
imports, invalid FK fault injection and sqlite.Row repr-order comparison. Each
was corrected in the independent tests without product changes. `acceptance-01`
was 19 passed/1 failed because its forged-key mutation targeted a document outside
the queried candidate set; matching candidates remained sound, so fallback was
not required. The corrected actual-matching-candidate counterexample passed
individually (`row-key-focused`: 1 passed/19 deselected), then all 20 passed in
`acceptance-02`. No product defect is established by these development failures.

This is focused E2E evidence only. Broader existing test reconciliation,
crash/budget/recovery boundaries, genuine Access-grant probes, distribution
isolation, ancestry, hosted CI and the independent read-only final review are
separate I5 evidence. It authorizes no main merge, release, real-Catalog operation,
credential access or P8 activation.
