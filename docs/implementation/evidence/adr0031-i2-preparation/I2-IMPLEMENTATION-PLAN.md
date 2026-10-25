# ADR 0031 I2 implementation preparation

Prepared 2026-10-21 UTC. **Design reconciliation and disposable prototypes only.**
No product source, packaged DDL, fingerprint, test, existing branch, PR metadata,
accepted ADR or real catalog was changed. No merge, release, P8 or live Provider
operation was performed. This preparation is not an independent approval of its
own proposed implementation; the future implementation requires non-author review.

## 1. Frozen dependencies and inspected sources

Live GitHub API and `git ls-remote` agree:

| Object | Commit | Tree / state |
|---|---|---|
| main | `cb532242c7aa86c6af5b6232b71c0906ea38f5c5` | `318ad07874ab436206e6a61f231b308a421cfc54` |
| I1a #116 | `d92377599a50f192f534836fc12402a5fe87ca83` | same tree as main; merged |
| I1b #117 | `32e5d4de67c0d436f7583d04e1cfd349b64b2bbd` | `708c860cd4badd4d787d4d8140b9626c80813be6`; Draft/open, base main |
| validation #118 | `9ea69ba8804a368802457950601a5a4027174c52` | `8183f346b3613ea1206b2c0ab3e6428f31614cd8`; Draft/open, base #117 |

Use **#118's exact effective tree** as the development dependency, after separate
implementation authorization. It includes I1b plus the reviewed active fixture
and distribution-input repairs. #117 alone still has obsolete collection inputs.
No old experimental branch is an implementation dependency. Recheck refs before
branch creation; neither a historical tree nor this plan grants merge authority.

The detached preparation clone is at #118; all **3,697 tracked file hashes**
match before/after final SQL execution and its tracked status is clean. The
original shared checkout is also unchanged. `source-binding.json`, `live-refs.txt`,
`pr-{116,117,118}.json` and `checks-{117,118}.json` retain the bindings. Both open
PRs have successful Development (`offline`) and failed Access
(`registry-sqlite-3513`) checks. Those are existing checks, not checks of this plan.

Read AGENTS, ADR index, ADRs 0017/0028/0029/0030/0031, the complete Resource
schema contract, implementation handoff, C-prime integration map, G3=A candidate
Resources/predicates/reference constraints and independent review, I1
implementation report, codec and boundary reviews, #118 closure/evidence, and
the later Task B independent report. Historical status statements in G3=A's
README/reviews precede ADR acceptance; they do not reopen the accepted decision.
The handoff's old product/main and PR-state coordinates are historical, not live.

Inspected actual `p1_ddl/context.sql`, `p1_schema.py`, reference and production
Context adapters, ResourceObservation/ports, GitHub intake, namespace consumers,
query/Search, recovery constraint validation, fingerprint generation and P1–P7
packaging fixtures. The product DDL, not the experiment, is the change baseline.

## 2. Exact I2 contract and physical proposal

The complete executable proposal is [resources.sql](resources.sql),
[resource_udfs.py](resource_udfs.py) and [compose_proposal.py](compose_proposal.py).
The full proposed composed SQL is `minimum/composed.sql` / `newer/composed.sql`,
SHA-256 **`c8fd84cf5e535d5f4c585d31a2e0ad0e4c791bb9cd7649f243e0bc1c6bfd223e`**.
It replaces only the Resource section, adjusts the existing endpoint FK target,
and adds the temporary fail-closed Transfer fence described below. It is **not
implemented or packaged product DDL**.

Keep `STRICT, WITHOUT ROWID` and direct BINARY TEXT primary key:

```sql
PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id)
```

Retain canonical UUIDv4 validation and the Provider FK. Replace the closed kind
enum with the existing nonempty-kind rule. Use exact comparison against the
empty string rather than SQLite length(), whose NUL termination would silently
reject some nonempty kind strings accepted by ResourceKey. No registry, prefix, tag, hash, row ID,
new UUID, key discriminator or fourth key coordinate is introduced. Unknown kinds
remain service-scoped and opaque; reserved common names still invoke known rules.
Other tables' six-role/type constraints are retained verbatim.

Replace `parent_resource_kind` / `parent_provider_resource_id` in Resources with
`identifier_namespace_kind` / `identifier_namespace_id`. Retain `document_kind`
and `provider_document_id`, changing the latter's representation to canonical
identity TEXT. These four non-key columns describe **native identification**, not
an attributed relationship. There is **no namespace/Parent-existence FK**.

