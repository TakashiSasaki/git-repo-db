# Context/Exchange design handoff and evidence boundary

Authority: [ADR 0030](../adr/0030-context-repository-relations-and-selective-exchange.md).
Read the [Context schema contract](../architecture/context-repository-relations.md)
and [Exchange contract](../architecture/selective-exchange-contract.md) together.

## 1. Fixed source and authorization

Design basis: `TakashiSasaki/git-repo-db`, PR #103,
`fix/access-a6-independent-review`, HEAD
`1134e200eb4ac9ec45bf3fae3be695e2bb786a8d`, effective tree
`e53755ac9fa35cd436d67afbb8810f3c6c11fdc2`.
It remains an open Draft atop #102. Main at preparation is
`b2a87cfc6562413d9ecde7f4329e90c434ae9aad`.

The current owner authorized a **design PR**, not product implementation, merging
any stack member, releasing, enabling P8, publishing Pages or changing real data.
Do not edit the parent/main branches. New implementation PRs require a subsequent
explicit instruction. Subagents may be used in that future work, with reviewer
independence and exact source bindings reported honestly.

### Decision precedence

The complete final selection ledger is in ADR 0030. In particular:

- Q-S14=B's earlier Witness-table choice was explicitly reversed **after** the
  model experiments. The final target contains claims and Dispositions only.
- Q-S15=A preserves sufficient genuine existing operation keys; its earlier
  Witness-specific PK is no longer a schema requirement. No new Witness UUID.
- Q-S16=A rules out a Witness-counterevidence table. Do not revive it as a generic
  evidence table or a `resource_relations` JSON payload.
- Q-S9=B supersedes the earlier draft SQL that accidentally included
  `represents_repository` in current-candidate pruning. That role is immutable.
- Q-S8=A supersedes earlier seven-role drafts: no `referenced_repository`, and no
  automatic PR owning/base duplicate or inherited Review/Comment Repository row.
- Context Q-S identifiers do not supersede similarly numbered Access Scope
  questions. ADR 0029's owner-confirmed Scope/locator decisions are preserved;
  its whole-ADR replacement approval remains a separate unresolved lifecycle gate.

## 2. Baseline code facts versus required changes

All paths below refer to the exact PR #103 HEAD, not the default branch's older
schema. Historical reports are not rewritten or upgraded to new implementation
acceptance by citing them here.

| Baseline path | Observed baseline | Required next implementation work |
| --- | --- | --- |
| `src/repo_catalog/adapters/sqlite/p1_ddl/context.sql` | Single `repository_uuidv4` field-candidate encoding, generated FK; 15 local CREATE TABLE statements before composition | Add two relations, retire special field/column, keep other authority and typed Resource parents |
| `src/repo_catalog/adapters/sqlite/p1_schema.py` | Composes `store_identity` and shared `coverage_claims` as well | Count/fingerprint the composed 19-table target, not just one source SQL file |
| `src/repo_catalog/domain/p1_context.py` | Whole-value canonical JSON, ResourceKey, genuine FieldClock; missing vs null | Define role/claim/Disposition values without row surrogates or implicit issuer filling |
| `src/repo_catalog/adapters/sqlite/p1_context.py` | `admit_repository` delegates to field candidates; original-time replay check; stale handling | Role-aware admission/read path, atomic trigger pruning and exact payload guards |
| `src/repo_catalog/adapters/sqlite/production_context.py` | Guarded Context facade, Source registration/known-positive membership | Expose new typed methods; preserve stop/snapshot/registration checks |
| `src/repo_catalog/domain/acquisition.py` | `DetachedResourceTransfer` is a current Repository candidate input, not proof of an actual Provider event | Distinguish real Transfer event reports from ordinary affiliation changes |
| `src/repo_catalog/application/acquisition.py` | `_admit_normalized_unit` admits one caller-supplied Repository value; generic transfer calls `admit_repository` | Do not blindly translate every registration/precondition to a relationship fact |
| `src/repo_catalog/adapters/github/production_intake.py` | Repository numeric ID normalization; PR head/base refs and OIDs; Timeline Event with genuine parent/event ID | Add actual head/base Repository Resource extraction and mapping support; do not infer it from OIDs or current affiliation |
| `src/repo_catalog/domain/exchange.py` | v3 sections include `repository_candidates`; envelope versus domain separation | New versioned role/Disposition sections, explicit R/O/C selections, bounded closure |
| `src/repo_catalog/application/exchange.py` | Single-seed admission restriction, separate Core/Context commits, receipt after processing; preserves many original fields | Q-E1--Q-E10 binding, permissions, partial units, checkpoints and Operational lifecycle |
| `src/repo_catalog/adapters/sqlite/acquisition.py` | Request issuance witnesses and Operational receipt/accounting APIs | Preserve request-witness role; do not confuse it with rejected mapping Witness persistence |
| `docs/implementation/p7-backup-recovery-technical-design.md` | Git-only/paired domain backups and fresh verified recovery | Include new Context authority and referential validation, not local check history or a new aggregate backup scope |

