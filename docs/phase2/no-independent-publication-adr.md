# Decision: no independent Publication; reassess the whole design before implementation

- **Decision status:** Accepted explicit owner decision, 2026-10-10.
- **Implementation status:** Not implemented by this document. Whole-design reassessment comes first; runtime changes follow it.
- **Questionnaire status:** Further P2 option selection is paused. Do not resume at Q05 or treat recommendations as approved.
- **Scope:** No independent Publication entity or subsystem in the target core, together with the already accepted latest-state choices below.
- **Documentation base:** PR #22 at `e5f7ff386b77627490a400f0a7e29d3989a9a532`.
- **Verified main:** `20e0f8d78b77c6c8d37826fd6d639819631e166b`, Schema 18.
- **Separate implementation under review:** PR #23 at `162581dfcfb501311d4993e90cdd160fb64d6e35`, Schema 19. It contains earlier contract corrections, not this redesign.
- **This change:** Documentation and task boundaries only. No production DDL, parser certificate, tests, CLI, data, branch base or merge is changed.

## 1. Accepted decisions and their precedence

This is the current decision overlay for the earlier [Phase 2 proposal](README.md)
and [question register](decision-register.md). Those files and their executable
69-table sketch retain value as investigated alternatives, but their
Publication-centered architecture is no longer the target. Their original
recommendations and blanket Pending status must not override the owner choices:

| Question | Accepted choice | Precise meaning |
| --- | --- | --- |
| P2-Q01 | B | PR state is the latest accepted state plus genuinely necessary evidence, not a retained sequence of previous attribute values. |
| P2-Q02 | B | PR title/body, conversation comments and independent thread state use latest accepted values plus necessary evidence; ordinary Issue/review current contracts remain unchanged. |
| P2-Q03 | B | Source Inventory uses the current known roster plus necessary scoped completeness/provenance/conflict evidence, not a general historical-value query service. |
| P2-Q04 | **NO_INDEPENDENT_PUBLICATION** | No independent Publication entity or subsystem. This supersedes the earlier deferral and Publication-assuming A/B alternatives; do not depend on a mutable option letter. |
| P2-Q05 onward, including Q08-S/G and Q10-T | **Selection paused; reassess** | No additional alternatives are approved. Reevaluate their wording, necessity and dependencies under the four accepted decisions before further choices or implementation. |

Latest accepted state does not mean last-received-wins. Preserve genuine
incomparable conflicts, field provenance and typed identity. Necessary evidence
is not permission to recreate every superseded value as hidden history. These
choices do not establish a retention period, automatic deletion/GC, or a rule
that a repository absent from a scan has been deleted.

The transport-independent core ADR (TP-01–TP-08), scoped R1–R7 retirements,
permanent repository/service/Source identities, natural document keys, signed
int64 epoch microseconds, Coverage v2, domain text/Git content and CAS-41 remain
binding where not explicitly superseded. Parser provenance remains actual module
name/version, not selection authority or verification certificates as a target.

## 2. What is excluded from the target

Do not introduce `repository_publications`, `source_publications`, independent
Publication UUIDs, Publication member registries, generic Publication seals,
Publication dependency graphs or a `publish` transition that every ordinary
resource must pass through before it can be used.

Do not retain the same abstraction under `batch`, `bundle`, `receipt`, `generation`
or a family-specific Publication name merely to preserve old input/output-manifest
machinery. A persistent object must have an independently stated domain or
operational responsibility, not merely represent that a transaction committed.

The decision is architectural, not a lexical deletion rule. It does not prohibit
all identifiers, every grouping of records, domain-specific completeness evidence,
or every occurrence of the word `publish`. It does not itself remove Git objects,
collection scope, conflict candidates or the ability to build and install a
validated catalog. Each remaining construct must justify its meaning without
using an independent Publication as its owner or eligibility authority.

## 3. Responsibilities that must be separated