| Row form | Namespace kind / ID | Subtype | `provider_document_id` | Required key |
|---|---|---|---|---|
| Independent non-Document / unknown kind | both NULL | NULL | NULL | any complete `J(V)` |
| Provider-global `document` | both NULL | NULL | non-NULL `J(V)`, equal to full key ID | `J(V)` |
| PR-scoped `document` | `pull_request` / `J(PR)` | actual nonempty subtype | non-NULL `J(D)` | `J(["pull_request",J(PR),subtype,D])` |
| `review` | `pull_request` / canonical ID | actual nonempty subtype | `J(D)` | same scoped profile |
| `thread` | `pull_request` or `review` / canonical ID | actual nonempty subtype | `J(D)` | same scoped profile |
| `comment` | `pull_request`, `issue`, `review` or `thread` / canonical ID | actual nonempty subtype | `J(D)` | same scoped profile |

`V`, namespace identity and `D` may be strings or recursive arrays, including
meaningful empties. Native-local `""` is SQL TEXT `"\"\""`; native `[]` is TEXT
`[]`. Neither is SQL NULL. The outer scoped key has its own complete I1 budget:
a local value that fits by itself may make the containing key exceed its budget.
Refuse the complete key; do not truncate or stringify the local value.

There is exactly one scoped profile: slot two is the canonical namespace **TEXT
inside a JSON string**, not its decoded array. Slot four is native `D`, while
`provider_document_id` stores `J(D)`. Do not pass its serialized TEXT as native D.
SQL validates complete metadata and exact reconstruction using the I1 codec.
No all-omitted Document, partial scoped contract or invalid-known opaque fallback
is admitted. SQL validates the declared contract; it cannot authenticate a
Provider's completeness, native contract or meaningful-singleton assertion.

### Global arrays shaped like scoped encodings

For `V=["pull_request",J("7"),"body","D"]`, the global and scoped factories
produce the same triple. The global row has `(NULL,NULL,NULL,J(V))`; the scoped
row has `("pull_request",J("7"),"body",J("D"))`. These are two **declarations
about one key**, not two keys or two simultaneously admissible entities.

Initial admission accepts either complete declaration selected by a genuine
native adapter contract. Exact replay with the same metadata deduplicates.
Changing declarations for an existing triple is an identification conflict and
fails before conflict shortcuts. A DB cannot determine the truthful first
declaration from array shape. If a native adapter claims two different entities
under the same triple, its native namespace/identity contract is incomplete;
surface that counterexample rather than adding a storage discriminator or choosing
an arrival winner. There is no automatic global-to-scoped promotion.

Persist and load the complete metadata. A bare triple carries identity, not an
identification declaration. Never reconstruct metadata by guessing array shape,
`_document_contract`, `asdict(ResourceKey)`, `replace`, set retention or arrival.
I2 closes local stored/API reconstruction; I6 must carry the declaration through
its versioned wire. A wire reader without it must refuse the affected unit.

### Row-local UDF contract

| Function | Contract |
|---|---|
| `p1_resource_identity_v1(TEXT) -> INTEGER` | Exactly 1 iff I1 `parse_identity` accepts the exact serialized TEXT; otherwise 0. SQL NULL/BLOB/forbidden or noncanonical TEXT never returns NULL. |
| `p1_resource_identification_v1(kind,id,ns_kind,ns_id,subtype,local_id) -> INTEGER` | Exactly 1 iff the full row obeys the form table, each identity component passes I1, and scoped reconstruction exactly matches the key. Otherwise 0, never NULL. |

Both use `deterministic=True`, do no DB lookup, external I/O, clock access,
configuration-dependent normalization or registration search. Move their pure
validation into the domain module proposed below; the SQLite wrapper only maps
typed invalidity to 0. Unexpected runtime failures fail the statement; do not
catch every exception and fabricate valid input. Keep the generic `p1_json`,
`canonical`, `p1_array` and Exchange digest serializers unchanged.

I1's inclusive limits are 262,144 canonical ASCII bytes, 32 array containers on
a path and 4,096 total value nodes. Exact types, scalar Unicode, canonical
spelling and prescan-before-decoding all come from I1. The functions' work is
bounded by the individual identity limits and a constant number of metadata
components; enclosing row/request/package work budgets still apply. SQLite's
TEXT callback materialization and original Python/JSON types are separate limits;
DDL cannot prove pre-affinity input types. Keep strict native API validation.

Versioned SQL names bind these semantics into the DDL fingerprint. A future
material change to limits/semantics requires a coherent versioned DDL/UDF contract,
new fingerprints, tests and review; a stable SQL hash alone does not attest an
unchanged Python function body. Record package/source hashes as well.

### CHECK, trigger and replay contracts

Use explicit `=1` CHECKs. The BEFORE INSERT guard validates the entire row and
then compares all four non-key columns with `IS NOT` against an existing exact
triple. A contradictory row raises `ABORT` before PK/UNIQUE handling, including
IGNORE, DO NOTHING, REPLACE and UPSERT. Checking `SELECT 1` and returning early
from `ContextStore.resource` is insufficient.