Repository registration metadata remains domain-only under Access separation.
Provider observations containing URLs are not silently stripped or executed.
`source_repositories` is not an issuer/authorization table and must not be merged
with Resource mapping claims. Core Reference and Coverage semantics survive.

## 3. Proposed stacked implementation sequence

These are work packages, not newly authorized changes or already-created PRs.

| Stage | Base/dependency | Deliverable and independent check |
| --- | --- | --- |
| I1: schema/domain contract | This design PR | Two Context tables, retired field path, exact keys/guards/finite JSON validators, Coverage role-scope encoding, schema fingerprint tooling; independent SQL/replay review |
| I2: Provider intake and qualified reads | I1 | Six role normalization, Provider relation preservation, genuine mapping support, original issuer/clock handling, current effect from available evidence; no Witness history |
| I3: selective Exchange | I1; integration consumes I2's supported relation codec | Versioned R/O/C selection/closure, permissions, binding/checkpoints/retry; no Access mutation |
| I4: query/search/backup integration | I2 + I3 | Accurate qualified projection, derivative rebuild/fallback and paired backup/restore tests |
| I5: independent end-to-end review | I4 assembled exact tree | Adversarial cases, preserved Core/Access boundaries, installed distributions and finite evidence report |

I2 and I3 can be developed in sibling branches after a fixed I1 interface; use an
explicit integration PR rather than combining unrelated tips implicitly. Rebase
or merge only with permission and renew exact-tree evidence after code changes.
Do not inherit #103's test counts as evidence of these future implementations.

## 4. Required counterexamples (specifications, not executed here)

1. Mapping claims A->R1 and A->R2 survive reverse arrival, replays and newer clocks;
   no merge/rekey/latest mapping winner. A new current owner at T200 prunes only
   comparable T100; equal-time value/null alternatives and unknown/different clocks
   survive. Raw supported SQL and typed methods agree.
2. Invalid role/Resource combinations, nonexistent target Repository, ordinary
   Comment transfer, PR-parented transfer and malformed parent/Event IDs fail.
   Labeled/non-transfer Timeline Events fail typed admission even if the FK passes.
3. A genuine one-sided transfer remains one-sided; two different reports never
   cross-pair endpoints; same-report conflicting endpoints remain alternatives.
   A current Issue Repository after a second transfer does not fill the first
   transfer's missing endpoint. Missing and explicit null remain distinct.
4. Existing ClaimKey with changed original observation time fails. Existing
   DispositionKey with changed observation time **or replacement ClaimKey** fails.
   Exact repeats create no new rows. Wrong-Resource replacement/partial-null
   replacement/self-correction fail. Correction cycles are explicit, not winners.
5. An unsigned same-name issuer, `source=local`, a copied Catalog UUID, a checksum
   or imported verification claim never authenticates a withdrawal. Genuine local
   evidence may qualify only the exact supported scope. Missing evidence returns
   unconfirmed without destroying the original report.
6. No Witness table/columns, operation-event UUID, verification-history relation,
   hidden generic JSON check ledger or Witness-counterevidence table appears.
   A recheck is not admitted as a new withdrawal event or a mutated Disposition.
