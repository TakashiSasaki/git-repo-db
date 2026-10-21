# Provider identity and generic resource investigation (A/C)

Investigator report, **not independent review**. Frozen product commit:
`efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`, tree
`117d580b31098ecb8287281bd843894fdfad71fc`. Investigation and public-source
retrieval date: 2026-10-19 UTC. The dates reflect actual execution, rather than
assuming the task's 2026-10-20 reference date. Product code and ADRs are unchanged.

Read repository `AGENTS.md`, ADR index/operating policy, relevant ADR 0029/0030
clauses, and the `efficient-repository-investigation`, `three-store-invariants`
and `lessons-to-skills` procedures. Their historical baseline instructions do
not supersede the actual target source. No new skill is warranted by these
ordinary bounded inspections/probes; no speculative recipe was installed.

## Result and supported scope

The storage identity layer is service-instance scoped, and substantial generic
metadata support already exists. It is not, however, a complete arbitrary
Provider-resource model: the physical resource enum and document parenting are
closed, while non-GitHub normalization and several semantic targeting contracts
are absent. Encoding JSON is not evidence of a standardized interoperable meaning.
The observed rejections obey the current schema; none below is established as
an Implementation Defect or an inherent Architectural Conflict.

### Identity and physical model

- `providers.service_instance_uuidv4` is a portable UUIDv4 namespace. `provider_kind`
  is a nonempty descriptive string, not part of ResourceKey and not an enum.
  Provider kind cannot be rebound for an existing service UUID through the
  production API. Two installations of the same Provider need distinct service
  identities. Different kinds or URLs do not themselves allocate namespaces.
- ResourceKey is `(service_instance_uuidv4, resource_kind, provider_resource_id)`.
  IDs are nonempty strings; typed ResourceKey checks do not enforce the DDL's kind
  enum or understand provider ID scope. A project-local number without its actual
  namespace collides. Adapters must use a genuine global ID or a reversible,
  explicitly namespaced composite of actual identity coordinates. Hashes, URLs,
  inferred repository UUIDs and randomly assigned per-row IDs are not substitutes.
- `repository`, `pull_request`, `issue`, `review`, `comment`, `thread`, `document`,
  `assessment`, `identity`, `endpoint`, `annotation`, `lfs` are the **12** allowed
  resource kinds. `discussion`, `event`, `commit`, `analysis_result` are rejected.
  A Git commit is represented by typed OID reference, not by inventing a Provider
  `commit` resource kind.
- `review` and `document` require a `pull_request` parent; `thread` requires
  `pull_request` or `review`; `comment` requires `pull_request`, `issue`, `review`
  or `thread`. Their provider-resource ID is the canonical array
  `[parent_kind,parent_id,document_kind,provider_document_id]`; all four coordinates
  are actual identity components. These rows have a same-service composite parent
  FK. Other kinds cannot use these physical parent columns.
- Ordinary Issue identity excludes current repository membership and display
  number. Rename/URL changes therefore need not rekey a stable provider ID.
  Provider-side association and Core mapping remain separate. The schema cannot
  determine that an upstream ID was reused for a new entity: an unchanged triple
  is a replay. An actual upstream generation/incarnation coordinate, if supplied,
  needs a defined adapter identity policy. No observed source here proves routine
  ID reuse for any of the four Providers; reuse is a **hypothetical** stress case.
- A child whose provider ID is globally independent still has parent-bound local
  identity in the four document kinds. Reparenting the same native document ID
  creates a second ResourceKey. That is the settled current document contract,
  not a claim that any retrieved Provider actually supports this move.

Source: [ResourceKey][key], [Context DDL][ddl], [resource admission][admit],
[provider binding][provider], [ADR 0017][adr17], [ADR 0030][adr30].

## Official Provider comparison and evidence

`provider-sources.json` records URLs, actual fetch status, retrieval time, full
response SHA-256/byte count and bounded source excerpts. HTTP failures are retained
honestly. These are public documentation/specification requests; no Provider
account, credentials, catalog or private payload was used. Example IDs in tests
are **synthetic fixtures derived from documented semantics**, never live records.
Unversioned documentation can change; hashes identify what was fetched, while
excerpts retain the claim-bearing text. Gitea comparison deliberately uses the
versioned v1.23 specification after current docs were inaccessible.

