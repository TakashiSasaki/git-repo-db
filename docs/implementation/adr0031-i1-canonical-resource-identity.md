# ADR 0031 I1: canonical Resource identity implementation

I1 implements the shared identity codec and ResourceKey boundaries. It does not
implement generalized production Resource storage or I2–I8. The owner issued the
implementation task on 2026-10-21 after design acceptance and design integration.
Both implementation PRs remain Draft; no merge, release, deployment, P8,
retained-catalog mutation or live Provider operation is authorized or performed.

## Baseline and stack

Remote main was fetched and inspected before edits. It matches the supplied
baseline: commit `1ccb7f1902127cde649edcf605bb6d5935427302`, tree
`976810ffce675e0b30b0b68f7d90e8794d0ec29f`. PRs #113 and #114 are merged;
#115 is Draft/open/unmerged at `8ab57eb74068f5ba303b5985a335f0f76be4fdd2`
and is not an implementation dependency. No baseline difference was found.

| Unit | Base | Implementation freeze | Tree |
| --- | --- | --- | --- |
| [I1a / #116](https://github.com/TakashiSasaki/git-repo-db/pull/116) | main `1ccb7f1902127cde649edcf605bb6d5935427302` | `d92377599a50f192f534836fc12402a5fe87ca83` | `318ad07874ab436206e6a61f231b308a421cfc54` |
| I1b | **exact I1a head** `d92377599a50f192f534836fc12402a5fe87ca83` | published implementation `174880c113fcd37dad14a8083e85e987a32ae7c6` | `b6484a7185e9f410a8d05ff5bd4fa574e6dc45e2` |

The I1b connector implementation `174880c113fcd37dad14a8083e85e987a32ae7c6`
has exactly the tree of locally executed/reviewed
`e0e5c0ed37ac9d6c860db185415616c60161b30d`; its parent is the exact I1a head.
The I1a connector publication has exactly the tree of the executed local
`ebb48d4c0beeeb6c19d33d672185894886765835` commit. A non-author independently
fetched and confirmed that equality. I1b's later documentation/evidence commit
does not claim to rerun changed runtime inputs; publication coordinates and
exact final-tree binding are recorded in its PR description and review receipt.

## Public contracts and engineering choices

In `domain/resource_identity.py`:

```python
IdentityValue = str | list[IdentityValue]
encode_identity(value: IdentityValue) -> str
parse_identity(text: str) -> IdentityValue
```

The encoder accepts exact strings/lists only, recursively; it rejects subclasses,
tuples, numbers, bool, dictionaries, None, arbitrary objects and surrogate code
points. The parser accepts exact serialized string TEXT only; byte buffers,
including invalid UTF-8, are refused before decoding. Transport UTF-8 decoders
must be strict. Canonical TEXT is ASCII, so raw non-ASCII, BOM and in-memory
surrogates are refused before JSON decoding. Malformed/forbidden/noncanonical
input is refused rather than repaired. No trimming, Unicode normalization,
case-folding, sorting, flattening or implicit stringification occurs.

The accepted ASCII-escaped profile retains literal solidus, lowercase Unicode
escapes, valid supplementary surrogate-pair escapes and exact scalar sequences.
The generic `p1_context.canonical()` and Exchange outer serializer are unchanged.

Selected engineering limits are inclusive:

| Limit | Exact boundary semantics |
| --- | --- |
| `MAX_IDENTITY_BYTES = 262_144` | Complete canonical ASCII/UTF-8 bytes, including quotes, brackets, commas and escape expansion |
| `MAX_IDENTITY_ARRAY_DEPTH = 32` | Array containers on one path; scalar root depth 0, array root depth 1; a string inside the 32nd array is allowed |
| `MAX_IDENTITY_NODES = 4_096` | Root plus every array and string; empty array/string is one node |

Iterative native validation accounts exact escaped size with O(depth) frames
before `json.dumps`. A complete iterative restricted-grammar scan counts depth
and nodes before `json.loads`; the bounded decoded value is re-encoded and
compared to the exact input. Existing enclosing package/unit/cursor limits still
apply and may be lower. Limits are validated engineering choices, not new owner
decisions or guarantees for a later SQL schema.

In `domain/p1_context.py`:

```python
ResourceKey(service_instance_uuidv4: str, resource_kind: str,
            provider_resource_id: str)  # serialized canonical identity TEXT
ResourceKey.from_native(service_instance_uuidv4: str, resource_kind: str,
                        value: IdentityValue) -> ResourceKey
ResourceKey.global_document(service_instance_uuidv4: str,
                            value: IdentityValue) -> ResourceKey
ResourceKey.document(parent: ResourceKey, resource_kind: str,
                     document_kind: str,
                     provider_document_id: IdentityValue) -> ResourceKey
ResourceKey.timeline_event(issue_parent: ResourceKey,
                           provider_event_id: IdentityValue) -> ResourceKey
ResourceKey.scoped_document_coordinates() -> tuple[str, str, str, IdentityValue]
ResourceKey.coordinates() -> tuple[str, str, str]
validate_timeline_event_coordinates(provider_resource_id: str) -> tuple[str, IdentityValue]
```

Construction is strict serialized admission; `from_native` is explicit native
encoding. Equality, hash, dataclass public fields and `coordinates()` retain
exactly the original triple. Known review/comment/thread keys require the scoped
profile and cannot fall through an opaque-kind path. A scoped Document uses
exactly `J([namespace_kind, J(namespace_identity), subtype, native_local_id])`.
The second coordinate is canonical namespace TEXT represented as a JSON string;
the fourth is the native local value. Decoded-nested namespace alternatives fail.
PR identity, subtype and Provider local ID all survive reversibly.

`from_native(..., "document", value)` and `global_document` select the global
native contract; `document` selects the scoped contract. A private non-key
factory-intent guard prevents an explicitly global array from being interpreted
as scoped merely because its shape coincides. It adds no identity coordinate,
serialization field or equality discriminator. Serialized triple reconstruction
preserves identity equality but does **not** convey factory intent. Existing
serialized consumers implement only their explicit known scoped contract;
durable identifying metadata and generic global wire support remain I2/I6.
The guard is not durable evidence, authorization or a replacement for those stages.

Scoped-coordinate decoding establishes identification coordinates only. It
creates no semantic Parent report. The existing production hierarchy/dependency
rules remain; this stage does not claim their I2/I3 replacement is implemented.

## Modified files and complete boundary audit

[The AST callsite inventory](evidence/adr0031-i1/boundary-audit.json) lists every
production `ResourceKey` constructor/factory/reference and scoped decoder use in
the frozen source. The following classifications cover native and serialized
boundaries, including callbacks and nested references:

| Files / boundary | Contract and reason |
| --- | --- |
| `domain/resource_identity.py` | Pure strict identity grammar, canonical spelling, bounded parser/encoder |
| `domain/p1_context.py` | Strict serialized constructor; explicit native/scoped/global factories; namespace-TEXT decoder; Coverage first-three owner coordinates; Provider role IDs; nested MappingSupport IDs and ClaimKeys; EventReportKey Issue reconstruction; exact comparison helpers |
| `adapters/github/production_intake.py` | All native producers audited. `canonical_database_id` remains explicit native decimal normalization. `github_resource_id`, `github_repository_id`, `github_timeline_input_id` now always return canonical TEXT. Direct key construction consumes that TEXT; decimal parent inputs use `from_native`. PR title/body and Timeline Node local coordinates explicitly parse helper TEXT before becoming native slot four. Repository-role members/scopes and Timeline aliases consistently retain canonical TEXT. Thread IDs are never implicitly stringified; invalid parent kinds cannot use fallback |
| `adapters/sqlite/p1_context.py` | Explicit known scoped metadata extraction and before-replay refusal of unsupported global/composite-local persistence; row/nested ClaimKey/Transfer reconstructions remain serialized |
| `adapters/sqlite/production_context.py` | Exact namespace comparisons in inheritance and typed member ownership; row/resource/MappingSupport reconstructions remain serialized |
| `domain/selective_exchange.py`, `application/exchange.py` | Received/stored key triples and nested members remain serialized; known scoped dependency/member checks use shared decoder. No inner-key repair after digest binding; no generic Exchange expansion added |
| `application/acquisition.py` | Known scoped namespace reconstruction uses shared decoder; no new relationship report or artificial native coordinate |
| `domain/production_query.py` | Context/paired Resource cursor positions validate the full serialized ResourceKey even under a recomputed checksum; existing lower cursor limits remain |
| `cli/production_query.py` | `--id` explicitly requires serialized canonical identity TEXT; it never guesses native strings |
| Unchanged `domain/exchange.py` | Selection keys reconstruct serialized triples; independent outer UTF-8/SHA-256 canonicalization stays unchanged |
| Unchanged `adapters/sqlite/recovery_validation.py`, `production_search.py`, `application/production_query.py` | Stored ResourceKey constructors/callbacks consume serialized rows; strict shared constructor applies. No stored recovery, Search rebuild or fallback implementation is claimed |

New focused modules are `test_resource_identity.py`,
`test_resource_key_identity.py`, `test_github_identity_boundaries.py` and
`p1/test_resource_identity_sql.py`. Existing `p1/test_context.py`,
`test_context_relations.py`, `test_coverage.py`, `i2/test_provider_intake.py` and
`i3/test_selective_exchange.py` retain behavior assertions while native fixtures
now call `from_native` and embedded expectations use canonical TEXT. The Node
Event local coordinate expectation changes from serialized Node TEXT to its
native array. No test is deleted, skipped or xfailed to hide deferred failures.
The skill reference captures the verified native/serialized, shape/replay and
checksummed-cursor lessons; earlier historical evidence is untouched.

## Executed validation and limitations

The [execution receipt](evidence/adr0031-i1/author/summary.json) records commands,
frozen source hashes, selected/executed node inventories, JUnit and journal
reconciliation, outcomes and actual process exits. Runtime reports retain
`sqlite_version()`, `sqlite_source_id()`, compile options, connection pragmas and
every SQL case. Counts from overlapping earlier runs are not summed.

| Actual runtime | Python | sqlite_source_id() |
| --- | --- | --- |
| SQLite 3.51.3 | 3.13.5 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| SQLite 3.53.1 | 3.12.14 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

The genuine minimum library was built from the previously pinned SQLite source
archive (SHA-256 `81f5be397049b0cae1b167f2225af7646fc0f82e4a9b3c48c9ea3a533e21d77a`)
using the unchanged historical builder as a reference. A dynamic-binding Python
3.13.5 actually loaded it. The newer Python embeds actual SQLite 3.53.1. No
spoofed runtime, skipped minimum test or unsupported-runtime PASS is used.

All specification-vector rows are exercised at the appropriate boundary:
scalar/array distinctions; meaningful empty/nested identities; exact nesting and
order; leading zeros/long decimal strings; NFC/NFD, BMP and supplementary scalars;
quotes, backslashes, solidus, controls and DEL; native/escaped lone or reversed
surrogates; noncanonical escapes/whitespace/BOM/trailing data; malformed JSON,
NaN/Infinity, invalid UTF-8 buffers, forbidden root/nested types; SQL NULL in all
three components; exact bytes/depth/node limits and limit+1. Additional sentinels
prove structural/size refusal precedes library decoding/serialization. ResourceKey
tests cover exact stored/wire roundtrips, native namespace separation, every
genuine scoped PR coordinate and nested MappingSupport/Coverage/cursor checks.

The SQL module uses temporary disposable SQLite files and a minimal BINARY
compound-PK/FK comparison harness, explicitly **not production Resource DDL**.
It checks exact key distinctions, full triple FK consistency and canonical UDF
refusal. Four additional existing packaged ContextStore scalar/scoped controls
passed on each runtime. FK/recursive triggers are enabled; runtime JSON records
all actual pragmas. Neither these checks nor clean integrity/FK results implement
the later SQL identity/typed-admission guarantees.

Final frozen nine-module cohort, **on each runtime separately**: 564 selected,
564 executed, 561 passed, three failed, zero skipped/xfail. The process exits 1;
the full cohort is not reported as passing. Selected IDs, executed starts and
JUnit case multisets match; each has exactly one setup/call/teardown outcome.
The 37 disposable SQL cases all passed. Within the same cohort, the four new
focused modules passed 347 cases, and existing Context/Coverage/relation and
selective Exchange regressions passed 169 cases. The Provider-intake module
passed 45 and failed the following three cases. These cohorts partition the
564 selected cases; independent-review counts overlap and are separate.

Three retained Provider-intake failures identify actual deferred I2 limitations:

- `test_non_transfer_cannot_promote_repository_fields_or_forged_flag[True]`
- `test_graphql_transfer_parent_namespace_and_original_type`
- `test_graphql_event_does_not_infer_destination_from_current_issue_repository`

Each reaches the explicit current-DDL refusal of a native composite local Event
ID. I1 deliberately does not stringify that array to appease the old TEXT local
column, drop native namespace coordinates or expand production DDL. Global and
empty/composite local Document persistence also needs I2. Other product suites
outside the recorded cohort were not executed; legacy native-ID fixtures elsewhere
still require later cohort adaptation. Full product validation is not complete.

Earlier diagnosis logs are retained separately: initial old-fixture failures,
two subprocess import failures resolved by editable **development** installation
in both work venvs, and pre-correction counts are not final PASS receipts.
The first instrumented minimum-runtime attempt aborted after 192 starts because
codec tests temporarily patch the shared JSON serializer while the repository
journal also uses that serializer. Its INTERNALERROR/partial receipts are
preserved. A work-only event journal captured its serializer before tests; the
completed unchanged-source reruns above reconcile execution without that
instrumentation conflict. The aborted attempt is not counted as a passing run.
Ruff lint and format checks run on `src tests scripts`; whitespace and relevant
prose/report checks run separately. No local wheel/sdist acceptance was attempted.

## Independent reviews and dispositions

[I1a review](evidence/adr0031-i1/codec-review/review.md): a non-author inspected the
frozen codec in a detached tree, independently reran 195 author cases per genuine
runtime with zero failures/skips, and executed 50 reviewer groups per runtime.
Those include 5,000 native reference roundtrips, 15,000 serialized mutations and
9,331 exhaustive tokenizer inputs, nested within the 50 groups rather than
additional pytest counts. No substantive finding remains.

I1b's non-author boundary reviewer found two material issues during review:
explicit global arrays could be guessed as scoped (including duplicate replay),
and ResourceKey cursor positions validated only the service UUID. The corrections
preserve non-key factory intent, validate known scoped admission before replay,
and validate full cursor keys independently of checksums. Focused positive and
negative regressions cover both. The frozen independent review and counterexample
receipts are retained under `evidence/adr0031-i1/integration-review/`.
The reviewer inspected all 17 I1b source/test changes and independently passed
41/41 counterexample groups, zero failures/skips, on each genuine runtime,
including actual packaged scalar/scoped metadata, deferred composite refusal,
SQLite BINARY distinctions and compound FKs. Both material corrections were
re-reviewed against the frozen implementation; no blocking I1 finding remains.

No actual conflict with accepted ADRs was identified. The selected finite
constants, API names, iterative scans, temporary comparison schema and non-key
factory guard are engineering choices. A3, B3, U1–U5, U2-E2, G3=A and genuine PR
Document coordinates are unchanged.

## Development CI and remaining product stages

I1a [Development CI run 39578959808](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39578959808)
passed for feature `d92377599a50f192f534836fc12402a5fe87ca83`, checkout merge
`fa5d3baad773af3bada10d023c630713fc8a58c3`, effective tree
`318ad07874ab436206e6a61f231b308a421cfc54`. The bounded receipt ZIP is retained;
it reports `development_checks_passed`, `full_acceptance=false`. Hosted runtime
pytest and installed-distribution stages were skipped, so their execution is not
claimed. Final I1b Development CI is recorded against its exact published head in
the PR; a green result does not erase the three local product failures.

Post-publication checks at I1b head
`116cd208555da9ee6d6fddc80c6e519dbaa5cce1`, tree
`ec7ddcd0ddb4715a5fc604d2cac2581f5142d409`, exposed an additional wider-cohort
limitation. [Development CI 39581231211](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39581231211)
passed with `development_checks_passed`, `full_acceptance=false`, zero executed
pytest IDs and 203 required/unexecuted files. Its Python 3.12.15 / SQLite 3.45.1
performed static/smoke checks, not supported-runtime identity tests. The actual
bounded receipt and its 21 indexed members were hash-verified; test-merge
`58b17d1e69828c3c3120c435a39abcde16838ad3` has this exact effective tree.

The pre-existing [Access workflow 39581231143](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39581231143)
**failed** on actual SQLite 3.51.3. Its broader pytest collection exited 2 before
execution. A local reproduction of that exact collection command found 2,312
collected nodes and one collection error: the unadapted P3 module-level fixture
`ResourceKey(SERVICE, "pull_request", "pr-7")` in
`tests/integration/p3/test_production_context.py`. No broader tests are counted
as executed/passing. The same hosted workflow then attempted its existing
installed-wheel smoke; it failed at a plain-ID ResourceKey in
`scripts/verify_access_distribution.py`. No wheel/sdist acceptance follows.
These obsolete fixture/script boundaries are distinct from the three executed
deferred-I2 product failures; neither is hidden or presented as passing.
The [CI observation receipt](evidence/adr0031-i1/i1b-ci-observations.json) retains
the exact check states and local collection log. Wider fixture/script adaptation
and later product/distribution validation remain outstanding. This subsequent
documentation-only disclosure changes no frozen runtime or test input.

I2 must update production Resource DDL, identifying metadata, bounded SQL
functions, composer/fingerprint and packaged DDL together. I3 replaces the old
semantic Parent authority; I4 adds G3=A native-I7 Transfer SQL constraints;
I5 adds typed whole-unit admission. I6 supplies generic Relation/Collection/
Selective Exchange and durable identification-contract dispatch. I7 covers
stored recovery validation and paired backup; I8 covers query/Search rebuild and
fallback integration. Final distributions and integrated release acceptance
follow those stages under separate authorization. I1 prepares shared values and
boundaries without claiming any of those product guarantees.
