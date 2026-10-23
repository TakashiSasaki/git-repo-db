# I6-B Author requirement and execution map

The implementation scope is the pure v5 codec and finite Context dependency
planner. These are Author-team tests, not independent review. The final run
receipts in this directory bind execution to the tested source commit/tree and
input hashes; test existence alone is not a passing receipt. Normal acquisition,
selective Exchange integration, recovery and query/Search remain owned by later
stages. Both SQL Transfer fences and I6-A current-authority checks remain required.

The executable additions are
`tests/unit/test_context_wire_v5.py` and
`tests/unit/test_context_dependencies.py`. Their test function names retain stable
T/V identifiers. Run them directly with the repository's actual selected Python:

```sh
uv run --no-sync pytest tests/unit/test_context_wire_v5.py \
  tests/unit/test_context_dependencies.py -q -o addopts= \
  --junitxml OUTPUT/junit.xml --journal OUTPUT/journal.jsonl
```

No alternate SQLite engine, skip/xfail, network guard removal, permission widening
or ordinary Transfer activation is part of these tests. Earlier exploratory runs
and their failures remain distinct from the final frozen-source run.

## Requirements

| Contract | Author evidence/assertions | Scope limits |
| --- | --- | --- |
| R02 exact v5 | `test_T10_V08_v5_reader_rejects_other_versions_even_with_correct_checksum`, `test_T10_V08_missing_version_is_not_inferred`; exact seven Resource fields and complete endpoint references | No v4 fallback; pure section codec has an explicit v5 entry point and full wire envelopes use `decode_package` |
| R03 strict bytes, JSON, primitives, digest | duplicate outer/embedded keys, malformed UTF-8, lone surrogates, NaN/Infinity, wrong primitive/subclass/cyclic inputs, rechecksummed malformed embedded keys, altered digest and canonical UTF-8 recomputation | A checksum does not authenticate Provider origin or authorize admission; attributed evidence resembling Resource keys stays opaque unless it occupies an actual modeled reference path |
| R04 finite grammar and actual work | intrinsic ID bytes/depth/nodes exact/+1; actual outer 32 MiB exact/+1; dictionary-key lexical elements at real 200,000/+1; final-digest-inclusive envelope encoder/decoder limits; final-leaf string-chunk overrun rejection; decoded Identity aggregate element/depth/work accounting; planner zero/exact/+1 depth/node/edge/unit/byte/work with prior-work replay | Default/capped bounds are exercised without patching limits; individually valid identities can exceed enclosing limits |
| R05 existing identification authority | global/scoped/opaque scalar/array/empty/Unicode vectors preserve all seven fields, known-contract mismatch rejects without fallback, namespace absent and no inferred Parent | Reuses `ResourceKey`/`ResourceIdentification`; no new identity grammar or kind registry |
| R06 whole original generic reports | ordered alternatives, complete-empty versus partial-empty versus unknown versus no terminal, same-time competing orders, immutable scope/time conflicts, duplicate members reject; budget omissions preserve or withhold whole report/terminal alternatives | No durable pending queue, report shrinking, union or arrival winner |
| R07 Source and Coverage | partial inventory keeps both independent positive pairs, strict terminal boolean, canonical set ordering, five-column claim and exact terminal proof, service mismatch, source/known-positive-pair dependencies, exact Coverage Scope dependency for claims/proofs and Collection-header dependency for Collection-owned scopes, lost alternatives withhold completeness | Pure transport/planning preserves originals; it neither updates stored membership nor implements later route authorization |
| R08 original Parent | Parent 50/P/51 versus Event 100/E/101, complete quoted key, required genuine Parent row, different provenance cannot rescue missing original, immutable observation conflict | Admission and SQL authority remain I6-A; a decoded report is not current-authority approval |
| R09 original endpoint declaration | V04 one-sided explicit NULL, V05 complete two-sided and truncation refusal, V06 Provider-only, V07 resolved mapping support, missing fields/altered complete refs refuse, whole Transfer selection and missing mapping claim withholding | Pure codec checks structure/original binding; current Mapping qualification and receiver grants remain mandatory Admission work |

The focused Coverage regressions also require typed Collection proof scopes to be objects while preserving arbitrary canonical generic Collection scope values without proofs. A controlled earlier candidate produced five incidental `AttributeError` failures; the explicit typed refusal and five preservation controls are retained in the new evidence.

## Canonical vectors

[`vectors/manifest.json`](vectors/manifest.json) indexes nine exact synthetic
outer wire JSON files, with measured byte lengths, SHA-256 and the contained
recomputed digest. V08 is deliberately malformed after recomputing the outer
digest; its expected result is rejection, not checksum failure. The other files
are actual accepted codec outputs. They are fixtures, not real Provider traffic
or authenticated original evidence.

