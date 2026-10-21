# Generalized Context Resource design handoff

## Status and authorization

[ADR 0031](../adr/0031-generalized-context-resources.md) is **owner-accepted**
as of **2026-10-21** (`status: accepted`, `date: 2026-10-21`). The owner
accepted the complete design after independently reviewed G3=A SQL proof, with
the express statement 「ADR 0031 を受け入れます。」. A3, B3, U3=C′, U4=B,
U5=A, U1=B, U2=A, U2-E2 and Q-S10-specific G3=A remain fixed. Exact physical
mechanisms and finite limits called engineering proposals remain subject to
implementation review. Acceptance does not grant implementation or merge authority.
The [schema contract](../architecture/context-resource-schema.md) contains the
grammar, equality, specification vectors, dependency behavior, authority
boundaries, ADR matrix and experimental acceptance contract.

**OWNER DESIGN ACCEPTED (2026-10-21).** The G3=A SQL delta was independently
reviewed on real supported SQLite runtimes before approval. The owner's
whole-package acceptance is now recorded separately from implementation
authorization. Prior C′/G1/G2 evidence retains its reviewed scope. Product
integration remains unimplemented. The [evidence map](evidence/context-resource-design/cprime-integration.md)
and [G3=A receipts](evidence/context-resource-design/g3-a/README.md) distinguish
historical evidence from the new proof; no old F2 result is promoted.

The earlier G3=A task authorized documentation, disposable SQL experiments,
independent review and ordinary publication on Draft PR #114. This subsequent
owner acceptance authorizes recording the decision status and synchronizing its
living index/handoff and PR description; it does not authorize production code,
packaged DDL/fingerprint, dependency/test/workflow/runtime changes, new PRs,
merging or retargeting #113/#115, auto-merge, release, deployment, P8 or
real catalog, backup, credential or Provider-account operations.

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
by later inspection of #115. Main and #113 remain at the values above. This
G3=A revision starts from #114 HEAD
`3e6debe41f8e75f0a75be3a71cb1b12a0b70f0f5`, tree
`87c4a5963e6fc15e43d919b884907251f038178d`; the original authoring started from
`5244b98a9a302f082a07a526480faf438fc91838`. Inspected #115 HEAD
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
| Owner-selected logical choices | Open kinds with reserved known contracts; Provider-scoped meaning; existing PK triple; canonical String/recursive Array identity; meaningful empties; semantic Parent in resource_relations; complete-child admission with original-report re-supply; generic unknown-kind preservation/exchange; G3=A native I7 as semantic Issue only for Q-S10. |
| Preserved accepted contracts | Genuine PR-document coordinates; six Repository roles; immutable claims/qualified Dispositions; typed Issue Timeline Event SQL references plus event-semantic admission; five stores; original clocks/provenance; Source positives; five-column Coverage; exact text; PackageKey/digest behavior. |
| Engineering specification / demonstrated candidate | Context ASCII-escaped identity profile and BINARY equality; one canonical namespace-TEXT scoped-document encoder; explicit independent/scoped Document contracts; supplied and independently tested SQL support-key/projection/replay mechanisms. Numeric ceilings remain engineering proposals requiring integrated validation. |
| Demonstrated subset | Typed Parent/Timeline Event SQL references, exact support reports, NULL/replay/mutation protections, child-before-Parent and whole-unit admission at the frozen experiment, including G1/G2 corrections. |
| Decided G3=A boundary | An attributed I8 Parent report may be retained but is permanently ineligible to support Transfer for this I7-native Event. Missing correct I7 support is a re-suppliable dependency, not that violation. Historical F2 temporary QualificationRequired is not the current rule. |
| Product limitations | Production encoding/DDL/readers/writers, Exchange/selection, stored validation, backup/recovery, Search and packaging remain unimplemented for this format. |
| Package state | **Owner-accepted ADR 0031, dated 2026-10-21**, with bounded G3=A SQL proof and independent review. Draft #114 remains unmerged; production-implementation authorization, runtime integration and distribution verification remain separate. |

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

G1/G2 are closed within their independently verified scope. **G3=A is fixed**:
retain an admissible I8 Parent report unchanged, but reject its use as Transfer
support for this I7-native Event permanently as a Q-S10 contract violation. Do
not classify that mismatch as awaiting further qualification, delete/correct the
report or choose a winner automatically. Missing I7 Resource/report or other
required support instead withholds the dependent unit; Parent arrival alone does
not replay it, and the original report must be resupplied with its original
identity, provenance and times. Matching I7 is necessary, never sufficient.

