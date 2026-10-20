# Generalized Context Resource design handoff

## Status and authorization

[ADR 0031](../adr/0031-generalized-context-resources.md) is **proposed**, with
`date: null`. The owner has selected A3, B3, U3=C′, U4=B, U5=A, U1=B, U2=A and
U2-E2; the package records these without reopening them. Acceptance of the
complete package, physical realization and engineering proposals is separate.
The [schema contract](../architecture/context-resource-schema.md) contains the
grammar, equality, specification vectors, dependency behavior, authority
boundaries, ADR matrix and experimental acceptance contract.

This task authorizes documentation, checks, branch push and a Draft PR. It does
not authorize implementation, accepted-ADR body edits/retirement, production
Python, packaged DDL/fingerprints, dependencies, existing runtime tests, workflows
or default-runtime changes. Do not modify another agent's branch or modify/retarget
PR #113. Merge, auto-merge, release, deployment, P8, real catalogs, backups,
credentials and live Provider accounts remain outside permission.

## Fixed baselines and evidence

The task's coordinates were checked against live GitHub and a fresh fetch of all
remote heads plus PR #113. The repository was not shallow.

| Coordinate | Inspected value |
| --- | --- |
| Product/main commit | `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9` |
| Product/main tree | `117d580b31098ecb8287281bd843894fdfad71fc` |
| Integrated work | Main includes PR #112 / ADR 0030 I1–I5 integration |
| PR #113 state | Draft/Open; base main; unchanged during branch creation |
| Frozen audit/branch-base commit | `24f593861327328fa00dab0b83f956cec330a0ac` |
| Audit/branch-base tree | `7318fdb1cb5ef4959d685bf2a3a1d9d91385c89e` |
| Audit head / intended Draft PR base branch | `audit/context-provider-agnostic-20261020` |
| This documentation branch | `docs/generalized-context-resources-20261020` |
| ADR allocation | 0031; previous watermark 0030, no higher allocation found in current remote heads, reachable ADR history including deletions, index or open PRs |

Initial open-PR enumeration returned only #113; no public experiment/design PR
was available to cite. The owner described a separate experiment agent but no
executed evidence/commit was supplied to this author. U3=C′ remains open. Recheck
live heads and allocation immediately before publication; do not silently adopt
another product revision. The experiment agent is not to allocate an ADR.

The parent audit was read at its fixed HEAD:

- [Audit](https://github.com/TakashiSasaki/git-repo-db/blob/24f593861327328fa00dab0b83f956cec330a0ac/docs/implementation/context-provider-agnostic-audit.md).
- [Findings](https://github.com/TakashiSasaki/git-repo-db/blob/24f593861327328fa00dab0b83f956cec330a0ac/docs/implementation/context-provider-agnostic-findings.md).
- [Options](https://github.com/TakashiSasaki/git-repo-db/blob/24f593861327328fa00dab0b83f956cec330a0ac/docs/implementation/context-provider-agnostic-options.md).
- [Evidence and execution limits](https://github.com/TakashiSasaki/git-repo-db/blob/24f593861327328fa00dab0b83f956cec330a0ac/docs/implementation/evidence/context-provider-agnostic/README.md).

Its **37 added probes + 126 existing cases = 163 distinct author cases** concern
product `efb55af…`, Python 3.12.14 / SQLite 3.53.1. They are focused audit evidence,
not minimum-SQLite, live Provider, full release or new-schema verification.
Independent audit review counts overlap. F01's correct current kind/parent
refusals are broader-use gaps, not demonstrated production defects. F02 adapter
normalization, F03 actor/target conventions, F04 visibility/Coverage clocks and F05
structured Search remain separate work. Audit alternatives/recommendations do not
override the owner's subsequent common schema choices.

## Fixed, proposed and unproven boundaries

| Category | Contents |
| --- | --- |
| Owner-selected logical choices | Open kinds with reserved known contracts; Provider-scoped meaning; existing PK triple; canonical String/recursive Array identity; meaningful empties; semantic Parent in resource_relations; complete-child admission with original-report re-supply; generic unknown-kind preservation/exchange. |
| Preserved accepted contracts | Genuine PR-document coordinates; six Repository roles; immutable claims/qualified Dispositions; typed Issue Timeline Event SQL references plus event-semantic admission; five stores; original clocks/provenance; Source positives; five-column Coverage; exact text; PackageKey/digest behavior. |
| Engineering proposals | Reuse Context ASCII-escaped identity profile; exact BINARY comparison; byte/depth/node ceilings from existing strict JSON parser; consistent bounded validation; future document encoder details; support-key/projection DDL to be supplied by experiment. |
| Unproven gate | U3=C′ preserving required typed Parent/Timeline Event SQL FKs in existing tables, exact support-report references and adversarial mutation paths. No SQL solution is certified. |
| Package state | Proposed documentation, not accepted package, implemented feature or runtime verification. |

Syntax cannot prove `[]` is a native singleton or `""` a complete ID. Adapters
establish identification completeness; missing new adapters do not prevent
recording the common grammar. Future typed support cannot silently rekey or
reinterpret old opaque Resources. Unknown wire versions fail their separate gate.
Unknown relationship names grant no traversal, authority or completeness.

## Current-code impact map

These anchors describe unchanged fixed product source. They identify future
review targets, not authorized edits or an exhaustive implementation checklist.
All paths below are under `src/repo_catalog/`.

| Area / path | Current behavior and future boundary |
| --- | --- |
| `domain/p1_context.py:178,234` | Strict parser versus encoder: encoder alone permits lone surrogates; parser applies 262,144-byte/32-depth/4,096-node checks but counts nodes after json.loads. Identity requires restricted types and consistent bounded Unicode validation. |
| `domain/p1_context.py:639,654` | ResourceKey currently checks nonempty kind/ID, without new grammar/caps. Document factory embeds parent ID as a string within four coordinates; preserve semantics and explicitly specify encoding changes. |
| `adapters/sqlite/p1_ddl/context.sql:25` | Closed twelve-kind CHECK; parent/document columns, parent FK and typed Event index. Remove second semantic Parent authority only while preserving typed SQL guarantees through U3. |
| `adapters/sqlite/p1_schema.py:47` | SQL p1_json roundtrip is weaker than strict domain parsing. It does not already enforce the new Unicode/size/grammar requirements. |
| `adapters/sqlite/p1_context.py:75` | Admission reconstructs four string coordinates for known parented kinds. Separate complete identity from admissible semantic Parent reports. |
| `adapters/sqlite/production_context.py:520` | Reserved reviews/comments/threads/documents enforce child ownership. Preserve known semantics; generic member references still need referents. No opaque fallback. |
| `domain/p1_context.py:240,2371` | Timeline coordinates and Coverage owners embed Resource identity. Preserve Q-S10 and exact common representations/five Coverage columns. |
| `domain/exchange.py:162,471,565` | Outer digest profile differs from Context JSON. Compare declared SHA-256 then validate inner keys; no changed identity under old content binding. |
| `domain/selective_exchange.py:577,686,874` | Parent expansion, wire validation and unit selection need explicit new dependency authority and finite permitted expansion. Unknown names confer no traversal. |
| `application/exchange.py:2282,3038` | Dependency retention and Context admission order assume parented resources. Admit complete child independently; withhold/report dependent complete units and require re-supply. |
| `application/production_query.py:1042`, `adapters/sqlite/production_search.py:509` | Typed parent/document output, Search/fallback need consistent keys and unknown-kind readable output. Preservation does not promise arbitrary structured-field Search. |
| `adapters/sqlite/recovery_validation.py:9`, `adapters/sqlite/recovery.py:1388` | Stored semantic/FK and paired snapshot validation must understand generic format and typed constraints. SQLite byte-copy alone proves no new semantic guarantee. |
| `adapters/sqlite/p1_ddl/fingerprints.json` | Future schema/guards/fingerprints change together only under separate implementation authorization; untouched here. |

Baseline outer Exchange caps are 32 MiB, depth 32 and 200,000 elements; selection
defaults are depth 8, 10,000 units, 16 MiB and 10,000,000 work units
(`domain/exchange.py:27,234`). These differ from individual identity proposals.
Embedded escaping/wrappers consume extra enclosing budgets, so an ID passing its
cap need not fit every containing unit. No defaults change in this PR.

## U3=C′ experiment handoff

The separate experiment agent must supply exact experiment commit/tree, actual
SQLite version/source ID, scripts/schema/helpers, commands, assertions and
failures/limits. Preserve the [acceptance contract](../architecture/context-resource-schema.md#u3c-experimental-acceptance-contract):

- Existing resource_relations owns Parent. No new domain/header table, surrogate
  or contradictory resources Parent authority.
- Complete child survives missing Parent; relationship/Transfer does not. Parent
  arrival alone cannot synthesize or replay a withheld report.
- Typed SQL references retain actual Issue/Event/support-report coordinates;
  admission separately checks event semantics. Neither proves authenticity.
- Distinct reports, coherent membership, original clocks and alternatives survive.
- NULL/CHECK/FK, REPLACE/UPSERT, no-op replay, savepoint/transaction/COMMIT and
  re-supply cannot bypass required guarantees.

Publish the Draft with this gate open rather than waiting indefinitely. Later
available evidence must be cited at its own exact commit and limits; it is not a
new execution in this design PR. Failure returns a concrete finding and affected
implementation stage to the owner, not silent architecture substitution.

## Proposed later implementation and validation sequence

This dependency plan grants **no implementation permission**.

1. Close/review U3=C′ and confirm logical guarantees. Handle actual substantive
   conflicts through governance. Keep independent serializer design reviewable.
2. Freeze shared identity parser/encoder, bounds, exact key representation and
   known-contract dispatch. Execute schema specification vectors: Unicode,
   escapes, empty/nested coordinates, huge decimal strings and exact limits.
   Cross-check encoding, canonical input, SQL and embedded references.
3. Implement coherent schema/UDF/index/FK/admission changes in a separately
   authorized stack. Verify direct SQL and typed APIs, child-before-Parent,
   missing/wrong Event support, original-report re-supply and all mutation paths.
4. Update supported common Exchange format/selection/validation together. Test
   unknown kinds, known-invalid opaque fallback, unknown versions, denied/omitted/
   missing dependencies, bounded cycles, multi-member/Transfer atomicity, reverse/
   repeat/late re-supply, and finite limits. Forged-but-rechecksummed packages
   remain subject to domain checks; changed identity needs new package content ID.
5. Verify typed reads, exact text, Search scan/fallback/rebuild, original-clock
   Coverage/five columns, Source positives, competing immutable mapping claims
   and qualified Dispositions. Verify paired backup/restore semantic/FK checks,
   unknown-kind roundtrip and independent Access exclusion on disposable fixtures.
6. Independently review frozen implementation commits and reconcile later trees.
   Run risk-appropriate development checks. Full release qualification, merge,
   deployment, real-data operations and P8 remain separate.

Provider ID selection, lifecycle/reuse normalization and new adapters are outside
this task. Broader actor/file-position conventions, structured Search and
cross-domain Coverage summaries are not silently selected. No API archive,
universal edit history, ordinary blob-body retention, Mapping Witness,
Publication, new link store, legacy compatibility or real-data migration.

## Documentation validation and independent review

Applied procedures: repository adr-workflow, efficient-repository-investigation,
lessons-to-skills and exact-tree CI, plus cloud runtime guidance. Parallel
code-contract/ADR research is useful input, **not independent package review**.
A different reviewer must inspect a frozen authored commit read-only, including
metadata/index, clauses, canonical vectors, U3 gate, scope and skill changes.
The [review and verification record](evidence/context-resource-design/README.md)
records actual reviewed commit/tree, findings and post-review changes.

Checks cover prose validation, strict UTF-8, frontmatter/index, local links/anchors,
balanced fences and exact-parent diff scope/whitespace. Vectors remain
specifications unless explicitly executed. A full product suite is unnecessary
for this documentation PR and is not claimed. Before submission, reread live
#113/main, verify parent branch unchanged, and report actual base/head/tree. No
predecessor badge is this PR's check.