Retain existing `resources_no_update` and `resources_no_delete` guards at product
lines 182–183; they already protect identification evidence. No new Context-wide
mutation policy is needed. Identical UPDATE/UPSERT-update and REPLACE may remain
refused. Normal exact replay uses validated INSERT ... DO NOTHING or explicit
full-metadata comparison. Recursive triggers are required for REPLACE protection.
Other current-state tables keep their existing mutation/pruning policies.

`RAISE(ABORT)` is statement atomicity, not automatic rollback of a caller's earlier
statements. Wrap each supported domain unit in the existing savepoint. A failed
deferred COMMIT leaves the transaction active until explicit rollback. Do not
catch a failure and commit a partial typed unit. No reverse-set commit hook or
whole Transfer guarantee is supplied by I2.

## 3. Indexes, FKs and the intermediate Transfer fence

All declared key/reference/projection columns and corresponding PK/UNIQUE/FK
comparison use BINARY. SQLite uses parent collation for FK comparison; inspect
actual `index_xinfo`, not just column names. Keep exact service and kind components.

| Existing dependency | I2 action / later owner |
|---|---|
| Resources' Provider FK | retain; add explicit UUID CHECK on Resource service too |
| Resources self-FK on old Parent columns | remove; identifying namespace existence is not Resource admission |
| `resources_typed_event_fk` five-column UNIQUE | replace with `(triple,reference_document_kind,identifier_namespace_kind)` for staged legacy endpoint typing |
| New `resources_document_contract_fk` | `(triple,reference_document_kind)`; I3 source FK supports globals with a non-NULL absence projection |
| New `resources_native_event_fk` | `(triple,reference_document_kind,identifier_namespace_kind,identifier_namespace_id)`; exact I4 target, not an I4 constraint by itself |
| Endpoint five-column FK in `resource_repository_relations` | reference the new five-column UNIQUE; keep all role CHECKs and full triple FK; fence Transfer writes until I3–I5 replace support semantics |
| `field_candidates`, `resource_relations`, `collections`, `core_references`, `coverage_scopes` triple FKs | preserve exact ordered three columns and semantics; their parent table is still Resources |
| `repository_mapping_dispositions` ClaimKey/replacement FKs | retain; claims remain in the existing relation table |
| `rrr_by_repository`, `rrr_current_clock`, `rrr_event_report`, mapping indexes | retain; no role, clock, provenance or pruning change |
| Coverage Collection/terminal/scope/proof FKs and five claim columns | retain; no sixth column or inferred completeness |

`reference_document_kind = coalesce(document_kind,'')` is a generated non-key
typed absence projection. An independent Document's future source FK must include
the empty marker rather than NULL, which would exempt a composite FK. It is not
an ID tag. The full mandatory row predicate is what permits that marker only for
the complete global declaration. Generated columns are never independently writable.

The five-column index is transitional; drop it in I4 only after its last FK is
replaced. The four- and six-column indexes have explicit distinct consumers.
Keep required exact UNIQUEs rather than partial indexes or a wider superset that
does not match the referenced key. Wide index cost is accepted, not a reason to
add a surrogate.

**Intermediate safety choice:** removing the universal Parent FK changes what
the old endpoint type FK establishes. It now binds identification only. I2 must
not silently claim it still proves an attributed semantic Parent report. The
prototype adds `i2_transfer_stage_fence`, an unconditional BEFORE INSERT refusal
for both Transfer roles, including no-op replay shortcuts. Add the matching
typed API refusal. This is a temporary engineering fence, not a new accepted
Transfer rule. Remove it only with reviewed I3/I4/I5 support/admission replacements.
Alternatively integrate the complete reviewed I2–I5 stack as one effective tree;
never expose an unfenced partially rewritten Q-S10 path.

Do not add a Parent FK back to Resources to retain old tests. Complete child
identity must survive a missing namespace/Parent. I3 owns referent FKs on actual
reports; Parent arrival creates no report. No report payload queue is introduced.

## 4. Precise file-level implementation plan

Paths below are repository-relative and are **future edits**, not changes made
by this preparation. Keep one coherent packaged schema commit per frozen stage.