The new SQL delta must link the sole generated support payload to the same
Event's typed `timeline_event`/`issue` native-I7 metadata, while keeping the full
ParentReportKey FK and endpoint-to-full-EventReportKey FKs. Canonical namespace
metadata must agree with Identity; it is not another semantic Parent authority.
Do not apply native equality to general Parent reports or restore a Parent
existence FK on child Resources. Merely mentioning I7 in Identity establishes
none of its Resource row, report, qualified event, endpoints, original evidence
or Provider authenticity. Parent and Event reports may have independent genuine
provenance, clocks and observation times; preserve their complete keys rather
than requiring identical evidence values.

All ordinary SQL connections must enable the documented FKs/triggers and
register every required bounded deterministic UDF. A predicate that SQL always
evaluates is a SQL constraint; a caller-optional admission function is not. UDFs
must not hide table searches or external queries. SQL does not authenticate
Provider reports. Actual event semantics, original timestamp input types,
declared-member/endpoint completeness and whole-unit transaction admission
remain separate application duties. Arbitrary direct SQL is not claimed to
supply whole-unit atomicity.

The external #115 experiment remains outside #114 ancestry. Use stable links;
do not import/cherry-pick its branch. Preserve failed receipts, original F1
results, F2 executable bytes, R2 review/publication provenance and their separate
scopes. New G3=A disposable inputs and receipts belong to the new evidence
directory; they do not retroactively change F2's structural I8 counterexample or
its temporary QualificationRequired behavior.

## Proposed later implementation and validation sequence

This dependency plan grants **no implementation permission**.

These are planned future work units, not implementation PRs authorized by
this acceptance record. A non-author reviewer must inspect each frozen unit; re-review material
corrections and bind the final integrated inputs.