| Provider | Documented identity and associations | Implication for current Context |
| --- | --- | --- |
| GitHub | REST issue endpoint uses owner/repository/issue number; response distinguishes `id`, `node_id`, `number`. Official GraphQL guide describes global node IDs and REST-to-GraphQL lookup. | Existing normalizer uses decimal database IDs or explicit `['github:node_id',opaque]`; repository GraphQL normalization intentionally preserves opaque node namespace even with database ID present. No decoding/equating node and numeric IDs. Current issue/PR/comment/review shapes fit; repository Discussions are outside the enumerated model. |
| GitLab | Official REST source: `id` unique across all projects, `iid` only within a project; examples distinguish project 42, issue id 46, iid 5. Discussion endpoints exist for issues, merge requests, snippets and commits; discussion notes carry their own IDs and file/diff positions. | Global issue `id` can fit existing issue ResourceKey. A bare `iid` cannot. Issue discussion as `thread` is rejected; commit discussion requires an explicit modeling choice because there is no Provider commit kind and thread parenting is closed. No GitLab normalizer is shipped. |
| Gerrit | Current REST docs recommend `<project>~<changeNumber>`; alternatives include `<project>~<branch>~<Change-Id>`, bare Change-Id or change number only if unique. Change-Id is unique per repository/branch. Published comment and robot-comment UUIDs, file paths, revision/patchset and comment ranges are separate coordinates. | A bare Change-Id is insufficient. A canonical explicit compound coordinate can be stored. Calling every Gerrit change `pull_request` is an adapter semantic decision, not proven by string acceptance. Comment/analysis targeting revision and position needs a precise normalization contract. No Gerrit normalizer is shipped. |
| Gitea v1.23 | Official Swagger defines `/repos/{owner}/{repo}/issues/{index}` with repository-local index, Issue `id`/`number`, comment `id` and pull review endpoints/types; pull-review payload includes `commit_id`. | Do not use bare issue index as service-wide identity. Existing PR/review/comment shapes can represent relevant normalized data, but namespace stability, parent semantics and commit-role conventions need an adapter contract. No Gitea normalizer is shipped. |

Checked public specifications:

- GitHub: <https://docs.github.com/en/rest/issues/issues> and
  <https://docs.github.com/en/graphql/guides/using-global-node-ids>.
- GitLab: <https://raw.githubusercontent.com/gitlabhq/gitlabhq/master/doc/api/rest/_index.md>
  and <https://raw.githubusercontent.com/gitlabhq/gitlabhq/master/doc/api/discussions.md>.
  Rendered `docs.gitlab.com` requests returned HTTP 403; the official source
  mirror supplied the actual evidence.
- Gerrit: <https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html>.
- Gitea: <https://raw.githubusercontent.com/go-gitea/gitea/release/v1.23/templates/swagger/v1_json.tmpl>.
  Current rendered documentation returned HTTP 403 and attempted `main` raw
  path returned HTTP 404. No claim of having inspected the latest Gitea release.

Identity under move/rename is only as strong as the actual provider's immutable
ID guarantee. Stable global IDs should survive changing labels; a compound ID
containing mutable project/branch/path requires explicit provider semantics or
an attributed identity relationship. The database cannot infer continuity from
URL/name/OID matches. New-provider adapters must specify this before acquisition.

## Annotation, assessment and relation capability matrix

| Target / concern | Current usable representation | Limit and evidence |
| --- | --- | --- |
| Repository description/annotation | Existing repository fields; independently identified `annotation` + typed `ResourceRelation` to provider repository; exact Context text | PR06 persists and reads independent annotation, text and relation. No false PR needed. Custom relation name retains declared meaning but has no domain-specific targeting policy. |
| Commit / any Git object | Independent `assessment`/`annotation` + `CoreReference` with `(object_format,full_oid)` and role | PR07 preserves unavailable OID as reported reference, `required=False, available=False`; required `link_core` rejects missing target. OID does not prove commit type, membership, body, verification or canonical truth. |
| Specific file / location at commit | Possible structured fields carrying path, base/head/commit OIDs, side and line/range; generic target relations | No first-class typed file-location value, line semantics, path-byte encoding or validation contract identified. JSON roundtrip alone cannot establish target identity equivalence. No file body retention is required or authorized. |
| Provider Resource | Generic `ResourceRelation` with actual ResourceKey members | Admission validates member existence; reserved `reviews/comments/threads/documents` kinds additionally enforce child owner/kind. Cross-provider members are possible for generic names, but intended semantics require a contract. |
| Multiple repositories | Multiple provider repository members in a generic relation | Can preserve provider-side references; ADR0030 six Core-repository roles do not include generic `annotates_repository`. Do not mislabel annotations as owning Issues or mappings. Core UUID attachment may need future relation policy. |
| Information source / author / publisher | Required provenance has `source` and nonnull `evidence`; author/publisher/local-origin can be explicit current fields | Neither source string nor author/issuer equality authenticates origin. Dedicated normalized roles/policies are not enforced for generic annotations. Local authoring must define its genuine service/resource identity; arbitrary UUID per row is not justified. |
| Time and competing evaluations | FieldClock domain/time separate from observed time; independent assessment IDs and field alternatives | PR08 shows Missing vs explicit null vs disagreeing equal-clock sources. Later comparable field state can replace older state; not a full report/edit archive. For independent reports, preserve each genuine report's ResourceKey, not invented retry IDs. |
| Actual independent event | Issue timeline event is a comment composite with `timeline_event` kind; other event reports may fit assessment/annotation only if their meaning does | No generic event resource kind; renaming an event to a comment/annotation solely to bypass constraints loses semantics. ADR0030 transfer endpoints expressly require Issue timeline events. |