| File | Exact implementation work |
|---|---|
| `src/repo_catalog/domain/resource_identification.py` (new) | Immutable non-key ResourceIdentification value, explicit global/scoped/unscoped factories, storage decoder and the pure row validation above. Bind metadata to the same ResourceKey; no fourth equality coordinate. |
| `src/repo_catalog/domain/p1_context.py` | Re-export/use identification value where needed. Keep ResourceKey constructor, equality/hash/triple, native factories and I1 codec unchanged. Do not make a shape decoder choose global/scoped intent. |
| `src/repo_catalog/domain/production_context.py` | Carry `identification` in ResourceObservation. Require it for Document/review/comment/thread observations; validate key agreement. Plain unscoped kinds may use the all-NULL form. No evidence/time changes. |
| `src/repo_catalog/domain/ports/p1_context.py`, `domain/ports/production_context.py` | Add an explicit keyword identification argument to `resource`; expose checked metadata lookup. Match exact keyword names in reference/production facades and tests. Preserve optional repository registration precondition. |
| `src/repo_catalog/adapters/sqlite/p1_context.py` | Register both versioned deterministic functions. `resource` accepts the explicit identification value, validates before any duplicate lookup, and writes a named seven-column INSERT. Compare the complete stored declaration on replay. Return existing API result semantics. |
| `src/repo_catalog/adapters/sqlite/production_context.py` | Propagate observation metadata; checked metadata reads; `_members` and `inherit_fields` use known stored contracts rather than arbitrary Document key shape. Preserve referent existence and evidence semantics. Missing identification/unsupported dependent operations fail as input/dependency errors, not false corruption. |
| `src/repo_catalog/adapters/github/production_intake.py` | At every scoped factory/ResourceObservation production site, attach metadata from actual adapter inputs. Preserve Node-ID versus decimal namespaces and native composite Event local IDs. PR body/title/review/comment/thread coordinates stay exact. Never retry malformed known PR input as global. |
| `src/repo_catalog/application/acquisition.py` | Propagate typed identification through modeled observations. Replace the namespace-only reconstruction use near 1193 with explicit stored/native metadata. Do not synthesize Parent reports or alter request/Capture clocks. |
| `src/repo_catalog/adapters/sqlite/p1_ddl/context.sql` | Apply Resources fragment; remove universal namespace existence FK; update typed index/FK targets and add staging fence; retain existing immutable triggers and all unrelated constraints. No new product table. |
| `src/repo_catalog/adapters/sqlite/p1_schema.py` | Register functions on every normal/factory/expected-schema connection; explicitly set and verify FK/recursive-trigger/CHECK/trusted-schema/defer profile. Compose the exact packaged SQL. Retain fresh-format-only and min runtime checks. |
| `src/repo_catalog/adapters/sqlite/p1_ddl/fingerprints.json` | Regenerate from the coherent implementation; verify Context DDL and physical-schema hashes. Other store DDL hashes must remain unchanged unless an independently justified change is reviewed. |
| `src/repo_catalog/application/production_query.py`, `domain/production_query.py`, `cli/production_query.py` | Replace the four-column old Parent SELECT near 1051 with checked identification metadata. Expose `identification`/`identifier_namespace`, not an inferred semantic `parent`; define any Parent output from I3 reports later. Local ID output remains explicitly serialized TEXT. Keep cursor and enclosing-output limits. |
| `src/repo_catalog/domain/selective_exchange.py`, `application/exchange.py` | Audit `expand_resources`, retained-resource dependency ordering and row decoders. They currently infer Parent/require Parent before Resource. Do not use those paths for new global/unknown/child-first contracts until I6 carries metadata and I3 defines report dependencies. Add precise pre-write unsupported-format/unit guards where necessary; keep Core-only Exchange available. No undocumented old-wire translation, inner repair or changed-content reuse of PackageKey. |
| `src/repo_catalog/adapters/sqlite/production_search.py` | Check exact Resource triples still flow unchanged through Context text projections. Replace any changed query/view access mechanically; generalized structured Search remains I8. Search remains a derivative. |
| `src/repo_catalog/adapters/sqlite/recovery_validation.py`, `recovery.py`, `p1_coordination.py` | Ensure every trusted CHECK/schema validation connection registers the new functions and reads the new fields. Reuse the pure identification validator for local stored decoding. Preserve stop/paired-snapshot behavior. Gate unsupported generalized salvage/import rather than silently losing metadata; complete recovery integration is I7. |
| `scripts/build_p1_schema.py`, `scripts/audit_p1_schema.py`, `docs/implementation/p1-disposition.json` | Regenerate only active introspected schema/disposition data from the new composed format; map old Parent column routes to identifying metadata explicitly. Historical inventories/receipts stay untouched. Refresh generated active callsite index if its inputs change. |
| `tests/unit/test_resource_identification.py` (new), affected ResourceObservation/port tests | API boundary, reconstruction and no-fallback matrix below; no mirrored implementation-only tests. |
| `tests/integration/p1/test_generalized_resources.py` (new), `p1/test_schema.py`, affected Context/Coverage/Provider tests | Execute real packaged DDL with actual functions. Preserve behavior assertions and map any replaced mechanism assertion to its replacement node. |
| `tests/packaging/test_p1_distribution.py`, dependent P3/P6/P7 packaging tests, `scripts/verify_access_distribution.py` | Add installed generalized Resource/read/reopen/refusal probes. Keep both variants attempted and nonzero exit on failure. Do not erase the original Transfer/Exchange/Search/backup smoke assertions. |