7. Unknown Provider-to-Core mapping keeps the Provider relation and does not
   become null; changing/disputing mapping support cannot make a derived Core edge
   appear unconditionally established. Do not replace genuine Provider clocks
   with local mapping/admission/receipt time.
8. Field-to-role relocation does not turn old field Coverage into all-role
   completeness. Source positive pairs survive missing inventories and mapping
   withdrawals. Collections/groups retain original scopes and exact evidence.
9. Independent R/O/C selections, empty versus omitted filters, same shared OID,
   cyclic expansion, depth/work stops, explicit unauthorized dependencies and
   metadata-only input preserve their selected meanings in forward/reverse export.
10. Same PackageKey/digest resumes; known same key/different body fails before
    domain commit; new ID does not reset a continuing request's actual work.
    Registration only adds explicitly permitted received UUIDs; receiver seed and
    store pairing remain unchanged.
11. Valid independent units commit despite another missing dependency. No half
    atomic group, fabricated parent, durable unadmitted body or shrunken complete
    proof is introduced. Arrival order/retry does not invent new observations.
12. Crash immediately before/after each Core/Context commit and Operational
    checkpoint: actual domain state wins over absent/incomplete receipts. Binding
    races reject conflicting digests. Accounting remains cumulative after failure.
13. Operational absent or lost: explicit initialization/new request required; no
    zero-budget old-request continuation or automatic initialization. Request
    witnesses remain protected; package historical-detection limits are reported.
14. Bad incoming data versus actual stored corruption has distinct outcomes.
    Persistent P7 stops and cancellation/final completion boundaries cannot be
    bypassed by new package IDs, reconstructed Operational or mapping errors.
15. Paired backup includes all new durable Context rows/dependencies; git-only
    backup makes no Context promise. Imported/backup UUIDs and hashes are not
    issuer authentication. Access settings/approvals are not domain Exchange.
16. Product runtime, direct wheel and sdist-derived wheel use exactly the same
    finite schema/validators. All old special-field writers, readers, wire sections
    and generated indices are audited, not left as a second authority.
17. `foreign_keys`/`recursive_triggers`, REPLACE, UPSERT, rollback and conflicting
    trigger order are tested as a set. SQLite affinity never substitutes for
    strict input-type validation. Verification predicates cover enduring stored
    invariants, not only insertion-time triggers.

## 5. Experiment evidence retained by reference, not inflated

Two distinct supplied conversation artifacts informed the owner's decision. Their
reports/results were inspected and hashes recomputed while preparing this PR;
**their experiments were not rerun as product tests in this documentation task**.
Their scenario counts differ because they are different experiments, not because
one count silently supersedes another. Do not add their counts into a product
acceptance total. Both used Python 3.13.5 / SQLite 3.46.1 and synthetic audit
inputs, not the supported product-runtime/real-identity trust boundary.

| Artifact | Recorded final result | ZIP SHA-256 |
| --- | --- | --- |
| `witness-model-experiment-20261018.zip` (48,289 bytes) | 21 scenarios / 88 assertions; recorded repeat matched | `2bf0f082b24e3a4e708114c9e7066109121779b309560c9e66c4665003e8882d` |
| `witness_experiment_20261018.zip` (574,373 bytes) | 17 scenarios / 138 checks; recorded separate-process repeat matched | `d208ff1a6a6aa0510880ad402f5c205cf5df1ecfbf2afa5d174e6cccbde7a8b1` |

Selected original members and independently recomputed hashes:

| Member | SHA-256 |
| --- | --- |
| `witness-model-experiment/results/results.json` | `126505c102c9e024fd7799f6e02cb7f3c8cb79fe84cb9865248365d7d88cb5bd` |
| `witness-model-experiment/results/repeatability.json` | `0232b49e650773d6d53a0f1c681d1207452a9e1184f8a2850191b63cd9228a65` |
| `witness_experiment_20261018/results/run2/results.json` | `3b505d42ab06464a61b462a1d338ed08a74e53e0e0f5808d37a011e88ff756fb` |
| `witness_experiment_20261018/results/run3/results.json` | `127a441d7e2e96e2dd97f365f38c62e6711ffa0351de19d0e880965a0c4f3d1b` |
| `witness_experiment_20261018/results/reproducibility.json` | `25ce79c231fe32b4bb780ee991c2bcc222cc4f46dd001bcba15568a06c9cabd3` |