| Responsibility | Design-review direction under this decision | What must not be inferred |
| --- | --- | --- |
| Local all-or-nothing changes | Use the existing database transaction facilities and explicit failure handling for a coherent update. Identify actual write boundaries. | A commit does not prove that a remote list was fully enumerated, or that several separately committed operations form one complete snapshot. |
| Resource validity and ownership | Validate the resource's own identity, owner, fields, relationships and applicable conflict rules. Review direct typed relations instead of mandatory Publication ownership. | Deleting an FK to Publication does not authorize unowned data or arbitrary current winners. |
| Current-state freshness | Preserve comparable provider clocks, actual capture context, absent/null distinctions and actual per-field parser origins. | A transaction sequence, parser version or local receipt time is not a provider revision. |
| Collection completeness | Retain the existing semantic requirement that partial is not complete. Determine the minimum domain scope/member/terminal/child information needed without a Publication premise. | Q05 fragment versus final-set layout, permanent per-page receipts and new collection seals have not been selected. |
| Git/code consistency | Identify the actual object/acquisition/ref/target relation and the conditions under which its derived results are usable. | No universal Publication layer is required simply because a Git object produces several relational rows. A partially populated tree is not complete. |
| Restart and concurrency | Separate job/checkpoint/fencing state from durable resource eligibility. Review failure before commit, after commit and between acquisition steps. | Q07 cache policy or Q12 checkpoint placement is not decided by dropping Publication. |
| Exchange | Recompute the required domain relationships and receiver checks for actual retained records, not for sender Publication manifests. | A local transaction boundary is not a portable proof, and a sender digest is not provider authenticity. The final wire/trust policy remains unselected. |
| Backup and catalog installation | Preserve verified retained content, quarantine accounting and atomic installation/no-overwrite protection. | Filesystem installation, catalog lifecycle validation and domain Publication are not identical concepts. |

