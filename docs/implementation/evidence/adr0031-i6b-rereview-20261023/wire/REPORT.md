# Independent M02 / wire re-review of #153

M02 is closed for the reviewed I6-B scope. No new Critical, High, Medium or Low
finding was found in this lane. This is a separate reviewer execution of the
correction at HEAD `61e44291e293f773904a0127606e20c8cb83c95e`, tree
`4aa8ddf49fb52d0b903db0b0bfce00ccea2fae0c`; its direct #152 base is
`8521158f2996f125d2fcaac36ea79ac1296a7cf7`, tree
`455ef25606ee555e4154dd2d14929b41aa4ef50f`.

`exchange.decode_package` now computes the bounded received dictionary's
canonical bytes and verifies its SHA-256 before `ExchangeSelectionScope.from_dict`
runs. The shared encoder excludes only the top-level `digest_sha256`. The local
typed selection's existing `to_dict()` remains the representation authority;
the receiver requires exact equality after construction and cannot silently
deduplicate or reorder arrays. The wire envelope/digest encoder, Context report
encoder and Resource identity encoder remain different intentional profiles:
outer JSON uses compact sorted UTF-8 with `ensure_ascii=False`; report JSON uses
the existing compact sorted ASCII profile; identity TEXT uses the existing
string/recursive-array ASCII profile. NFC/NFD strings remain distinct.

## New, independent counterexamples and controls

The 61-node `test_fresh_digest_wire.py` imports no Author/saved test helper.
It uses fresh UUIDs/recursive Unicode IDs and an independently written raw
dictionary hash oracle. Source execution completed **61 PASS / exit0**, with
61 unique selected/start/JUnit identities and exactly 183 passing normal phases.
`source.reconciliation.json` checks actual collection/JUnit/journal/finish/exit.
`execution.json` records the actual command, Python executable/version,
SQLite 3.53.1/source ID and the imported codec file/hash.

- Four canonical positives use reversed object key insertion order, outer
  whitespace, literal UTF-8 or ASCII escapes; decoded canonical dictionary bytes
  and digest agree, and neither NFC nor NFD is normalized away.
- Twenty-four stale-digest cases change nested `digest_sha256`, nested list
  order/NULL, PackageKey, observation, empty/null selection, a Resource selection
  coordinate, or absent/empty Core section, over dict/text/bytes carriers.
  All stop with `DIGEST_MISMATCH`; a forbidden replacement constructor proves
  selection conversion was never entered. Eight correctly rehashed positives
  accept those same canonical changes.
- Twelve correctly rehashed negative cases combine changes to two set dimensions
  or use whitespace/alternate-escape identity TEXT or uppercase OID text. All
  are typed refusals without mutation of caller-owned input.
- Seven rehashed strict-primitive cases reject bool/int/float coercions and
  non-string selection coordinates. Six strict parser cases reject duplicate
  outer/selection/nested-report keys, invalid UTF-8, BOM and a lone surrogate.

The distribution reviewer independently replayed the same probe bytes from each
external site-packages installation: **61 PASS / exit0 in the direct wheel** and
**61 PASS / exit0 in the sdist-derived wheel**, with exact collection/JUnit/
journal phases. Their actual origin/artifact records are in the review's separate
distribution evidence (`direct-fresh-test_fresh_digest_wire-*` and
`derived-fresh-test_fresh_digest_wire-*`). Those outcomes are separate invocations,
not a count added to a full-suite total.

## Unchanged historical probes independently replayed

`original-probe-binding.json` checks all seven files against their actual #152
Git blobs. All seven are byte identical, including the 33 saved counterexamples.
The copied Author34 remains attributed Author coverage; rerunning it does not
make its fixture design independent.

| Separate source invocation | Actual result | Ordinary phases | Exit |
| --- | --- | ---: | ---: |
| Prior independent normal wire157 + planner28 + admission19 + resolved V07 4 | 208 PASS | 624 | 0 |
| Unchanged Author external cases | 34 PASS | 102 | 0 |
| Saved M02 digest30 + M01 work3 | 33 PASS | 99 | 0 |

Each `reused/<lane>/` contains its collection, command/execution, JUnit, journal
and exact node/phase reconciliation. This is additional focused source execution;
it does not replace the parent's single full ordinary invocation or its separate
actual-frame/assertion-entry comparison. The 208-node normal lane has no
saved-failure node or new 56-node correction file in it. These suites overlap
conceptually with the full suite and distribution lanes and are never summed.

## Semantic review and limits

The strict row authority `exchange_rows.ROW_KEYS` still requires all seven named
Resource identification columns and the complete endpoint reference fields.
The embedded `ResourceKey` is the existing three-coordinate key, while its
Resource row carries seven identification columns; neither is a new identity.
`ResourceIdentification.from_wire` reconstructs the same canonical Resource key.
Known scoped contracts cannot fall back to opaque/global dispatch. Complete
child registration requires neither namespace registration nor a Parent report.

The normal208 probes re-execute exact original Parent/Event clocks, provenance
and independent observation values, one/two-sided and Provider-only declarations,
multiple resolved Mapping alternatives, ordered relation/Collection alternatives,
real complete-empty/partial/absent terminals, Source positive pairs and exact
five-column Coverage proof bindings. Source full-key Parent lookup never substitutes
Event values or another Parent's provenance. Explicit endpoint declarations are
checked against all received endpoints; truncation cannot become a one-sided
report, NULL cannot become an unknown Provider target, and a sender verified flag
remains attributed evidence. Exact report payload changes are replay conflicts.

The pure codec still grants no admission authority. This review does not claim
Provider authenticity, durable PackageKey replay, current authorization, SQL
atomicity or operational route integration from a checksum or pure roundtrip.
The normal208 lane separately reruns 19 prior independent authorization/COMMIT
controls, with their actual trace observations; the admission reviewer owns the
broader current-policy/fence retention evidence. I6-C/I7/I8 remain unimplemented
and unexecuted stages. No fence was retired and no normal Transfer enabled.

`MATRIX.md` maps all R02–R09, V01–V09 and T01–T27 to their actual stage owners,
code/probes and explicit deferred portions. The M01/new-limit disposition,
single full-suite/299-signature comparison, all-member distribution audit,
hosted CI receipt verification and final review readiness are owned by the other
review lanes and parent synthesis; this report does not substitute for them.

The applicable AGENTS, accepted ADR0001/0031/0032, I6 wire/admission/exchange,
vectors/tests, change-map/handoff, #152 REPORT/findings/probes and #153 REPORT/
product diff were inspected. The repository investigation/CI/three-store skills
were applied subject to ADR0032. No alternative SQLite was acquired or loaded;
no product/test/assertion/ADR/historical evidence file was edited. No new skill
recipe is needed: the existing received-dictionary canonicality lesson already
states the verified correction, and this lane found no new reusable failure mode.