API proposal: `resource(key, repository_uuidv4=None, *, identification=None)`.
For known scoped kinds and `document`, omission is an error even for duplicates.
`ResourceIdentification.global_document(key)` explicitly repeats key ID into the
native-ID column; `.scoped(key, namespace, subtype, native_local)` validates the
single scoped encoding and service match; `.from_storage(key, four_columns)`
validates the persisted declaration. Bare key reconstruction is never sufficient
to synthesize this argument. Additional metadata is not another ResourceKey.

Do not expand I2 into complete Exchange or Parent/admission implementation. A
schema-compatible read/registration path must work; genuinely unsupported new
typed consumers must be explicitly refused before side effects. The I2 stack is
not product-wide integration-ready until those dependent stages are implemented.

## 5. Executed disposable evidence and counterexamples

Final proposal lanes each select and execute **133 SQL diagnostic cases**:
**133 pass, 0 failed/error/skipped/xfail**, process exit 0. Each contains 45 accepted
statements and **88 expected SQL refusals** with unchanged pre/post rowsets.
They are diagnostic cases, not pytest/product acceptance tests. The separate
transaction/reopen, four misconfiguration controls, six actual-product baseline
controls and two historical-helper differential vectors are not added as distinct
acceptance counts. Earlier 125-case receipts and pre-final 131-case freezes are
retained separately, not added to final totals.

| Actual runtime | Interpreter | `sqlite_source_id()` |
|---|---|---|
| 3.51.3 | fresh `/usr/bin/python3.13` venv, Python 3.13.5 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| 3.53.1 | fresh managed-Python venv, Python 3.12.14 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

Task C freshly compiled the minimum library from a read-only copy of Task B's
sqlite.org amalgamation; no author-built library or prior execution receipt was
substituted. Independently fetched official release pages verify both source IDs
and minimum C SHA3-256 `32d5424f97e0a7fc5ed2f6335afbb58be4e0298bd7117a34e39d345ff13d859e`.
`provenance.json` records compiler, library/source hashes and options. The build
uses `-O0`; no performance/benchmark conclusion is made.

Supported probe profile: FK=1, recursive triggers=1, ignored CHECKs=0,
deferred FKs=0, trusted schema=1, UTF-8, synchronous=EXTRA, file DB in DELETE mode.
Normal initialized product databases still require their existing WAL checks;
the disposable DELETE-mode runs do not validate WAL crash/power-loss semantics.

The composed proposal retains **19 Context tables and exactly five Coverage
claim columns**. The probe additionally creates three explicitly auxiliary
comparison/reference tables; those are not proposed domain tables. FK/integrity
results are empty / `ok` on both runtimes. Full SQL, arguments, trace, actual
exceptions/extended codes, constraints, before/after rowsets, transaction state,
source hashes, pragmas and index/FK inventories are in `minimum/receipt.json`
and `newer/receipt.json`.

| Counterexample | Actual observation / responsible guarantee |
|---|---|
| Scoped-looking global versus scoped declaration, same triple | Both admit initially in isolation. Opposite complete declaration fails `Resource identification rebind` / trigger 1811 through INSERT, IGNORE, DO NOTHING, REPLACE and UPSERT; reopen retains the declaration. |
| Child before namespace; namespace arrives afterward | Child admits; later namespace gives two Resources and zero reports. Neither operation synthesizes Parent evidence. |
| Omitted/partial metadata; wrong repeated global ID; double-encoded local ID | SQL refuses, including explicit NULL components; no partial row remains. |
| Namespace passed decoded/nested or noncanonical | Refused; one namespace-TEXT profile only. |
| Generated projection explicitly supplied | `cannot INSERT into generated column`, SQLITE_ERROR 1. |
| Invalid UTF-8 from SQL CAST | Refused at the Python UDF decoding boundary with SQLITE_ERROR 1. It is not silently decoded/replaced. |
| Exact limits versus +1 | All inclusive positives admit; oversize/depth/node failures are refused before JSON decoding. SQL-invoked sentinel probes verify prescan ordering. |
| Wrong service/kind/canonical spelling in FK | Real FK787 failures. Explicit NOT NULL projections refuse partial references rather than taking FK's NULL exemption. |
| Wrong absence/subtype on a Document source | Real FK787; generated empty absence cannot quote a scoped source. |
| BINARY identities | Case, whitespace, NFC/NFD, order/nesting, string/array and all four empty forms remain distinct. |
| Exact replay / mutations | IGNORE and DO NOTHING deduplicate; equal UPDATE/UPSERT-update/REPLACE and DELETE refuse under retained immutable triggers. A later invalid row aborts the entire multirow INSERT. |
| Caller savepoint failure | SQL statement failure leaves an earlier prefix pending; explicit unit rollback removes it while preserving outer admitted Resource. COMMIT/reopen retain exact global metadata. |
| Deliberately enabled deferred-FK control | Invalid reference can enter the open transaction; COMMIT raises FK787, transaction remains active, explicit rollback removes all rows. This is outside the proposed normal profile. |
| Missing UDF / trusted schema OFF | DDL or writes fail; Python functions are not SQLITE_INNOCUOUS. Unsupported connection settings are labeled as such, never supported PASS. |
| Experimental helper versus I1 | **33 empty array containers** pass historical `cp.identity`; I1 refuses maximum depth. 32 pass both. Reuse I1, not the old helper's parser/counting. |
| Actual unchanged product SQL | Raw Issue `731` admits but strict ResourceKey reconstruction refuses; unknown kind/global Document/absent-namespace child/native-array-local cases refuse at their actual old constraints. These remain baseline gaps, not repaired product outcomes. |

