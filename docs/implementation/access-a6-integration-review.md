# A6a integrated Access review and callback-handoff hardening

Status: main-agent integration review, NOT independent review or merge acceptance.
Base: PR #101 `444dcecf38f5db3cccdb4716c7c8c6b584543475`, effective tree
`2db6023f98a6e5947e470950ecc78ee290280bc2`. Work began 2026-10-18 10:25:24 JST.
The owner requested continuation; no merge, P8 activation, release, deployment,
real-data operation or whole-record ADR retirement was requested or performed.

Read the [accepted Scope choices](../adr/0029-independent-access-store.md),
[A1 contract](access-a1-contract.md), [A5 report](access-a5-backup-restore.md),
and [ADR replacement review](access-adr-replacement-review.md). They have distinct
approval/implementation/evidence scopes. An old successful receipt is not a current
PASS after implementation changes.

## 1. New finding and correction

A6-H01: `AccessWorkflow.dispatch_reviewed_once` checked deadline, guard and grant
before invoking the bound executor. The real `BoundLocalDirectory.invoke` then
performs another filesystem evidence check. If expiry, revocation, a new default
registration or cancellation occurred during that final check, the application
callback still started. Both public dispatch APIs shared this path.

Eight new deterministic counterexamples failed on the unmodified A5 implementation
with DID NOT RAISE (zero setup errors). The tests use the actual bound-directory
adapter and Access SQLite database, injecting the concurrent change at the last
filesystem evidence call. The defect is an application-admission timing gap, not
a claim that an arbitrary remote attack has been demonstrated.

The callback handed to the executor now rechecks guard, session/deadline and the
exact grant AFTER executor preparation and checks time again after the DB read.
The token is still single-use and the descriptor is closed on rejection. The
existing callback-already-in-flight semantics, original request/budget coordinates,
ranking-before-permission, exact registration key and all five DDLs are unchanged.
This narrows the reproduced gap; it does not provide cross-process linearizability
or instantaneous cancellation of an already-started callback.

## 2. New cross-stage scenarios

`tests/integration/access/test_stack_acceptance.py` exercises both Git SHA-1 and
SHA-256 with actual local repositories:

- Acquire a non-seed repository, back up Access, restore inactive, reject work
  before route enablement and local reapproval, then resume the original request.
  Existing Core facts stay exact; actual cumulative work increases.
- Fork restored settings into a new Scope. Preserve original Scope history and
  disable copied settings; after explicit setup/approval refuse to retarget the
  old request. A genuinely new capture/request can acquire the same Repository UUID.
- Register stored HTTPS/SSH alternatives and rotate a profile after real local
  acquisition. Repository identity and existing Core facts remain unchanged;
  no remote execution is implied by storing the alternatives.
- Remove or stop Access after real acquisition. Independently sound Core metadata
  remains readable with no Access initialization or repair.

The ten cases passed at the initial integration checkpoint. One initial fixture
asserted a CoreFailure code against its human message; it was corrected to inspect
`error.code`, with no change to product rejection semantics.

## 3. Requirement ledger and execution reconciliation

[The machine-readable ledger](access-a6-acceptance.json) preserves the 26 numbered
requirements and links 48 actual test functions. Its status is scoped to the finite
Linux opt-in implementation: **23 covered within that scope, 2 partial, 1 deferred**.
"Covered" does not claim all transports, all possible attacks, independent review
or release qualification. The ledger audit checks names and recorded evidence;
semantic review of assertions remains necessary.

| Item | Incomplete part and next boundary |
| --- | --- |
| 11 | Native/Notes additional-repository acquisition works. General external GitMetadataInput and Exchange remain seed-scoped; full multi-repository interchange is not certified. |
| 15 | Routing/classification is implemented, not a legacy real-data extraction tool. No real catalogs were read or migrated. |
| 16 | Exact-source/installed-distribution verification is separate from independent review, whole-ADR acceptance and full release testing. |

Do not remove these gaps simply to obtain a green ledger. No unresolved earlier
Scope question is reopened: Q-S1-Q-S4 A, Scope UUID-only identity, same-table Locator
history and MAX(original time) remain inputs.

`scripts/audit_access_acceptance.py` verifies exact requirement text/IDs, test-source
functions and explicit incomplete scopes. With paired collection/JUnit inputs it
also rejects failed/skipped/missing/substituted/duplicate nodes and missing linked
tests. A matching hash/receipt is consistency evidence, not sender authentication
or proof of an independent reviewer. Seventeen audit-counterexample tests exercise
these boundaries.

