# I1b non-author frozen implementation review

Reviewed implementation: `e0e5c0ed37ac9d6c860db185415616c60161b30d`.
Tree: `b6484a7185e9f410a8d05ff5bd4fa574e6dc45e2`.
Exact dependency: `d92377599a50f192f534836fc12402a5fe87ca83` (I1a).

The independent reviewer authored none of the production changes or author
tests. Review used a separate detached checkout, `work/i1b-review-tree`, with
clean tracked/untracked status after execution. All 17 files changed against the
exact I1a parent were inspected, including test fixture adaptations; the shared
codec dependency was also inspected. `frozen-input-sha256.json` binds those
inputs. No source file was edited by the reviewer.

## Findings and dispositions

1. **Material: explicit global Document intent was lost when its native array
   resembled the known scoped layout.** The initial working implementation
   allowed `global_document(S, ['pull_request', J('PR1'), 'body', 'D1'])` to enter
   the existing scoped-only Context adapter as scoped identifying metadata.
   This was independently reproduced using actual SQLite 3.53.1 before the
   correction. The frozen implementation now retains only a non-key in-memory
   factory intent guard. Native `document` construction selects global;
   `document()` explicitly selects scoped. Scoped consumers reject explicit
   global intent, including an already stored equal-key replay. The guard adds
   no identity coordinate: constructor arguments, dataclass fields/asdict,
   equality, hash and `coordinates()` remain the public triple. Both insertion
   and replay counterexamples passed independently on the frozen commit.

2. **Material boundary gap: Context Resource cursor triples only checked their
   service UUID.** A cursor with a recomputed valid checksum could carry plain
   or alternately escaped Resource identity text. The frozen implementation
   constructs a strict `ResourceKey` for both Context/paired Resource cursor
   endpoints. Independent tests recomputed valid checksums for forbidden raw and
   alternate-escape IDs and observed `INVALID_CURSOR` on both endpoints. Valid
   canonical positions roundtripped.

Both corrections were re-reviewed in the frozen commit. No remaining blocking
I1 finding was identified.

## Independent execution

The independently authored `reproduce.py` performs **41 case groups per runtime**,
not a rerun or reclassification of the author's suite. Each runtime executed
41, passed 41, failed 0 and skipped 0. Counts overlap author validation and must
not be added to those counts as unique product tests.

The cases cover native scalar/array/JSON-looking-string distinctions; nested
forbidden native types; plain/noncanonical serialized refusals; strict inner
namespace TEXT versus decoded-nested alternatives; Timeline Node arrays and
exact Issue reconstruction; global/scoped factory intent and triple equality;
MappingSupport, Provider role scope and Coverage owner reconstruction; Exchange
selection roundtrip/refusal; valid and valid-checksum forged cursors; GitHub
decimal/Node namespaces and scoped native Node IDs; scoped Context metadata;
explicit deferred composite-local refusal; actual SQLite BINARY distinctions
including NFC/NFD, empties and scalar/array IDs; and exact compound FK refusal
for wrong service, kind or alternate identity spelling. No Parent report was
created by scoped Resource insertion.

Actual runtime source IDs:

| SQLite | `sqlite_source_id()` |
| --- | --- |
| 3.51.3 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| 3.53.1 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

Both disposable file databases used `foreign_keys=1`, `recursive_triggers=1`,
UTF-8 encoding, DELETE journal mode, synchronous=2, trusted_schema=1 and
temp_store=0. Both ended with no `foreign_key_check` rows and `integrity_check`
equal to `ok`. The JSON receipts retain compile options, exact cases,
observations and actual expected exception/error messages. Runtime versions are
actual SQL query results, not mocked or substituted version constants.

Executed from the main checkout:

```sh
LD_LIBRARY_PATH=/workspace/git-repo-db/work/i1-sqlite/runtime/minimum/lib /workspace/git-repo-db/work/i1-sqlite/venv/bin/python /workspace/git-repo-db/work/i1b-independent/reproduce.py /workspace/git-repo-db/work/i1b-independent/sqlite-3.51.3.json 3.51.3 /workspace/git-repo-db/work/i1b-review-tree
/workspace/git-repo-db/work/i1-sqlite/venv-newer/bin/python /workspace/git-repo-db/work/i1b-independent/reproduce.py /workspace/git-repo-db/work/i1b-independent/sqlite-3.53.1.json 3.53.1 /workspace/git-repo-db/work/i1b-review-tree
```