The artifacts are conversation attachments, **not repository paths or permanent
public download URLs**. They are not copied wholesale into this design PR; no
synthetic DB, historical alternative executable schema or experiment program is
installed as product code. A checkout retains the essential result and boundary
here, while hashes permit matching supplied originals without claiming origin
authentication. Original reports still describe Q-S14=B as unmodified because
that was correct when they were written. ADR 0030 records the later owner override;
never edit the old reports to pretend they made that decision.

### What the experiments support

With the same currently available original operation evidence and the same
revalidation rule, Disposition-only and Disposition+Witness models produced the
same current qualified effects. Later availability of evidence did not require
editing an old Disposition. Only the Witness model retained a separate historical
fact of a later local check. Generic Resource relation JSON could store that
extra fact physically, but did not give its embedded Disposition reference a real
FK and would need new semantics/authority/Exchange rules. That alternative was
not adopted.

The result is conditional on the revalidation model, not proof that Witness
storage is useless for every audit requirement. The owner chose not to require
independent past-check history. Actual local principal authentication and usable
operation identity are not supplied by either toy model. A future missing
adapter must return unconfirmed rather than fabricate evidence.

The experiments also exposed two engineering hazards: a Witness key naming the
operation cannot distinguish every later check action, and a Disposition PK does
not by itself protect its non-key replacement payload. The former is no longer a
required schema problem after dropping Witness; the latter remains a mandatory
replay guard. Neither problem is solved by inventing a UUID.

## 6. ADR and implementation consistency audit

| Existing authority | Preservation in this design |
| --- | --- |
| ADR 0003 (operative clauses) | Domain boundary, independent durable Context, immutable Core, paired backup and no fabricated observations stay binding |
| ADR 0004/0005/0006 | Metadata-only operation, common typed OID identity, attributed scalar/group boundaries retained |
| ADR 0017 | Direct semantic keys/FKs; no database-only aliases, new operation UUIDs or hash-only claim keys |
| ADR 0023/0024/0025 | Finite work, actual processing cost and cumulative original-request accounting retained |
| ADR 0026 | Persistent corruption stop, untrusted salvage and fresh validated recovery retained |
| ADR 0027 | Unauthenticated attributed origins allowed; issuer text/UUID/digest is not authentication; no new PKI requirement |
| ADR 0028 | Classified original epoch microseconds and SHA-256 envelope retained |
| ADR 0029 and Access stack | Confirmed independent Access semantics preserved; whole-record acceptance/retirement and current approval rules not changed |
| Historical single-seed Exchange implementation | Baseline behavior, explicitly replaced in the next implementation by selected Q-E semantics, not falsely claimed already corrected |

The physical SQL/codec details are reviewable proposals under fixed decisions.
Known engineering closure obligations are mapping-support qualification, exact
Coverage role scope, Provider null/current-relation encoding, finite graph unit
semantics and connection/guard consistency. These are not permission to erase
scope or source evidence. Report any genuine new architectural conflict before
implementing its dependent stage; do not make every numeric default another
owner question.

## 7. Publication verification boundary

For this design-only PR, check decision-ledger completeness, negative Witness
selection, schema-key/FK consistency, new relative links, frontmatter/index
synchronization, whitespace and the exact diff against #103. The root agent guide
already directs agents to the common ADR index; update that index, not a second
competing authority register. Do not change the Pages allowlist to publish this
new internal material as part of submission.

Remote branch/open-PR/index and ADR-path history were inspected through the
GitHub connector before allocating 0030; previous allocation watermark is 0029.
A full local clone attempt failed because the container could not resolve
`github.com`. Connector publication and exact changed-file/tree checks do not
constitute a full local history clone. No independent subagent review, product
pytest, installed distribution test, P7 qualification or full site build is
claimed by document checks. Record actual submission-time checks in the PR body.