SQLite provides transaction control and isolates uncommitted writes between
ordinary separate connections. That supports local atomic updates, not semantic
collection completeness or cross-catalog transaction replay. A constraint error
must be handled according to the actual transaction state; do not assume any
error automatically rolls back the whole unit. See the primary SQLite
[transaction](https://www.sqlite.org/lang_transaction.html) and
[isolation](https://www.sqlite.org/isolation.html) documentation.

## 4. Initial whole-design impact map

This is a responsibility reassessment map, not an unconditional DROP list and
not a claim that a complete replacement schema has already been verified.

| Area | Existing or proposed dependency | Required reassessment |
| --- | --- | --- |
| Phase 2 candidate schema | Independent Repository/Source Publications, seals, output-member unions and Publication-owner FKs in `prototypes/candidate.sql` | Withdraw this topology as the target. Preserve the old sketch/receipts as an identified comparison snapshot; derive a fresh no-Publication model. Do not subtract a few tables and call the remainder approved. |
| PR/document/thread current values | Historical rows owned by `parsed_result_uuidv4`, fetch-origin references and selected-result readers | Integrate Q01-B/Q02-B: current values, real field evidence, direct typed owners, unresolved conflicts and necessary target references. Do not preserve discarded old bodies merely to validate an old seal. |
| Source Inventory | `_publish_inventory`, Source result/input/publication membership and historical roster queries | Integrate Q03-B without making a Source scan Repository-owned. Preserve scope and partial-scan honesty. No delete-on-absence policy is chosen. |
| API persistence | `ApiFacts.page/result/ownership/publish`, saved-original input manifests and pending results | Separate parsing, domain admission, local transaction completion and progress. Remove the independent result-publication role in the eventual replacement; do not rename it. |
| Parser infrastructure | `parsed_results`, `parsed_result_inputs`, `parsed_result_publications`, Profile/Fact selection tables and published/usable views | Classify every responsibility and consumer. Retire generic publication/selection authority under the accepted target, while retaining or reexpressing legitimate ownership, conflicts and incomplete-domain constraints. Current runtime still needs a coordinated replacement. |
| Git ingestion and analysis | `GitImporter`, `GitParsing`, result-owned commits/parents/trees/tags/snapshots, `git_acquisition_publications`, root manifests | Distinguish verified object facts, observed refs/roots, derived decoding and partial acquisition. Review the meaning of each completion marker; neither blanket deletion nor a new Git Publication wrapper is authorized. Git interpretation lifecycle beyond existing decisions remains unresolved. |
| Collections/Coverage | `fetch_collections`, current page receipts, completion markers, memberships and `Graph.aggregate_proof/proof_requirements/code_proof` | Remove Publication as a conceptual prerequisite. Review what proves each requested scope without saved HTTP originals; preserve exact five-column claims and latest-time derivation. No new evidence layout is selected here. |
| Exchange/staging | Publication roots, typed dependency closure, original authorization, late promotion and conflict barriers | Replace only generic publication dependencies; keep actual domain ownership, data integrity and unresolved dependencies/conflicts. Audit reverse arrival, partial transfer, re-export and mixed versions without silently approving Q10. |
| Local catalog revision | `Store.publish()`, `database_identity.publication_seq`, `Store.revision()` and pagination/live-acquisition fences | The checked implementation increments a local revision counter, not an independent domain Publication. Preserve the concurrency/staleness responsibility; a later rename must follow all consumers. Do not drop it by name alone. |
| Catalog building and restore | `database_identity.lifecycle`, target validation and atomic file installation | Keep physical catalog readiness separate from an individual resource's validity or a collection's completeness. Preserve CAS-41 and no-overwrite behavior. |
| CAS/content | `stored_bytes`, `payloads`, Git links, exact text and quarantine | Remove API-original roles only as their consumers are replaced. Retain genuine domain bytes and shared-digest integrity. This is not authority for physical deletion of existing user data. |
| Tests/docs/generated contracts | Publication-dependent fixtures, generated JSON/SQL guards, handoffs, phase2 proposal and acceptance assumptions | Preserve tests for still-required outcomes, rewrite only superseded mechanism assertions after the new design is checked, and label historical proof honestly. All retained references and generated artifacts must match the new contract when implementation occurs. |

Checked anchors include [Store](../../src/repo_catalog/adapters/sqlite/store.py),
[ParserModel](../../src/repo_catalog/adapters/sqlite/parser_model.py),
[GitHub persistence](../../src/repo_catalog/adapters/github/persistence.py),
[collection service](../../src/repo_catalog/application/collection_service.py),
[Git parsing](../../src/repo_catalog/adapters/git/parsing.py),
[current receipts](../../src/repo_catalog/adapters/sqlite/current_collections.py)
and the Phase 2 [publication workstream](workstreams/publication.md).

## 5. Reevaluate the remaining questions, do not answer them by implication

Q05/Q06 must stop assuming an upstream Publication exists. Q07/Q12 must describe
operational cache/checkpoint duties independently of resource ownership. Q08 must
not reinstate Parser Result selection merely to replace Publication. Q09 must
remove hidden full-response/value-history assumptions. Q10 must distinguish
retained current values, necessary historical evidence, domain dependencies and
sender claims without a Publication envelope as authority. Q11 must preserve real
domain content and avoid turning the redesign into an unapproved GC operation.

The earlier four approval bundles and Publication-first implementation ordering
must be rebuilt. No question should ask the owner to reconsider Q01-B/Q02-B/Q03-B
or independent-Publication rejection. Review may identify genuine unresolved
requirements, but must report them as such, not continue the sequential multiple-
choice interview or silently pick a previous recommendation.

An operational export envelope or a collection-specific identity may still have
a real purpose. Its necessity, lifetime and constraints must be explained without
creating a general persistent commit-group owner. Neither existence nor removal
of such specific records is automatically approved by this decision.

## 6. Concrete consistency cases for the redesign

1. **Partial multi-page acquisition:** P1/P2 are valid and committed; the next page
   fails. The valid current resources remain usable where their own constraints
   permit; the requested list is not complete. No Publication UUID is needed to
   express either fact. Exact receipt layout and transaction size remain review work.
2. **Failed multirow update:** updating a comment and its provenance fails midway.
   The chosen transaction boundary must prevent a committed value with mismatched
   producer/clock evidence. Test both failure before commit and retry after commit.
3. **Current-value drift:** a PR was head A at 100 and is now B at 200. A retained
   code assessment for A cannot be relabeled as about B, or require the whole old
   PR/body to survive merely because a Publication once owned it. Justify the
   minimal exact code-target evidence under the latest-state policy.
4. **Sparse parser output:** an older body survives a newer title-only update.
   Attribute each retained value to its actual producer and clock, not the latest
   transaction or one generic bundle header.
5. **Inventory interruption:** a complete roster had R1/R2; a later partial scan
   sees R1 only. Do not infer R2 deletion or a complete later roster. Preserve
   Repository identity separately from Source membership and scan assessment.
6. **Partial/reordered transfer:** a receiver gets a child without its parent, or
   some members without sufficient completion evidence. It cannot gain complete
   status by committing its import transaction. Review actual domain dependencies
   and pending/conflict behavior without a Publication manifest.
7. **Large Git load:** a process commits a prefix of tree/parent/ref data and stops.
   The prefix cannot masquerade as the complete requested Git scope. Determine the
   narrow domain-specific predicate without creating a new generic publication phase.
8. **Revision versus freshness:** incrementing local `publication_seq` must continue
   to invalidate stale local pagination/live fences where required, but cannot make
   a provider value newer. Two catalogs need not share that counter.
9. **Old evidence without old values:** no accepted-value history was retained.
   A digest can identify a witnessed value but cannot reconstruct it or recompute
   it from a different current value. Do not solve this by reintroducing an edit log.
10. **Malicious or inconsistent evidence:** count/hash agreement alone cannot prove
    that a sender enumerated the provider honestly. Preserve current validation
    guarantees; the paused Q10 trust decision is not implicitly settled.

## 7. Work sequence and review completion criteria

### First: whole-design reassessment

Trace producer/store/consumer paths across the actual latest runtime and the old
proposal. Classify each affected table, column, FK, JSON reference, view, trigger,
CLI/service entry point and test as: remove independent Publication role; retain
independent domain/operational responsibility; reexpress under accepted choices;
or genuine unresolved requirement. Static hits alone do not prove a live use.

Rewrite the active overview, decision status, candidate schema and implementation
dependency plan coherently. Keep immutable historical evidence intact and use a
new fingerprint for any revised prototype. Do not call the old 69-table sketch a
no-Publication design or promise its table count as the final outcome.

Review the integrated model, not separate renamed tables. Use independent
reviewers/subagents and executable synthetic counterexamples where available.
Check local atomicity, field evidence, bounded collection and Git consistency,
Exchange ordering, missing dependencies and shared-byte integrity. Do not equate
an empty fresh `foreign_key_check` with proof of all domain behavior.

This reassessment is complete only when no active candidate requires independent
Publication ownership/eligibility, no settled latest-state choice has become
hidden history, every removed responsibility has an explicit disposition, and
remaining uncertainties are disclosed without selecting a new owner policy.
Report the actual review/prototype scope; this ADR itself is not that proof.

### Then: reflect the reviewed design in implementation

Use the decision/review documentation as the baseline for substantial, coherent
implementation PRs. Coordinate schema, writers, readers, current/conflict handling,
collection/Git checks, Exchange, operational fences, maintenance and packaging.
Temporary breakage during development and incompatible fresh schemas are allowed;
final correctness and tested integration are required. No migrations, dummy fetches,
compatibility Publications or renamed generic commit ledgers are required.

Remove old Publication/result/selection dependencies only with their surviving
consumers coherently addressed. Run the applicable full ordinary and isolated
wheel/sdist suites, generated-contract checks, FK/integrity and independent
regressions against the exact submitted tree. Record preserved current guarantees,
changed mechanism assertions, failures/skips/unexecuted checks and remaining scope.
Do not use a successful old PR to claim acceptance of the new architecture.

If a genuine new owner-level semantic choice is unavoidable, identify that
specific issue during reassessment rather than inventing an answer. The current
instruction pauses additional selections and requires review before implementation;
it is not permission to leave correctness undefined in production.

## 8. Repository integration boundary

This documentation change is stacked on PR #22 so the original investigation is
available for review. It does not rewrite PR #22/#23 branches or merge them. PR
#23's earlier bug fixes/indexes and Schema 19 remain separately reviewable; they
neither implement nor approve the old independent-Publication proposal.

This document records the accepted direction and an initial full-design impact
map. It does not claim that all revised DDL, domain validators or replacement
Exchange behavior have been implemented, independently reviewed or tested. No
runtime change, full acceptance, migration, live acquisition, release or merge
is performed or authorized by this documentation PR.
