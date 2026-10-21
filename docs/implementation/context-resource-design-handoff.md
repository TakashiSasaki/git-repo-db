# Generalized Context Resource design handoff

## Status and authorization

[ADR 0031](../adr/0031-generalized-context-resources.md) is **proposed**, with
`date: null`. The owner has selected A3, B3, U3=C′, U4=B, U5=A, U1=B, U2=A and
U2-E2; the package records these without reopening them. Acceptance of the
complete package, physical realization and engineering proposals is separate.
The [schema contract](../architecture/context-resource-schema.md) contains the
grammar, equality, specification vectors, dependency behavior, authority
boundaries, ADR matrix and experimental acceptance contract.

**NOT YET READY for owner design acceptance:** bounded C′ structural feasibility
and G1/G2 corrections are independently demonstrated. G3 remains one semantic
owner-decision blocker. Product integration is still unimplemented. The
[evidence map](evidence/context-resource-design/cprime-integration.md) identifies
each demonstrated obligation and enforcement layer.

This task authorizes documentation, checks, branch push and a Draft PR. It does
not authorize implementation, accepted-ADR body edits/retirement, production
Python, packaged DDL/fingerprints, dependencies, existing runtime tests, workflows
or default-runtime changes. Only existing design PR #114 is updated; do not
modify/retarget PR #113 or #115. Merge, auto-merge, release, deployment, P8, real catalogs, backups,
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