```sh
python scripts/audit_access_acceptance.py
python scripts/audit_access_acceptance.py \
  --junit artifacts/access-registry/tests.xml \
  --collection artifacts/access-registry/collected.txt
```

## 4. ADR consistency and retirement gate

The current tree still contains accepted ADR 0003 and proposed ADR 0029. Scope
choices are explicitly accepted by the owner within 0029; its status does not yet
accept the COMPLETE replacement of 0003. The [governance policy](../adr/policy.md)
requires an accepted successor, preserved operative clauses, coherent index/link
updates and retirement in one reviewed change. A coding continuation is not a
substitute for whole-record acceptance or a merge request.

The existing carry-forward map was reread against the COMPLETE source, including
all six acceptance criteria. Preserve metadata-only versus checked-byte admission,
Core INSERT-only/retention, independent Context evidence/Source semantics, actual
capture/claim provenance, cross-store failure truth, correct-source Search behavior,
finite cumulative work, P7 stop/fresh restore and domain-backup scopes. Apply the
already accepted ADR 0014/0026/0028 scoped refinements; do not revive obsolete body
archival, quarantine counters or signed observation-time rules.

This review clarifies requirement 12 in the companion design: continuity restore
DOES preserve UUID/history, but not the other environment's execution binding or
approval. The prior shorthand "scopes ... are not inherited" could contradict the
explicitly selected continuity rule. This is wording reconciliation, not a new
Scope lifecycle choice. No accepted ADR is removed or substantively rewritten.

The exact source archive is now available, unlike the earlier index-only review.
An exhaustive filename-reference scan found 25 files (26 occurrences), including
three immutable distribution receipts. Per-file hashes are retained in the A6
evidence. Distinguish current links/procedures from historical narratives and
immutable distribution receipts. Those receipts must not be rewritten to remove
an old ADR filename from the historical package manifest.

Still required before accepting the whole replacement:

1. An independent reviewer must check the operative carry-forward, not approve a
   clause table on its own. Cite any unpreserved clause before deleting 0003.
2. Record explicit whole-replacement acceptance and its actual date. Set 0029's
   status accordingly, update its index and current incoming links, retire 0003
   coherently, and close only that policy migration-debt entry.
3. Preserve historical execution receipts. Review active root/agent documentation
   for four-store summaries, without implying P8/default activation or expanding
   the public website source allowlist.

## 5. Evidence and limits

The A5 source artifact SHA-256 and complete Git tree were independently recomputed
by the main agent before editing; this is verification, not an independent agent.
Actual local SQLite is 3.51.3 with its official source ID. The untouched 1,767-case
risk cohort passed with four inherited Python-3.13 P7 fork warnings. New local
checkpoints: 8 handoff regressions + existing 63 workflow cases passed; 10 cross-stage
cases passed; 17 ledger consistency tests passed. Final combined execution and
hosted evidence must be bound to the final candidate tree in the PR/evidence bundle.

An initial virtualenv did not inherit the outer environment's pytest installation.
An explicit source-overlay/tools path corrected setup without disabling the
repository's network guard or changing product checks. The failure log is retained.
Local package-network access is unavailable; do not fabricate local MkDocs or
installed-wheel results. Hosted verification may run the existing allowlisted
MkDocs builder using --no-mermaid: it inserts placeholder diagrams, so success
would validate staging/links/templates, NOT fresh Mermaid rendering or publication.
Internal Access design files are not automatically in that site's public allowlist.

No subagent or independent reviewer was available/launched. A6a is NOT A6 completed.
The complete default-runtime release suite and real hardware power-cut scenarios
remain outside this developer validation task. No real user catalog, credential,
backup or deployment is operated on.

## 6. Independent review packet

Review the final PR HEAD and actual parent #101; use the exact tested tree, not a
moving branch. Independent subagents are permitted with disjoint ownership:

- Identity/history reviewer: audit the 26-item ledger against assertions; attempt
  timestamp ties/replay, scoped uniqueness, restore/fork and fixed request identity.
- Execution reviewer: reproduce A6-H01 without this test fixture, check grant and
  filesystem handoff, cancellation, original budgets and exact-source read guards.
- ADR reviewer: read all 0003 clauses and 0029's operative successors, inspect the
  exact incoming-reference inventory, and report replacement readiness separately
  from design choices, tests and merge authorization.

Record start/end time, commit/tree, commands and observed failures. Do not alter the
reviewed tree, merge, activate P8 or claim independence for author-run tests/CI.
Return severity, exact source lines, minimal reproduction and remaining scope.
Reusable lesson: [final executor handoff](../../.agents/skills/three-store-invariants/references/final-executor-handoff.md).