| Vector | Executable mapping | Preserved or rejected property |
| --- | --- | --- |
| V01 | `test_T01_T02_V01_V02_identity_and_all_seven_named_columns[global-*]` | Global Document repeats complete native canonical ID and has no namespace/Parent prerequisite |
| V02 | same test `[scoped-*]`, scoped mismatch, namespace-planner test | Explicit canonical-TEXT namespace; child independent of namespace registration |
| V03 | `test_T03_T05_T06_V03_V07_original_parent_endpoint_semantics`, complete Parent-key/other-provenance tests | Parent original clock/provenance/time stay independent of Event |
| V04 | original-semantics case `[False-False]` | Genuine one-sided explicit NULL remains one-sided with complete Event reference |
| V05 | original-semantics `[True-False]`, truncated-two-sided test | Original two-endpoint declaration cannot be shrunk to one endpoint |
| V06 | original-semantics `[False-True]` | Provider-only unresolved endpoint stays distinct from NULL or resolved Core Repository |
| V07 | resolved-mapping helper and exact support tests; planner missing-mapping test | Full direct MappingClaimKey, support and original endpoint refs survive; absent dependency withholds entire Transfer |
| V08 | strict/canonical/version/duplicate/time/unknown-field tests and rechecksummed fixture | Semantic validation still runs after a valid outer checksum; coherent attributed forgery does not gain authentication |
| V09 | generic order/real terminal tests, Source/Coverage tests and planner alternatives tests | Ordered reports and complete/partial/unknown/absent terminals remain distinct; inventory remains set-valued |

## T01–T27 allocation

| Test ID | I6-B execution mapping | Deferred/shared obligations |
| --- | --- | --- |
| T01 | Native identity corpus and exact/+1 caps; seven-column codec, strict primitives, aggregate embedded identity depth/elements/work | API/SQL BINARY invariants remain covered by unchanged I1/I4 cohorts |
| T02 | Global/scoped child-first codec, no synthesized Parent, namespace excluded from planner traversal | Durable route import/export and late original resupply are I6-C |
| T03 | Exact independent Parent/Event originals and provenance lookup | I6-A stored replay/current authority retained |
| T04 | B transports exact Parent support; no I8-to-I7 correction | Native-I7 Admission/direct-SQL controls remain unchanged I4/I6-A tests |
| T05 | One-/two-sided and missing/truncated declarations, complete endpoint refs, atomic planner unit | Stored replay/normal-route integration are I6-A/C |
| T06 | Explicit NULL, not-reported, Provider-only and resolved support remain distinct; malformed refs/targets reject; missing mapping planner omission | Current qualification and permission outcomes are I6-A/C |
| T07 | No authorization grant is created by planner/codec | Per-dependency current authority is I6-A/C |
| T08 | No receipt/replay authority added; immutable wire replay checks remain | Store/facade/route revocation and lease fences are I6-A/C |
| T09 | Strict selection primitives and explicit empty Resource/Source selection | Receiver permission context is I6-A/C |
| T10 | Valid-checksum malformed canonical IDs, wrong versions, dropped endpoints and unknown fields reject | Receiver-local Provider assessment cannot be advanced by sender flags; current authority remains A/C |
| T11 | Cyclic actual-member graph, namespace-independent traversal, deterministic whole units, exact/zero/+1 node/edge/depth/byte/unit/work, cumulative prior work | Actual database dependency reads and request continuation integration are I6-C |
| T12 | Ordered terminal alternatives, empty/partial/unknown/no terminal, real proof retention and atomic loss | Current derived Coverage projection and nested proof integration retain their existing authorities |
| T13 | Partial Source inventory, known-positive associations, source service/selectability, exact original proofs; Source registration selects no Resource | Durable associations and current grants remain I6-A/C |
| T14 | Pure planner whole-unit omissions tested | Sender/receiver disjoint grants and authorized-local dependency lookup are I6-C |
| T15 | No hidden replay/pending implementation added | Two-/three-catalog late/reverse/onward routes are I6-C |
| T16 | Planner dependencies include genuine Parent before Transfer; independent Resource survives missing support | Durable route ordering/import permutations are I6-C |
| T17 | Preserved existing implementation/test inputs | In-flight rollback and COMMIT behavior remain I6-A |
| T18 | Codec keeps complete Parent/Event references and strict types | Full 217 I4 SQL mutation/constraint controls remain unchanged and separately rerun |
| T19 | No fence/schema edits | Existing normal/helper/facade and installed distribution controls remain I6-A |
| T20 | No schema/UDF/fingerprint edits | Existing connection safety controls remain; stored corruption/recovery decoder work is I7 |
| T21 | Unexecuted in B; no recovery changes | I7 |
| T22 | Unexecuted in B; no paired restore/salvage changes | I7 |
| T23 | Unexecuted in B; no query/Search implementation | I8 |
| T24 | New wire tests are part of source and both isolated installed distributions; origins/product bytes/RECORD are recorded by the Author runner | Final installed receipts carry actual outcomes; no full Release acceptance claim |
| T25 | Ordinary suite outcomes compared by node/phase/exception/assertion reach with #149; original Access smokes retained | Historical failure counts are reference evidence, never a fixed target |
| T26 | No route integration or boundary weakening | I6-A ordinary-route fail-closed tests rerun; complete route implementation is I6-C/I7 |
| T27 | Same original key with changed time, scope and membership/order conflict; independent alternatives retained | Durable PackageKey/current-permission replay controls remain A/C |

Independent non-Author review is not claimed. Development CI Success, source
Author tests and installed-distribution Author tests are separate observations;
none alone establishes complete Release acceptance or retires either Transfer
fence.
