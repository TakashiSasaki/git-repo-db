# C-F1 correction to the I2 staged Transfer contract

This additive design supersedes only the incomplete staging-fence portions of
[Task C's plan](../adr0031-i2-preparation/I2-IMPLEMENTATION-PLAN.md). It preserves
all predecessor commits/evidence and the complete Resources design. It is based
on PR #121 `03ff484eca32bf6ed76b4b9fd472c99052f7d8b6`, tree
`927288ecc20082144887fd668636b35171b647dd`. The independent
[Task D report](../adr0031-i2-independent-review/REPORT.txt) remains NOT READY for
its reviewed inputs. This correction requires a new independent review; its own
author validation cannot update Task D's verdict.

## Before and after

| Contract | Task C before | C-F1 after |
| --- | --- | --- |
| Endpoint writes | Both reserved Transfer roles refused in `resource_repository_relations` | Same original trigger, unchanged |
| Transfer report writes | Generic `resource_relations` checks admit reserved `transfer_event_report` | New unconditional BEFORE INSERT refusal for that exact reserved name |
| Provider-only reports | Can bypass the endpoint fence and reach the reference reader without I7/Parent/endpoint rows | SQL refuses even this well-formed report; typed reads/imports also declare Transfer unavailable |
| Conflict shortcuts | Endpoint trigger prevents them | Both representations refuse before INSERT conflict handling; retained UPDATE guards close UPDATE/UPSERT-update paths |
| General Parent/other relations | Existing common row contract | Same contract; no extra Parent table/FK, namespace equality, member rewriting or new authenticity claim |
| Product support | Not implemented | Still not implemented; executable evidence helpers live only in this directory |

[compose_f1.py](compose_f1.py) calls the frozen predecessor composer and appends
[fence.sql](fence.sql). The old composed SQL is an exact prefix of the new one.
Only one new physical-schema object is added: `i2_transfer_report_stage_fence`.
No Resources column, CHECK/UDF, PK, index/FK, Provider registration, role grammar,
Source/Coverage, immutable guard, store schema or fingerprint is changed.

The new predicate compares the reserved name using BINARY equality and always
raises ABORT; it does not inspect payload completeness, dependencies, arrival
order or old rows. INSERT, OR IGNORE, DO NOTHING, REPLACE, OR REPLACE and UPSERT
therefore cannot turn it into a no-op. Malformed reserved payloads are refused
too. No table-search UDF or optional application call supplies the SQL guarantee.
Existing `resource_relations_no_update` and `rrr_no_update` remain essential:
they also refuse an INSERT of a generic row whose UPSERT update would change
its kind to a reserved representation. DELETE/REPLACE immutability remains.

This unreleased staged format is fresh only: no grandfathered Transfer rows,
repair migration, configurable bypass or feature flag is introduced. Both
fences remain until one independently reviewed effective implementation tree
contains I3, I4 and I5 plus matching read/import support. I4 still must reject
I8 support for an I7-native Event in SQL; removing these guards alone cannot
enable Transfer.

## Mandatory product stage constraints

The following are requirements for the future I2 implementation, not product
behavior supplied by this design-only PR. [stage_contract.py](stage_contract.py)
is an executable routing model for the normalized boundary only.

1. **Typed writes:** `admit_transfer_event` and every facade/port equivalent must
   raise an explicit unsupported-stage error before Resource registration,
   evidence, clocks, ledgers or duplicate shortcuts. Generic relation admission
   must reject the exact reserved report name; endpoint admission must reject
   both reserved roles. This is `I2_TRANSFER_UNSUPPORTED`, not a missing-I7
   dependency, a Q-S10 I8 finding or supported empty success. SQL fences remain
   mandatory even when callers bypass those APIs.
2. **Exchange/import:** retain the supported-version, digest, canonical input,
   permission, selection and dependency checks. After decoding to typed units,
   preflight all selected operations in the current atomic admission transaction
   before any of its effects or replay return. Detect typed Transfer units,
   reserved report rows and either endpoint role, including nested typed units
   and Provider-only forms. Refuse the selected transaction on any such unit;
   preserve existing outer-transaction rollback rules. Do not silently strip a
   Transfer member, relabel it opaque, shrink complete claims, or persist a
   deferred payload. Independent Core-only selections remain available under
   their existing contracts. The model accepts prevalidated normalized operations
   and does not implement the real envelope/parser or selection traversal.
3. **Readers/export/query/Search:** an explicit Transfer query/export selection
   must report unsupported even when the store is empty. Generic readers and
   unfiltered exports must not publish reserved Transfer rows as ordinary
   reports. After normal trusted schema/function/PRAGMA validation, validate the
   staged invariant that neither representation exists, before domain exposure.
   A mismatch of expected schema is a format refusal; an impossible reserved row
   in a matching authoritative schema follows existing stored-invariant and ADR
   0026 handling. Never delete, hide, downgrade or auto-repair it; diagnostic and
   salvage reads remain explicitly untrusted. Search cannot make unsupported
   Transfer effective via a stale projection or verified flag. Full I7/I8
   backup/Search integration remains separate.
4. **General reports:** preserve `resource_relations` as the sole semantic Parent
   authority. A general I8 report remains eligible under its ordinary contract;
   it is not Transfer support. Do not derive Parent evidence from namespace
   metadata or require a Parent for complete child identity. Generic names are
   exact BINARY strings; case/whitespace variants are opaque names, never aliases
   of the reserved name. Arbitrary payload text mentioning Transfer conveys no
   event semantics. Existing reserved common contracts still apply.
5. **Transaction and replay:** ABORT rolls back its statement, not an earlier
   caller prefix. Supported admissions must use whole-unit savepoints and roll
   back on body, SQL or COMMIT failure. Refusals must precede package/unit replay
   shortcuts and must leave no partial report/endpoint. Parent arrival cannot
   replay a withheld Transfer. Required SQLite configuration and UDF registration
   stay identical to Task C; disabled enforcement is unsupported.

The stage-storage check is a minimal I2 safeguard, not full I7 semantic recovery
validation. The normalized routing model is not an installed API, real Exchange,
production reader or Search implementation. Those product paths must receive
the documented guards before I2 is accepted.

## Mapping to the original implementation plan and matrix

| Task C section / file | Required additive correction |
| --- | --- |
| Plan sections 2–3, proposed composed SQL | Keep Resources/endpoint fence exactly; append the report fence and retain immutable UPDATE guards |
| Plan section 4, `p1_ddl/context.sql`, `p1_schema.py`, fingerprints | In the separately authorized product implementation, compose/package both fences with exact registry/configuration/schema hashes; include the minimal staged stored-row check |
| `p1_context.py`, `production_context.py`, domain ports | Guard typed Transfer API, generic reserved report admission and all read/facade routes before effects/replay; retain ordinary relation behavior |
| `application/acquisition.py`, GitHub intake | Guard normalized Transfer units before hierarchy/resource registration; do not fall back to a generic report when unsupported |
| `domain/selective_exchange.py`, `application/exchange.py` | Preflight normalized selected transactions including nested report/endpoint/Provider-only forms before admission or replay; refuse explicit Transfer export selection |
| `application/production_query.py`, `production_search.py`, stored validation paths | Explicit unsupported Transfer reads; detect unexpected reserved storage without publishing or silently dropping rows; keep existing recovery boundaries |
| Plan section 6, SQL matrix | Add the exact Task D minimal SQL, both report/endpoint conflict verbs, generic-to-reserved UPSERT update, NULL/malformed report, statement atomicity and rollback |
| Plan section 6, consumer matrix | Add empty-store unsupported query, malicious replay, mixed Context import preflight/rollback and poisoned-store ordinary-read/export refusal |
| Plan sections 7–9 | Both fences persist through I2/I3/I4, removed only with reviewed I3–I5 plus routing support; independent frozen-input re-review required |

## Review matrix and limits

- Re-execute the unchanged Task D minimal SQL on the old and new compositions.
  The old report INSERT must succeed, and the new one must raise SQLITE trigger
  refusal while preserving its exact pre-statement rowset. No I7 Resource,
  Parent report or endpoint is needed to reach the new refusal.
- Exercise all INSERT/conflict verbs for reports and both endpoint roles,
  with missing/present dependencies, malformed/NULL metadata, forced collision,
  no-op clauses and generic-to-reserved UPDATE/UPSERT update.
- Keep positive child-first, independent/global/scoped Resource, Parent I7/I8,
  alternative, ordered multi-member and opaque relation examples. Their success
  establishes common staged storage only, not completed I3 typed-report semantics.
- Check full before/after rowsets, real exceptions/codes, multirow abort,
  caller rollback, ordinary read reopening and deferred COMMIT rollback.
- Exercise the routing model's typed APIs, normalized import preflight/replay,
  positive generic import/export and an injected reserved-row reader refusal.
  Injection is a disposable diagnostic fixture, never a supported write path.
- Bind all candidate, harness, predecessor, codec and product inputs, runtime
  sources/libraries, actual SQL versions/source IDs, options, pragmas and process
  exits. Run actual 3.51.3 and 3.53.1. Preserve failed attempts and old evidence.

I3 general Parent constraints, I4 native-I7/full-report reference guarantees,
I5 actual event semantics/completeness/whole-unit Admission, I6 wire selection,
I7 complete recovery and I8 Search are not implemented or independently approved
by this correction. Accepted ADR 0031 and G3=A remain unchanged.