At original authoring only #113 was public; that historical absence is superseded
by this revision's inspection of #115. Main and #113 remain at the values above;
#114 starts from `5244b98a9a302f082a07a526480faf438fc91838`, and inspected #115 HEAD
is `8ab57eb74068f5ba303b5985a335f0f76be4fdd2`. The latter publishes review of
executable freeze `9eeacb28f7e4a426114a9ce40e2324b4da302817`, not an execution of
that later HEAD. [Complete provenance](evidence/context-resource-design/cprime-integration.md#provenance-and-dependency-ledger)
includes F1/F2/report trees and input hashes. No new ADR number is allocated.

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

## Fixed, demonstrated and unresolved boundaries

| Category | Contents |
| --- | --- |
| Owner-selected logical choices | Open kinds with reserved known contracts; Provider-scoped meaning; existing PK triple; canonical String/recursive Array identity; meaningful empties; semantic Parent in resource_relations; complete-child admission with original-report re-supply; generic unknown-kind preservation/exchange. |
| Preserved accepted contracts | Genuine PR-document coordinates; six Repository roles; immutable claims/qualified Dispositions; typed Issue Timeline Event SQL references plus event-semantic admission; five stores; original clocks/provenance; Source positives; five-column Coverage; exact text; PackageKey/digest behavior. |
| Engineering specification / demonstrated candidate | Context ASCII-escaped identity profile and BINARY equality; one canonical namespace-TEXT scoped-document encoder; explicit independent/scoped Document contracts; supplied and independently tested SQL support-key/projection/replay mechanisms. Numeric ceilings remain engineering proposals requiring integrated validation. |
| Demonstrated subset | Typed Parent/Timeline Event SQL references, exact support reports, NULL/replay/mutation protections, child-before-Parent and whole-unit admission at the frozen experiment, including G1/G2 corrections. |
| Semantic blocker | G3: whether native Issue I7 or separately qualified reported Parent I8 determines Q-S10 eligibility. Temporary mismatch withholding does not decide the rule or close required SQL proof. |
| Product limitations | Production encoding/DDL/readers/writers, Exchange/selection, stored validation, backup/recovery, Search and packaging remain unimplemented for this format. |
| Package state | Proposed documentation, date null; NOT YET READY for complete acceptance. Experimental verification is not package approval or product implementation. |

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

## U3=C′ evidence handoff

The completed experiment supplies exact inputs, actual SQLite 3.51.3/3.53.1
source IDs, scripts, assertions, errors, rowsets and independent review. Use the
[eight-obligation map](evidence/context-resource-design/cprime-integration.md#acceptance-obligation-map)
and preserve the [acceptance contract](../architecture/context-resource-schema.md#u3c-experimental-acceptance-contract):

- Existing resource_relations owns Parent. No new domain/header table, surrogate
  or contradictory resources Parent authority.
- Complete child survives missing Parent; relationship/Transfer does not. Parent
  arrival alone cannot synthesize or replay a withheld report.
- Typed SQL references retain actual Issue/Event/support-report coordinates;
  admission separately checks event semantics. Neither proves authenticity.
- Distinct reports, coherent membership, original clocks and alternatives survive.
- NULL/CHECK/FK, REPLACE/UPSERT, no-op replay, savepoint/transaction/COMMIT and
  re-supply cannot bypass required guarantees.

G1/G2 are closed within their independently verified scope. G3 requires owner
review of the precise alternatives in the schema contract. Retain I8 as an
attributed report without treating structural support as qualified Transfer
admission. No default equality policy, silent Q-S10 amendment or inferred report
authenticity is permitted. The affected work is Transfer qualification and broad
acceptance, not the demonstrated SQL construction as a whole.

The experiment remains outside #114 ancestry. Use stable links; do not copy
the branch solely for citations. Preserve failed receipts, original F1 results,
F2 executable bytes, R2 review/publication provenance and their separate scopes.

## Proposed later implementation and validation sequence

This dependency plan grants **no implementation permission**.

These are future authorized work units, not implementation PRs created by this
task. A non-author reviewer must inspect each frozen unit; re-review material
corrections and bind the final integrated inputs.

| Unit | Dependency and work | Verification and independent gate |
| --- | --- | --- |
| D0 — Q-S10 decision | Owner resolves G3, specifies Issue eligibility/evidence and reviews any substantive ADR carry-forward. Keep unaffected identity design independently reviewable. | Explicit acceptance source; no implied choice from temporary withholding. Specify scoped SQL and semantic criteria before dependent Transfer work. |
| I1 — shared ResourceKey | After design acceptance and implementation authorization, share strict parser/encoder, Unicode/scalar validation, finite bounds and BINARY equality. Use one namespace-TEXT scoped encoder and explicit native-contract dispatch. | Positive/negative vectors, empty/nested/huge IDs, exact limits, malformed canonical input and API/SQL/reference agreement. Review no dropped PR coordinates or unknown-kind reinterpretation. |
| I2 — generalized Resources | Depends I1. Update packaged DDL/composer/functions/index/fingerprint together; complete global/scoped identifying metadata without semantic Parent FK/authority. Keep ResourceKey triple and Provider registration. | Direct SQL omitted/partial contracts, global scalar/composite Documents, typed absence projection and all conflict verbs. Review no surrogate/table and unchanged five Coverage columns. |
| I3 — Parent reports | Depends I1/I2. Extend resource_relations, full-key index, deterministic target/source projections, complete non-NULL CHECKs and typed FKs. No independently writable projection. | Child-before-Parent, absent referent FK errors, original re-supply, independent provenance/clocks, Document children and attributed alternatives. Review sole report authority and no inferred winner. |
| I4 — Transfer SQL | Depends D0/I2/I3. Integrate exact Parent/event support FKs, full scope/member/provenance coordinates, endpoint CHECKs and pre-conflict immutable guards. Keep EventReportKey and six roles. | Wrong Event/kind/subtype, absent/cross-paired support, NULL, IGNORE, REPLACE, both UPSERT actions and same-key changed payload. Review owner-resolved Q-S10 SQL requirement, not merely Python equality. |
| I5 — typed admission | Depends I1–I4/D0 for Transfer. Check actual normalized event type, native contract, declared Provider members, strict original timestamps and complete supplied endpoints. Savepoint whole units; withhold/report missing dependencies without hidden queues; re-supply originals. | Second-endpoint FK rollback, one-sided versus truncated reports, missing-member re-supply, bool/float/string times before affinity, replay and G3 qualification. Review separate SQL existence, semantics, authentication limits and atomicity. |
| I6 — relations, Collections, scoped Exchange | Depends I1–I3 and I4/I5 for Transfer. Preserve unknown kinds/common format, ordered groups, absent/empty/partial/complete terminals, explicit selection/permission, finite cycles and whole-group dependency closure. | No blanket Provider selection, fabricated referent, shrunk complete group, generic-array FK claim or unknown-version fallback. Reverse/repeat/late onward Exchange, forged-but-rechecksummed inputs, original clocks and changed-content/new-PackageKey. Independent Q-E5/Q-E6 review. |
| I7 — stored integrity and backup/recovery | Depends all persisted forms I1–I6. Update fingerprints and stored semantic validators; consistent Core+Context pairing, separate Access scope and ADR 0026 stop/salvage/fresh-restore rules. | Unknown/global/scoped roundtrips, invalid stored typed units despite clean FK checks, actual original evidence and retained bytes. Independent recovery review; SQLite copying/integrity alone is insufficient. |
| I8 — queries and Search | Depends I1–I3 and I4/I5 for qualifying report consumers; integrate I6/I7 before final acceptance. Consistent typed reads/text projection, Source positives/Coverage and unresolved alternatives. | Query/scan/fallback/rebuild equivalence, generation fences, unknown-kind readability and nonleaf Documents. Do not promise arbitrary structured-field Search or unrelated adapters. |
| V1 — supported runtimes | Apply throughout I1–I8; freeze coherent integrated inputs. Run actual minimum SQLite 3.51.3 and a newer supported runtime with source IDs/options/pragmas and exact collected/executed cases. | Old/new adversarial units, schema/FK/integrity, transactions/reopens and misconfiguration controls. Independent execution separates SQL errors from Python validation; no version spoofing or inherited PASS. |
| V2 — distributions and final tree | Depends V1 and all reviewed units. Build isolated wheel and sdist-derived wheel; verify packaged DDL/UDF/fingerprints and execution outside checkout. Reconcile actual feature/merge parents and effective tree, including later changes. | Package-installed schema/roundtrip/validation on supported runtimes, input/output hashes and independent integrated-tree review. Full release qualification requires separate authorization; green development checks do not authorize merge/release/P8. |

Provider ID selection, lifecycle/reuse normalization and new adapters are outside
this task. Broader actor/file-position conventions, structured Search and
cross-domain Coverage summaries are not silently selected. No API archive,
universal edit history, ordinary blob-body retention, Mapping Witness,
Publication, new link store, legacy compatibility or real-data migration.

## Documentation validation and independent review

Applied procedures: repository adr-workflow, efficient-repository-investigation,
lessons-to-skills and exact-tree CI, plus cloud runtime guidance. Parallel
code-contract/ADR research is useful input, **not independent package review**.
A different reviewer must inspect this frozen authored revision read-only,
including metadata/index, clauses, canonical vectors, G1–G3, original experiment
receipts, all eight obligation mappings, stable citations and proposed state.
The [review and verification record](evidence/context-resource-design/README.md)
records actual reviewed commit/tree, findings and post-review changes.

Checks cover prose validation, strict UTF-8, frontmatter/index, local links/anchors,
balanced fences and exact-parent diff scope/whitespace. Vectors remain
specifications except exact cases bound to cited receipts. A full product suite is unnecessary
for this documentation PR and is not claimed. Before submission, reread live
#113/main, verify parent branch unchanged, and report actual base/head/tree. No
predecessor badge is this PR's check.
