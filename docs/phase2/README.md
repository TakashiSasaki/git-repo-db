# Phase 2 design reassessment: no independent Publication

**Accepted direction, whole-design revision in progress; not a completed replacement schema.**
The owner selected latest-state designs for P2-Q01/Q02/Q03 and rejected an
independent Publication under P2-Q04. Further option selection is paused while
all design areas are reconsidered for consistency. Implementation follows that
review; this documentation change does not modify runtime behavior.

Start with the [accepted decision and impact map](no-independent-publication-adr.md)
and the [current decision register](decision-register.md).

The earlier [integrated proposal](proposal-before-no-publication.md) and
[questionnaire](decision-register-before-no-publication.md) are preserved verbatim
as comparison snapshots. Their Publication-centered 69-table sketch, recommended
options and approval bundles are **not** the current target or permission to
implement. The old prototypes and receipts remain unmodified historical evidence.

## Verified baseline and authority

Main was verified at `20e0f8d78b77c6c8d37826fd6d639819631e166b`, Schema 18.
This design update is stacked on PR #22 at
`e5f7ff386b77627490a400f0a7e29d3989a9a532`. PR #23 at
`162581dfcfb501311d4993e90cdd160fb64d6e35` separately proposes Schema 19
correctness/indexing changes. Neither PR was merged at this decision checkpoint.
Recheck actual branches before later implementation; do not overwrite another
agent's work or treat the old tested tree as acceptance of this redesign.

[AGENTS.md](../../AGENTS.md) establishes explicit owner decision and accepted ADR
precedence over unapproved proposals and transitional runtime structures.
The new decision makes Q01-B/Q02-B/Q03-B and **NO_INDEPENDENT_PUBLICATION** binding.
The unresolved choices have not been approved by this document or previous CI.

## Accepted invariants, unchanged

Permanent repository/service/Source identity, natural document keys, signed int64
Unix epoch microseconds, the exact five-column Coverage claim model and its
latest-time candidate-set derivation remain fixed. Preserve required exact text,
verified Git content, typed owners/parents, actual module/version attribution,
per-field evidence, missing/null/empty distinctions, incomparable conflicts,
Issue transfer provenance, receiver-local checks and CAS-41.

Latest-state storage does not imply receipt-order wins, automatic deletion on
scan absence, discarding conflicts, or a GC/retention policy. Necessary evidence
must not be an undeclared complete history of superseded PR/comment/roster values.
Saved API originals, retired replay and parser-profile authority must not return
under a new container name.

## Evidence: live dependency chains, not grep conclusions

The existing [dependency inventory](dependency-inventory.json),
[source analysis](dependency-source.json.gz), [field inventory](field-contract.json)
and [conditional disposition](schema-disposition.json) describe the investigated
Schema 18 checkpoint. The five [publication](workstreams/publication.md),
[completeness](workstreams/completeness.md), [acquisition](workstreams/acquisition.md),
[fields](workstreams/fields.md) and [Exchange](workstreams/exchange.md) workstreams
are useful evidence of callers and failure cases. Their recommended replacement
Publication topology and still-open lifecycle assumptions require revision.

The new ADR maps these dependencies to independently meaningful duties. It does
not assert that every production path has already been retraced or that a new
DDL has been proven. Static references, statement preparation, executing a
synthetic case and full runtime acceptance remain different kinds of evidence.

## Integrated target architecture

The fixed architectural constraint is **no independent Publication entity or
subsystem**, including a renamed generic bundle/seal with the same ownership and
eligibility role. No common `publication_id` is required merely to record that
a transaction committed.

Review the model by independent responsibilities: resource identity/current value;
actual field provenance and unresolved candidates; database atomic update;
collection scope/completeness; Git objects/acquisitions/targets; operational
concurrency/restart; receiver domain validation; and retained-content maintenance.
The presence and exact shape of any further persistent evidence require a domain
justification, not an assumption that the old Publication manifest must survive.

No new final table count, generic collection seal, checkpoint journal, current
winner rule or Exchange trust policy is selected here. In particular, Q05 does
not automatically inherit the old fragment-receipt recommendation.

## Transactions, predicates and deletion dependencies

A committed local transaction can expose a coherent update without an independent
Publication record. It cannot by itself establish the completeness of an API
list, nested child set, multi-transaction Git import or a received transfer.
Review those predicates separately and preserve their real domain constraints.

`Store.publish()` currently increments `database_identity.publication_seq`.
That counter supports local revisions/fencing and is not an independent domain
Publication. Classify and preserve the necessary concurrency semantics before
renaming or removing anything. Similarly, catalog installation and a Git/collection
completion condition are not automatically forbidden by their current names.

Audit Publication/result FKs, manifests, read gates, exchange closure, generated
JSON/SQL guards, staging and package tests together. Delete the independent
mechanism in a coordinated replacement; do not use an empty input manifest,
dummy Fetch, hidden history or compatibility Publication to satisfy old checks.

## Independent review, prototypes and performance

The old [independent review](independent-review.md),
[Exchange addendum](review-exchange-addendum.md), [evidence ledger](verification.md)
and probes remain checkpoint evidence only. Passing the old candidate does not
validate a no-Publication architecture. Do not modify its raw receipts to make
historical runs appear to cover revised inputs.

The reassessment must challenge rollback and post-commit failure, partial and
empty collections, same-time/stale evidence, sparse field origins, Source-scope
mismatch, changed PR head/base, partial/reordered Exchange, incomplete Git object
relations and shared-byte corruption. Review proposed evidence for hidden history
or a renamed Publication. Capture new exact fingerprints for revised prototypes.

## Implementation sequence after decisions

The previous Publication-first approval bundles are superseded. The sequence is:

1. Freeze the accepted no-Publication and latest-state direction (this decision).
2. Reassess the entire model, update dependencies and evidence requirements, and
   record genuine unresolved issues without continuing the multiple-choice sequence.
3. Independently review the integrated no-Publication model and its counterexamples.
4. Reflect the reviewed design across schema/writer/reader/Exchange/maintenance in
   coherent, substantial implementation PRs, preserving settled correctness.

No new option choice, merge or release is authorized here. There is no migration
or intermediate-working-state requirement, but final integrated correctness is
required. If a genuinely undecided semantic question blocks a sound replacement,
report the specific issue rather than inventing a policy.

## Reproduction and evidence scope

The original reproduction commands and limitations are preserved in
[the earlier proposal](proposal-before-no-publication.md#reproduction-and-evidence-scope)
and [verification ledger](verification.md). They reproduce that checkpoint, not
this redesign. New code-bearing work must use the actual latest repository tools,
synthetic disposable catalogs, exact-tree ordinary/package acceptance and honest
failure/skip reporting.

This change records design authority, revises the active overview/register and
preserves old materials. No runtime tests, implementation of this redesign,
merge, live acquisition, migration, retained-data deletion or deployment is
claimed by the document itself.