Raw Python driver error names are preserved: e.g. one runtime labels extended
datatype code 3091 `unknown`; do not manufacture a reported driver name. Expected
errors also include CHECK275, NOTNULL1299, UNIQUE2067, FK787 and TRIGGER1811.

An initial prototype accidentally duplicated the product's existing immutable
trigger names; composition failed before test execution. Its composed input and
failure note are retained under `initial-duplicate-trigger/`. The correction
retains the real product guards. It is a prototype setup error, not a product bug.

## 6. I2 implementation test matrix

The 133 external probes are a reproducible design basis. Future tests must execute
the actual packaged implementation, not import these external helper replacements.

| Family / suggested owner | Required production regression |
|---|---|
| Pure identification unit | Global scalar/array/empty; PR scoped all genuine coordinates; metadata/key mismatch; known-kind invalid no opaque retry; serialized versus native local distinction |
| Reconstruction | Copy/triple/asdict/replace/JSON of key alone preserves equality but supplies no declaration; explicit metadata roundtrip remains exact; new process/reopen; global-shaped replay in both arrival orders |
| Reserved vs unknown SQL | Each allowed namespace above and each wrong one; unknown name per service; known invalid input cannot use generic path; existing six Repository role constraints remain closed |
| Canonical SQL | Every I1 vector at root/namespace/local, Unicode scalar/escape/NFC/NFD, exact bytes/nodes/depth and +1, BLOB/NULL/nontext, bad UTF-8; prove prescan before decoder |
| Omission / NULL / projections | Missing native ID for global, all partial scoped combinations, canonical-looking malformed declarations, generated write attempts, explicit typed-absence references and full non-NULL typed FKs |
| Replay/conflict verbs | Initial/duplicate/conflicting declarations; normal INSERT, OR IGNORE, DO NOTHING, REPLACE, OR REPLACE, UPSERT update and no-op; multirow abort; changed service/kind/ID; unchanged rowsets |
| Dependencies | Provider absent refuses; complete child before Parent succeeds; Parent arrival creates no relationship; no hidden pending payload; I3 later owns original-report re-supply tests |
| Transactions/connections | Savepoint/outer rollback and failed COMMIT; correct normal FK/CHECK/recursive/trusted flags, missing UDF, fresh/reopen/read-only snapshot/expected-schema/stored validator connections |
| Existing contracts | P1/P3 field alternatives, exact text, provenance and classified clocks; Source positives; five Coverage columns/owners/terminals; immutable mapping claims and Dispositions; Core INSERT-only and unaffected Access/Operational/Search DDL |
| Consumer dispatch | Typed facade keyword calls; every ResourceObservation production site; arbitrary global key never calls a scoped decoder; unsupported Exchange/salvage/Transfer refused before effects; output labels namespace separately |
| Four retained Event failures | Re-run all three Provider-intake nodes and I5 namespace-pairing node from Task B. I2 must remove the scalar-local storage refusal, but later I3/I4/I5 exceptions/assertions must be recorded separately. Passing the first gate is not passing their whole semantics. |
| Distributions | Wheel and sdist-wheel outside checkout on both real runtimes; initialized schema, declared/physical fingerprints, required UDF flags and positive/adversarial Resource reads/reopen; preserve complete Access smoke and honest residual failures |