| Unit | Dependency and work | Verification and independent gate |
| --- | --- | --- |
| D0 — G3=A acceptance preparation | Reflect the explicit 2026-10-21 decision, demonstrate the bounded SQL delta on frozen disposable inputs, and obtain non-author review with independent major-counterexample execution. No new A/B selection. | Native-I7 SQL refusal of I8 support, retained I8 report and correct-I7 positive/dependency cases; actual minimum/newer runtimes, error/rowset/transaction receipts and frozen review. The owner accepted ADR 0031 on 2026-10-21; implementation and merge require separate authorization. |
| I1 — shared ResourceKey | After design acceptance and implementation authorization, share strict parser/encoder, Unicode/scalar validation, finite bounds and BINARY equality. Use one namespace-TEXT scoped encoder and explicit native-contract dispatch. | Positive/negative vectors, empty/nested/huge IDs, exact limits, malformed canonical input and API/SQL/reference agreement. Review no dropped PR coordinates or unknown-kind reinterpretation. |
| I2 — generalized Resources | Depends I1. Update packaged DDL/composer/functions/index/fingerprint together; complete global/scoped identifying metadata without semantic Parent FK/authority. Keep ResourceKey triple and Provider registration. | Direct SQL omitted/partial contracts, global scalar/composite Documents, typed absence projection and all conflict verbs. Review no surrogate/table and unchanged five Coverage columns. |
| I3 — Parent reports | Depends I1/I2. Extend resource_relations, full-key index, deterministic target/source projections, complete non-NULL CHECKs and typed FKs. No independently writable projection. | Child-before-Parent, absent referent FK errors, original re-supply, independent provenance/clocks, Document children and attributed alternatives. Review sole report authority and no inferred winner. |
| I4 — G3=A Transfer SQL | Depends I1–I3 and completed D0 preparation after whole-design acceptance/separate implementation authorization. Add native-I7 typed Resource UNIQUE/reference guarantees from the sole generated support payload; keep exact complete ParentReportKey and endpoint-to-EventReportKey FKs, full scope/member/provenance coordinates, required non-NULL/CHECK guards and immutable pre-conflict guards. Keep six roles; no general Parent equality or child Parent-existence FK. | Direct SQL without Admission rejects I8 support, wrong Event/service/kind/subtype, absent/mixed support, NULL/noncanonical values, IGNORE/DO NOTHING/REPLACE/UPSERT rebinds and same-key changed payload. Review the actual I7 SQL constraint, matching collation/UNIQUE, generated nonwritable projections and required UDF/FK/trigger connection configuration. |
| I5 — typed Admission | Depends I1–I4. Distinguish permanent Q-S10 ineligibility of I8 support from missing correct-I7 dependencies that may be retried by original-report resupply. Eligible I7 support still requires actual normalized event type, native contract, declared Provider members, strict original timestamps and complete supplied endpoints. Savepoint the whole unit; no hidden queue or replay merely on Parent arrival. Preserve independent Parent/Event provenance, clocks and times. | Wrong-I8 input is a Q-S10 violation before writes; missing I7 row/report/member is dependency refusal. Test second-endpoint failure rollback, genuine one-sided versus truncated reports, original resupply, bool/float/string times before affinity and exact idempotent replay. Review SQL existence versus semantics/authenticity and Admission transaction atomicity. |
| I6 — relations, Collections, scoped Exchange | General Relation/Collection/Exchange work depends I1–I3; its Transfer portion also depends I4/I5. Preserve unknown kinds/common format, ordered groups, absent/empty/partial/complete terminals, explicit selection/permission, finite cycles and whole-group dependency closure. | Revalidate Transfer eligibility on replay/import; a stored row or sender verified flag is no approval. No blanket Provider selection, fabricated referent, shrunk complete group, generic-array FK claim or unknown-version fallback. Reverse/repeat/late onward Exchange, forged-but-rechecksummed inputs, original clocks and changed-content/new-PackageKey. These product paths are not executed by the bounded G3 experiment; independent Q-E5/Q-E6 review remains mandatory. |
| I7 — stored validation and backup/recovery | Depends on the persistent forms of I1–I6. Update fingerprints and stored semantic validators; consistent Core+Context pairing, separate Access scope and ADR 0026 stop/salvage/fresh-restore rules. | Revalidate every recovered/replayed Transfer against current eligibility; stored rows or verified flags cannot approve an ineligible unit. Unknown/global/scoped roundtrips, invalid stored typed units despite clean FK checks, actual original evidence and retained bytes. Product backup/recovery paths remain unexecuted by the bounded experiment; independent recovery review is required and SQLite copying/integrity alone is insufficient. |
| I8 — queries and Search | Basic reads can proceed in parallel from I1–I3. Transfer consumers and final integration must agree with I4–I7. Consistent typed reads/text projection, Source positives/Coverage and unresolved alternatives. | Query/scan/fallback/rebuild equivalence, generation fences, unknown-kind readability and nonleaf Documents. An unqualified Transfer must not become effective through a stored/search flag. Do not promise arbitrary structured-field Search or unrelated adapters. |
| V1 — supported runtimes | Apply throughout I1–I8; freeze coherent integrated inputs. Run actual minimum SQLite 3.51.3 and a newer supported runtime with source IDs/options/pragmas and exact collected/executed cases. | Old/new adversarial units, schema/FK/integrity, transactions/reopens and misconfiguration controls. Independent execution separates SQL errors from Python validation; no version spoofing or inherited PASS. |
| V2 — distributions and final tree | After I1–I8 and stage-wise V1, build isolated wheel and sdist-derived wheel and execute both outside checkout. Independently verify bundled DDL/UDF/fingerprints and final integrated tree; reconcile actual feature/test-merge parents and effective tree, including later changes. | Package-installed schema/roundtrip/validation on supported runtimes, input/output hashes and independent final-tree confirmation. These product distribution checks are future work; full release qualification requires separate authorization and green development checks do not authorize merge/release/P8. |

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
including metadata/index, clauses, canonical vectors, fixed G3=A, original
F1/F2 evidence versus new SQL-delta receipts, all eight obligation mappings,
stable citations and the proposed state at the frozen pre-acceptance checkpoint. That reviewer independently executes the
major SQL counterexamples against the frozen inputs; initial parallel research
is not a substitute. Material semantic/constraint corrections require re-review.
The [review and verification record](evidence/context-resource-design/README.md)
records actual reviewed commit/tree, findings and post-review changes.

Checks cover prose validation, strict UTF-8, frontmatter/index, local links/anchors,
balanced fences and exact-parent diff scope/whitespace. Vectors remain
specifications except exact cases bound to cited receipts. A full product suite is unnecessary
for this documentation PR and is not claimed. Before submission, reread live
#113/main, verify parent branch unchanged, and report actual base/head/tree. No
predecessor badge is this PR's check.