Typed reads return fields, text, parent, all relation kinds, collections and
Core dependencies for every admitted resource, not just GitHub PRs. Search's
Context extractor indexes string-valued fields and referenced exact text for
all resource kinds; structured object/array field values are intentionally not
full-text indexed. Source inspection is not a newly executed Search rebuild
proof. [Typed resource view][query], [Search extractor][search].

Exchange expansion visits actual resource parents and generic relation members;
Provider registration is not a seed for every sibling resource. Typed replay
reuses the original keys. See root audit's full Exchange execution for end-to-end
results; this investigator's **18 probes stop at admission and typed read**, and
do not independently claim export/import or backup completion. [Expansion][expand].

## Executed probes and interpretation

Command from repository root (supported environment selected by coordinator):

```sh
.venv/bin/python -m pytest -c pyproject.toml \
  docs/implementation/evidence/context-provider-agnostic/reproduction/test_provider_resource.py -q
```

Python 3.12.14 / SQLite 3.53.1; 18 passed. The script asserts runtime >=3.51.3,
uses packaged initialization and production `Context.transaction` over pytest
throwaway directories. It does not alter the product default runtime or create
real catalogs. An initial harness assertion used `.resolved` instead of actual
`CoreDependency.available`; corrected after reading the dataclass, then all 18
passed. This harness error is not a product failure. Unified JUnit/JSON receipts
are generated by the coordinating audit run.

| Probe | Count | Actual result | Interpretation |
| --- | ---: | --- | --- |
| PR01 | 2 | Equal IDs in different service UUIDs stay distinct (different/same provider kinds) | Success / Non-Issue |
| PR02 | 1 | Bare project iid produces one identity; qualified actual project+iid coordinates produce distinct identities | Adapter contract gap, not a database duplicate-detection defect |
| PR03 | 5 | Repository/Issue documents, Issue thread, annotation/repository reviews rejected | Specification-compliant refusal; broader requirement gap |
| PR04 | 1 | PR document admitted and read | Positive control |
| PR05 | 4 | Non-enumerated discussion/event/commit/analysis_result kinds rejected | Specification-compliant refusal; extension needs design/contract |
| PR06 | 1 | Repository annotation, text, typed relation and exact replay survive | Existing-schema success |
| PR07 | 1 | Assessment reference to absent OID preserved as report; required link rejected | Existing-schema success |
| PR08 | 1 | Missing, explicit null and competing fields distinct; exact replay deduplicates | Existing-schema success |
| PR09 | 1 | Same native document ID under different parent creates two keys | Hypothetical identity-scope limitation, not observed provider behavior |
| PR10 | 1 | GitHub REST numeric and GraphQL opaque repository IDs remain separate | Existing-schema/normalizer success |

## Finding candidates for audit consolidation

### PR-F01 — Closed resource kinds and PR-bound documents

- **Classification / severity:** Requirement Coverage Gap / Major for the broad
  future scope; not an Implementation Defect.
- **Reproduction / result:** PR03/PR05. Real GitLab Issue/commit discussions motivate
  the hierarchical gap; repository standalone document and non-PR review examples
  are synthetic broader-use cases. All refused at the actual DDL CHECK boundary.
- **Expected meaning:** Preserve actual provider resource identity and actual
  parent/target without fabricating a PR or relabeling the resource.
- **Source / ADR:** [DDL lines 26–44][ddl], [ResourceKey lines 639–677][key],
  [admission lines 75–106][admit]; ADR0029 provider-state boundary, ADR0030 Q-S6/10,
  inherited natural document key contract, ADR0017.
- **Impact:** Normalization, typed API, SQLite, parent-aware reads, selective
  traversal, search projection and compatibility fingerprints; not only INSERT.