## Scope and deferred guarantees

Factory intent is deliberately not durable or wire metadata. Serializing a key
triple preserves key equality, not an unavailable global identification
contract. Existing serialized scoped wire/DDL consumers explicitly select their
known scoped format; future generalized identification metadata must be handled
by I2/I6. The supported Context adapter refuses explicitly global Documents;
the packaged DDL remains scoped-only, closes its kind vocabulary and requires
scalar local Document coordinates. The independent composite-local
refusal is an executed **deferred-stage boundary**, not a successful product
roundtrip.

No generalized production DDL, fingerprints, sole semantic Parent authority,
G3=A native-I7 SQL enforcement, whole-unit Transfer admission, generalized
Exchange, stored recovery/paired backup or Search rebuild guarantee was reviewed
as implemented. Existing Parent metadata/constraints remain the prior format
pending later stages. No new semantic Parent report is inferred from parsing.

The generic `canonical()` and outer Exchange digest serializer are unchanged.
Frozen SQL evidence, accepted ADR meaning, store boundaries, Core INSERT-only
semantics and default runtime activation were not changed. No actual accepted
ADR conflict was found. The finite codec bounds and non-key factory intent guard
are engineering choices within I1. This review establishes scoped implementation
and selected executed validation only; it is not full product, distribution,
release, merge or production activation approval.

## Published source and documentation review

The reviewer independently fetched published implementation commit
`174880c113fcd37dad14a8083e85e987a32ae7c6` from `origin`. Its sole parent is
`d92377599a50f192f534836fc12402a5fe87ca83`, and its tree is
`b6484a7185e9f410a8d05ff5bd4fa574e6dc45e2`. `git diff --exit-code` against
executed/reviewed `e0e5c0ed37ac9d6c860db185415616c60161b30d` exited zero.
All 426 author input-manifest blob/SHA-256 records and all 18 independent-review
runtime input hashes match the independently fetched published objects. Changed
commit metadata therefore changes neither reviewed code nor executed inputs.
This is publication binding, not an additional runtime rerun.

The reviewer also inspected the later documentation/evidence additions:
`docs/implementation/adr0031-i1-canonical-resource-identity.md`,
`docs/implementation/evidence/adr0031-i1/`, and the new lesson in
`.agents/skills/three-store-invariants/references/context-registration-exchange.md`.
The implementation report accurately distinguishes 347 passing focused cases,
169 passing existing Context/Coverage/relation/Exchange cases and 45 passing
Provider cases plus three actual Provider-intake failures, per runtime. The
three failures remain explicit deferred-I2 composite-local persistence refusals;
the report retains pytest exit 1 and claims no full product acceptance.

The reviewer independently verified all 48 indexed raw archive files against
their receipt manifest. Each runtime's retained JUnit contains exactly 564
cases: 561 passed, three failures, no errors/skips. Each named failure contains
the explicit current-DDL scalar-local-ID refusal described in the report.
An initial reviewer archive-inspection command assumed flat archive paths;
the corrected inspection accounts for its `i1-final-validation/` prefix and
the unindexed manifest itself. No receipt or product input was changed.
The previously executed four packaged smoke controls and their script were
copied byte-for-byte into author evidence. The public signature's parameter
name was corrected to `provider_resource_id` during report review.

The 88-entry boundary inventory contains every independently enumerated
production constructor/factory/scoped-decoder callsite, plus explicitly labeled
ResourceKey callback/references. The skill addition records the reproduced
native/serialized, shape/replay and checksum-independent-validation lessons;
it adds no authority, durable metadata, architecture choice or new acceptance
claim. Historical evidence stays unchanged. The documentation explicitly
preserves factory intent's in-memory-only scope and future I2/I6 obligations.

No blocking semantic or claim error remains in these documentation additions.
A subsequent documentation-only commit must retain the frozen runtime inputs
and keep final commit/tree/CI coordinates in the PR or a later publication
receipt; this review does not invent a self-referential final documentation SHA.