Use existing ordinary collection with `python -m pytest --collect-only -q` and
the default `not live and not benchmark` markers. Do not exclude modules to fix
collection. Start development execution with the new units/SQL tests plus
`tests/integration/p1`, `p3`, Provider intake, I5 and impacted query/recovery/Access
tests, then expand by actual dependency risk. Bind selected, collected, executed,
passed, failed, errored, skipped and xfailed inventories independently; reconcile
literal parameter IDs without splitting embedded `::`. No full suite was run
for this preparation and no final product PASS is claimed.

The exact retained failure nodes to re-execute are:

- `tests/integration/i2/test_provider_intake.py::test_non_transfer_cannot_promote_repository_fields_or_forged_flag[True]`
- `tests/integration/i2/test_provider_intake.py::test_graphql_transfer_parent_namespace_and_original_type`
- `tests/integration/i2/test_provider_intake.py::test_graphql_event_does_not_infer_destination_from_current_issue_repository`
- `tests/integration/i5/test_independent_e2e.py::test_transfer_reports_never_mix_across_observations_or_identifier_namespaces`

The installed Access Event's native Node local coordinate must also remain an
array. Removing their first scalar-local error does not establish the later
assertions. Record whether each next result is a pass, an I3/I4/I5 dependency,
or a genuine implementation defect; do not preassign all future failures to I2.

## 7. Staged PR and independent-review plan

This is a plan only; no branch or PR was opened.

1. **I2 implementation Draft**, based on exact #118 or its independently verified
   integrated equivalent. Commit pure identification values/API, coherent schema
   and functions/indexes/fingerprints, adapter propagation and relevant tests in
   the same reviewable unit. Keep the Transfer fence until the replacement stack.
   Documentation/evidence may follow as a separate unchanged-executable commit.
2. **I3 Parent reports Draft**, exact dependency I2. Extend existing
   `resource_relations`, deterministic projections, complete report support keys
   and referent FKs. Independent/global/nonleaf Documents and attributed
   alternatives; do not issue another domain table. It may use the four-column
   absence-projection Resource index. Fence remains for Transfer.
3. **I4 native-I7 SQL Draft**, exact dependencies I1–I3. Implement the six-column
   same-Event/native-I7 FK from the sole generated support payload, complete
   ParentReport FK and endpoint-to-full-EventReport FK. Preserve lawful I8 reports
   but reject their Transfer support directly in SQL. Retire obsolete five-column
   endpoint index only after every FK is coherently changed. Fence remains until
   the supported typed API also satisfies I5.
4. **I5 typed Admission Draft**, exact I1–I4 dependency. Actual normalized event
   semantics, strict original timestamp types, Provider members, complete supplied
   endpoint set and one savepoint. Remove temporary fence in this coherent
   reviewed replacement; SQL I4 constraints remain mandatory. Revalidate replays.
5. I6 general Relation/Collection/Exchange depends I1–I3; Transfer work also I4/I5.
   I7 stored validation/recovery depends persistent I1–I6. I8 basic reads may
   proceed with I1–I3, while Transfer/final integration agrees with I4–I7. The
   final integrated tree and installed distributions require their own review.

Before each implementation unit is integration-ready, a non-author reviewer must
freeze commit/tree and all codec/schema/UDF/admission/package inputs, independently
inspect exact diff, rerun high-risk SQL counterexamples on both real runtimes and
verify actual PK/FK/UNIQUE collations and connection registration. Independently
challenge shaped global declarations, pre-conflict replay, NULL projections,
native arrays/limits, wrong service/kind and statement/transaction rollback.
Inspect correct positive alternatives too. Re-review every material correction
against its new frozen tree. A SQL architect's own prototype is not this gate.
Do not automatically impose a four-reviewer redesign process or Release Validation.

## 8. Packaging and fingerprint requirements

When implemented, run `python scripts/build_p1_schema.py` once to generate, then
`python scripts/build_p1_schema.py --check` and `python scripts/audit_p1_schema.py
--check` against the prepared interpreter. Inspect actual expected schema and
`table_xinfo` (generated columns are absent from `table_info`). Registration must
cover initializer, writer, snapshot reader, expected-schema constructor, Exchange,
schema audit and recovery CHECK validators; no caller-specific missing function.

Normal connections explicitly set/verify `foreign_keys=ON`,
`recursive_triggers=ON`, `ignore_check_constraints=OFF`,
`defer_foreign_keys=OFF`, `trusted_schema=ON` and existing durability settings.
Python UDFs are deterministic but not innocuous, hence trusted schema must be
enabled only for the exact trusted packaged schema. Do not execute recovered SQL.
Keep no-function/misconfiguration refusal controls. PRAGMA changes after entering
a transaction may not take effect; configure and inspect before ordinary work.