- **Options:** Use annotation/assessment only where meaning matches; otherwise
  define new kinds/parent contracts or independent document identity with an
  explicit relation. Existing Context remains natural placement.
- **Accepted specification change?:** Yes for physical enum/parent changes or
  altering the settled document identity; none implemented by this audit.

### PR-F02 — Non-GitHub ID normalization contracts are absent

- **Classification / severity:** Engineering Contract Gap / Major for enabling new
  Providers (no claim they are already promised supported collectors).
- **Reproduction / result:** PR02 preserves only one row when two project-local
  IDs are supplied without scope; canonical project-qualified IDs remain distinct.
  GitLab official docs prove scope distinction; Gerrit docs prove bare Change-Id
  is not generally unique. [GitHub normalization][normalizer] is the only located
  production Provider normalizer.
- **Expected meaning:** Stable, reversible original identity; scope must travel
  with local IDs across acquisition, replay and Exchange.
- **Source / ADR:** [ResourceKey][key], [provider binding][provider],
  [GitHub ID rules][normalizer], ADR0017 and ADR0030 identity constraints.
- **Impact:** New adapters, source clocks, ID translation policy and testing;
  existing generic PK need not change if actual identity can be encoded.
- **Options:** Prefer existing actual global provider IDs; otherwise specify an
  explicit composite namespace and lifecycle policy. Do not mint a surrogate or
  infer stable identity from URLs. Test transfer/rename and replay for each API.
- **Accepted specification change?:** Usually no for meaningful existing kinds;
  genuine upstream ID reuse without a durable occurrence coordinate requires a
  design decision rather than a fabricated repair.

### PR-F03 — Generic target/actor semantics need an engineering contract

- **Classification / severity:** Engineering Contract Gap / Minor until these
  future features are selected; not proof of semantic impossibility.
- **Reproduction / result:** PR06/07 prove generic repository and unavailable-OID
  annotation foundations; code exposes arbitrary field/relation/role strings,
  not a typed file-location/author/publisher/local-origin model.
- **Expected meaning:** Preserve object format/OID, repository if actually
  reported, path/position/side, actor roles and source attribution independently.
- **Source / ADR:** [field candidate][field], [resource relations][relation],
  [reported Core references][core], ADR0005/0008, ADR0017/0028/0029/0030.
- **Impact:** Normalization, typed validation/read/search filters and Exchange
  semantic validation; no automatic need for a new table or independent store.
- **Options:** Define reusable typed values and role vocabulary over existing
  fields/relations first. Add tables only if concrete identity/constraint needs
  cannot be met faithfully. Explicit relation to multiple Core repositories
  must respect the current six-role boundary rather than repurpose it.
- **Accepted specification change?:** Not necessarily for typed value contracts;
  extending Core-repository roles would require design review.

### PR-N01 — Existing generic evidence primitives are useful

- **Classification / severity:** Non-Issue / informational.
- **Reproduction / result:** PR01/04/06/07/08/10: namespace isolation, valid
  documents, independently identified annotations and assessments, exact text,
  generic relations, unresolved typed OID reports and original competing field
  provenance all work through production SQLite and typed reads.
- **Expected meaning / impact:** These can be retained while extending adapters;
  no proof supports moving mappings/annotations out of Context or forcing Core
  target acquisition. Reported references do not authorize ordinary file bytes.
- **Source / ADR:** [provider][provider], [relation][relation], [core][core],
  [field][field]; ADR0005/0008/0014/0017/0028/0029/0030.
- **Response / accepted specification change?:** Reuse; no change required.

## Decisions reserved for the designer

Choose supported new-provider kinds and their stable identity guarantees before
implementation; decide whether any document identity must be independent of
parent; choose explicit file-location/actor semantics; decide whether generic
annotations need direct Core repository relations beyond the six existing roles.
No evidence here justifies a new Mapping/Link store. None of these open choices
reopens permanent repository UUIDs, Core INSERT-only, Coverage columns or the
no-Witness/no-Publication decisions.

[key]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/p1_context.py#L639
[ddl]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql#L26
[admit]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_context.py#L75
[provider]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_context.py#L374
[field]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/p1_context.py#L701
[relation]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_context.py#L520
[core]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_context.py#L995
[normalizer]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/github/production_intake.py#L50
[query]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/application/production_query.py#L1042
[search]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/production_search.py#L508
[expand]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/selective_exchange.py#L578
[adr17]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/docs/adr/0017-domain-keys-without-storage-surrogates.md
[adr30]: https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/docs/adr/0030-context-repository-relations-and-selective-exchange.md