Build direct wheel and sdist-derived wheel with explicit `--python
sys.executable`, in isolated paths using the declared build dependencies. Install
each in a new environment and execute outside checkout without PYTHONPATH or
editable imports. Verify module origins, artifact/source hashes, actual SQL
version/source ID/options/pragmas, packaged SQL bytes, declared and executed schema
fingerprints, function flags, positive/refusal/reopen probes and FK/integrity.
Check Core/Operational/Search/Access/default Schema 21 remain unchanged. The
prepared runtime must actually load 3.51.3; changing a version constant or only
setting LD_LIBRARY_PATH on a static Python does not do so.

Retain all original installed Access smoke assertions. Attempt both artifact
variants even if the first fails. I2 should remove obsolete scalar-local errors,
but its fence and later dependencies can still fail Transfer/Exchange/backup
paths. Record the first actual boundary and unexecuted later assertions. Neither
passing packaging structure tests nor Development CI establishes installed Access
acceptance. Do not change workflows to suppress residual failures.

Bind evidence to both the tested executable tree and final publication tree,
including actual hosted test-merge parents/effective tree. DDL fingerprints do
not hash Python implementation by themselves; bind UDF/codec source and installed
artifact hashes too. No migration/compatibility shim or real-data operation is
needed for this unreleased format. Final release validation remains a separate
explicitly invoked task.

## 9. Deliberate deferrals and ADR reconciliation

| Stage | Explicitly not established by I2 |
|---|---|
| I3 | Sole semantic Parent report acceptance; complete typed report references; member referent FKs, coherent provenance/scope/clock and alternatives; original report re-supply after missing dependencies |
| I4 | Direct-SQL native-I7 support rejection for Q-S10, complete Parent/Event support keys, endpoint support projections and their own no-NULL/rebind guarantees |
| I5 | Actual external Event semantics, original pre-affinity time types, full Provider-member/endpoint completeness, and atomic typed Admission |
| I6 | Generic unknown/global/nonleaf relation/Collection/wire preservation and selection, durable identification metadata through wire, rechecksummed hostile packages, whole-unit dependency omission |
| I7–I8 | Complete generalized stored recovery/paired backup/salvage and query/Search integration, beyond necessary I2 row/schema/read adaptations |

G3=A is fixed: an admissible I8 Parent report is retained but permanently cannot
support this I7-native Event's Transfer; missing correct I7 support is a dependency
requiring original re-supply. Neither matching native namespace metadata nor a
Resources table proves a report, eligible event, endpoints, times or authenticity.
Do not apply native namespace equality to general Parent reports. Do not claim
the complete Q-S10 contract from a generalized Resources table.

**No genuine conflict with accepted ADRs was identified.** Triple PK and matching
wide FKs preserve ADR 0017; exact clocks/digests preserve 0028; five stores and
Core INSERT-only preserve 0029; known role constraints and the deferred reviewed
Q-S10 chain preserve 0030; explicit metadata/child-first admission and sole
resource_relations Parent authority implement the accepted 0031 direction.

Function/index names, metadata API shape, generated absence projection, a temporary
Transfer fence and file organization are engineering choices. The old experiment's
33-array acceptance is an implementation-candidate mismatch with the completed
I1 limit, not an ADR conflict or a reason to reopen the design. The metadata cannot
authenticate a false native contract; that limit is already explicit in the
accepted schema. No new owner policy question is required for these choices.

Procedures used: cloud runtime checks, scoped three-store invariant guidance,
Context registration/Exchange reference, and lessons-to-skills assessment.
No repository skill was modified. Suggested reusable lesson is in
`suggested-skill-lesson.md`; a future authorized implementation owner can add it
with non-author review after product verification. This handoff does not turn
the proposed design into a previously verified production procedure.

## Reproduction and artifact guide

Run `python run.py` in a fresh extraction with the two explicitly configured fresh venvs in this folder,
or use exact argv/environment overrides in `minimum-command.json` and
`newer-command.json`. It sequentially invokes the same `probe.py` against the
untouched source tree and freezes all tracked source hashes. Runtime compilation
is documented in `provenance.json`; official pages are retained.

`baseline_controls.py` and `transaction_controls.py` use the same PYTHONPATH and
runtime overrides, with their output JSON filename as the only argument. For
reruns in this existing workspace, choose new output directory names as probe.py
arguments; existing disposable databases are intentionally not overwritten.
`COMMANDS.md` records complete commands and process outcomes. `artifact-index.json`
binds the selected input/report/receipt files; `i2-preparation-evidence.tar.gz`
contains them without venvs, catalogs or the large source clone.

This plan is ready for an authorized implementation agent and non-author review.
It is not product integration, release approval or a claim that outstanding
required tests pass.
