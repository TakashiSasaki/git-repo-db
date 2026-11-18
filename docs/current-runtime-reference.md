# Current runtime reference: separated persistence

The ordinary `repo-catalog` CLI composes independent responsibility roles. This
is the implemented interface described by the current source, rather than the
former normal Catalog3 / Schema 21 startup. The old DB layout, selector aliases
and command syntax have no compatibility or conversion path. Existing user DBs
are not rewritten or removed by this cutover.

The Repository role defined by [ADR 0044](adr/0044-repository-store-rename.md)
uses repository.sqlite3. Start it in a new empty directory if an earlier
catalog has core.sqlite3. The P1 SQLite family requires user_version 5.
Use backup manifest v4 and Exchange v9 for new backup and interchange data.
Keep legacy catalogs and exports in their original locations.

## Responsibilities, files and classes

| Role | Authority | Initialization |
| --- | --- | --- |
| Repository | Permanent Git identity, attributed metadata and ref observations, intrinsic structure, permitted checked representations and Notes evidence | `init --scope repository` |
| Context | Provider resources, modeled text, original field evidence, Source inventories and relations | `init --scope context` |
| Access | Scope/locator registrations, connection settings and local approvals | `init --scope access` |
| Operational | Reconstructible requests, cumulative work, resumable progress and managed caches | `init --scope operational` |
| Search | Rebuildable projections with exact authority snapshot tokens | `init --scope search` |
| Filesystem | Metadata/digests and complete or partial filesystem scan history | `init --scope filesystem` |
| Worktrees | Repository/worktree observations and qualified optional links | `init --scope worktrees` |

`init --scope paired` chooses Repository and Context together. Each command takes an
explicit `--catalog PATH`; compatible existing selected roles may be reused.
Missing optional roles are not a reason to initialize every store. The role
registry counts schema definitions, not files opened at every startup. Independent
Filesystem/Worktrees CLIs also accept their own explicit DB paths.

The four-role factory remains named
[`p1_schema.py`](../packages/runtime/src/repo_catalog/adapters/sqlite/p1_schema.py)
internally. Its name does not imply an alternative opt-in backend. Access,
Filesystem and Worktrees have their own factories. Use the current factory
fingerprints; there is no exact SQLite version/source-ID pin or cross-version
acceptance claim.

[The canonical persistence mapping](architecture/persistence-model.json) assigns
one dedicated generated row class to each selected table in its owning
namespace distribution. SQL columns, ordered keys, generated fields and FKs come
from actual DDL. Input DTOs, values and query projections are separate bindings.
Generated row modules are stdlib-only; read/write conversion preserves SQL
defaults and rejects invalid original Python primitives rather than relying on
SQLite affinity. Generated/hidden columns are not ordinary write inputs.

```bash
scripts/local-run.sh python scripts/persistence_model.py --check
scripts/local-run.sh python scripts/generate_persistence_rows.py --check
scripts/local-run.sh python scripts/schema_inventory.py --check
scripts/local-run.sh python scripts/audit_implementation_boundary.py --check
```

These are structural/generated-byte checks. They do not prove row semantics,
retained-instance integrity, every install combination or full runtime acceptance.
The neutral schema producer defaults to all current role definitions and never
opens retained DBs. The old `schema-inventory.json` and `table-disposition.*`
remain historical normal-format disposition evidence; current generated artifacts
are `separated-schema-inventory.json` and `separated-persistence-boundary.md`.

## CLI entry points

Start with `repo-catalog --help` and each command's own `--help`. JSON request and
authority files are explicit inputs, not a hidden API-original replay mechanism.

| Command | Work |
| --- | --- |
| `init`, `doctor` | Explicit role creation/reuse and read-only catalog diagnostics |
| `acquire` | Native/local or remote Git, real GitHub REST/GraphQL, frozen mixed-source batches |
| `query` | Git metadata/history/paths/diffs, Context, scoped PR assessment and Search |
| `context` | Explicit typed Context administration |
| `access` | Separate connection and local-approval administration |
| `operations` | Request state, resumptions, finite managed-cache policy and reservations |
| `identity` | Explicit reported equivalence/cancellation assertions without physical merge |
| `exchange` | Selective typed export/import under declared local authority |
| `reparse` | Checked retained metadata/Notes analysis with explicit decoder settings |
| `recording inspect-message` | Bounded inspection of an external supplementary HTTP recording |
| `recovery` | Scoped backup, diagnosis, typed salvage, fresh restore, validated merge and activation |

Select permanent UUIDs and full service/kind/native resource keys. Names, URLs
and UUID-looking descriptions do not establish identity, choose an implicit
Source, or confer permissions. Explicitly permitted original Source references
may remain unresolved when their registration was not selected for transfer;
actual Source-owned operations still require their dependencies and known
service conflicts are refused.

Repository-only metadata reads and Git-only recovery do not require Context,
Operational or Search initialization. Acquisition/resume operations that use
Operational work accounting require that capability explicitly. `doctor` inspects
existing Repository/Context/Operational/Search catalog roles; separate Access and local
catalog administration retain their own verification surfaces. Optional FTS or
Operational telemetry availability does not establish domain completeness or
invalidate sound authoritative facts.

## Current and captured PR queries

`query pr-code --listing-kind pr_files` assesses the requested current file
listing independently of the commit listing. Repeat `--listing-kind` to request
both `pr_files` and `pr_commits`; `query pr-list --assessment code` accepts the
same option. The default current code assessment requests both kinds and Git
metadata. Its current head/base, actual count/cap and required-role checks still
apply before pagination. A complete file listing can coexist with a capped,
partial commit listing.

`query pr-code-capture` reads one immutable original listing. Supply exactly one
`--kind pr_files` or `--kind pr_commits` and its `--provenance-file`. The file
contains either the original provenance as a JSON string or the corresponding
canonical JSON object. Use the actual provenance returned with that collection;
a new descriptive label selects a different identity. For example, after setting
the catalog path, Service UUID and canonical Provider ID JSON from a Resource:

```sh
repo-catalog query pr-code-capture --catalog "$RA_CATALOG" \
  --service-instance "$RA_SERVICE_UUID" --provider-resource-id "$RA_PR_ID_JSON" \
  --kind pr_files --provenance-file original-provenance.json
```

This result has `scope_kind: captured_listing` and
`current_provider_state_asserted: false`. It defaults to Provider evidence;
`--require-git` additionally requests actual matching Git metadata. It preserves
the original terminal, proof, anchors and conflicting member originals even after
the current PR changes. Historical completeness does not certify the current PR.

`query pr-documents`, or `query pr-list --assessment documents`, accepts exact
Provider document `--path` and full `--commit` selectors with an explicit document
`--kind`, such as `review_comments`. `--object-format` selects SHA-1 or SHA-256 for
the commit. In `--mode context_only --no-require-git`, these selectors use actual
captured Provider fields and need no Repository or native file bodies. Required text,
actual parent/thread lineage and whole requested-scope coverage still apply;
the selected documents do not establish Git-byte verification.

## Selecting complete Exchange units

The `--selection` file uses tagged `ExchangeSelectionScope` JSON. Its optional
`collection_keys` contains exact five-part keys:
`(service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind,
original_provenance_json)`. Copy the qualified owner and original provenance from
the actual collection. `all_selected: false` plus these keys selects whole
collection units, including required nominal owners, members, terminal/proof and
Source dependencies. A broad resource selection includes that resource's history;
an exact collection key excludes unrelated sibling collections. Finite export
limits withhold an entire unproven unit instead of truncating its membership.

Context import requires `--authority`; Repository import also retains explicit
`--permit-repository` scope. The root filter and receiver's local admission
selection have separate purposes. Declare finite grants for the required
`resources`, `repositories`, `sources`, `provider_registrations` and any
`object_oids`. The authority file's `selection` carries the local
`AdmissionSelection`: its `resource_keys`, `repository_uuidv4s`, `source_uuidv4s`
and `object_oids` cover the intended dependency targets. An explicit local
`all_selected` remains bounded by those finite grants. Selecting a collection
root alone does not grant its dependencies.
Neither a sender packet nor a sender-verified flag supplies receiver authority.

Genuine later claims on the exact selected collection scope remain transferable.
A later partial claim can make the current projection partial while its older
complete terminal/proof remains unchanged. Reverse and repeated delivery preserve
those immutable originals; ordinary proof admission still checks current evidence.

## Data, work and completeness

Repository is application-level INSERT-only. It retains verified commit/tree/tag
representations and receiver-evidenced Notes bodies; ordinary file-body archival
is excluded. Filesystem scans retain metadata/digests, not file contents.
Context owns modeled Provider text and per-field evidence. Missing and explicit
null differ; actual equal/incomparable-clock alternatives stay visible. A local
revision, later receipt time or preferred decoder/version cannot choose a winner.
Issue identity is independent of current repository membership, and review
identity includes the PR/kind/native-document namespace.

A single explicit request accumulates actual input, metadata and proof work
across retry, resume and every Source in a frozen batch. Failed or rolled-back
processing does not erase spent work. Deliberate finite increases are distinct
from resetting a request. Source ordering/settings and credential references are
frozen; credentials are resolved at use, never persisted inline as plan data.
Scheduling deadline zero is a valid expired deadline; observation/Provider times
retain their positive-when-known rules and native Git author times remain signed.

Source inventory separates Git repository UUIDs from qualified Provider
repository resources. An HTTP repository name/URL cannot invent a Git UUID
mapping. Whole historical inventory/claim/proof units may survive reverse/repeat
transfer and recovery; only the appropriate latest evidence determines current
coverage. Positive associations retain known members during partial refreshes.

PR code assessment needs exact current head/base and any actually captured
required roles, matching captured listings, actual counts/caps and verified
permitted Git metadata. Another PR's resource or a different current target
cannot satisfy that scope. Document/thread assessments retain actual original
root/child lineage. Parent-universe and full requested-scope checks precede result
pagination/filtering; filtered empty output alone never proves completeness.
An API cap or a reported-count mismatch produces `API_CAP` or
`API_COUNT_MISMATCH`: an admitted commit prefix remains usable and an independent
file listing can still complete. Neither scope borrows the other's proof.

Pagination uses explicit item limits and snapshot-bound cursors, with finite
input/text/SQL/output limits. The former fixed 8 MiB automatic page algorithm is
retired. HTTP sync performs a fresh bounded traversal; it does not reproduce the
old automatic first-read-minus-300-seconds `since` cutoff, and may perform more
requests. Conditional ETag reuse and per-PR completed-unit skipping are not
required by this fresh-fetch path; frozen batches still skip completed Sources.
Request retries preserve genuine prefixes, original evidence,
actual deadlines and cumulative accounting.

## Optional Git checks during GitHub acquisition

An `acquire github` request with `operation: "sync"` may include `git_source` to
acquire the actual captured head/base, optional merge and observed review-target
metadata while checking fresh Git refs. This requires an already initialized
Repository plus the explicit Context/admission and Operational capabilities. Without
`git_source`, the HTTP operation can retain Provider facts; that alone does not
prove their required Git metadata is available.

The following is a fragment to add to a complete request, with example UUIDs and
the bytes of `/tmp/repo`. Replace those with the explicitly selected Git Source,
permanent Repository UUID and actual local path; names and URLs do not establish
the association.

```json
{
  "git_source": {
    "kind": "local",
    "source_registration_uuidv4": "00000000-0000-4000-8000-000000000101",
    "repository_uuidv4": "00000000-0000-4000-8000-000000000102",
    "path_hex": "2f746d702f7265706f",
    "ref_templates": {
      "head": "refs/pull/{number}/head",
      "base": "refs/heads/{base_ref}"
    }
  }
}
```

Local `path_hex` is canonical lowercase hex of the lossless OS path bytes. For
remote work, choose `kind: "remote"` and replace `path_hex` with a `remote` object
containing the explicit HTTPS/SSH `locator`, `object_format` and nonempty
`refspecs`; their destination refs must cover the role refs. Remote settings use
the ordinary finite transfer/disk/timeout policy and credential references, with
SSH host verification. No inline credential is accepted. The request may also
bound `metadata_bytes` and `max_objects` with positive finite integers; the
`max_objects` ceiling is 100,000.

`ref_templates` requires full `refs/` names for `head` and `base`; supply `merge`
when an actual merge role is captured. Only `{number}` and `{base_ref}` template
fields are supported. The base-ref substitution comes from the actual Provider
detail. An unavailable captured role/ref reports partial rather than guessing
another ref.

HTTP and Git work share the same parent RequestIdentity and cumulative budget,
including retries and remote fetches. If the Provider captures head A while the
fresh Git ref points to B, acquisition reports `PR_CODE_RACE` and keeps the
original comparison plus the actual ref observation. Previously admitted A
remains usable; its presence cannot make this contradictory live comparison
complete. Resuming the original request preserves spent work and original facts,
and performs genuine bounded acquisition again. Context comparison evidence
contains the typed Source/Repository/ref coordinates, not local paths, temporary
cache locations or secrets. See the
[role-source implementation](../src/repo_catalog/application/github_git_roles.py)
and [actual CLI controls](../tests/e2e/test_separated_cli_github_git_roles.py).

## Integrity, recovery and evidence

Detected authoritative corruption stops ordinary reads/writes/workers/Exchange
and normal backup for the affected catalog. Preserve suspect files read-only.
Explicit salvage emits untrusted typed candidates; current local authority,
canonical values, complete dependencies and original provenance are revalidated
before fresh-destination admission. No sender flag, recovered local approval or
byte-presence claim supplies authority. Git-only backup is labeled; full
Context-containing backup is paired Repository+Context. Access is separately scoped.
Normal backup/restore never completes with known damaged retained bytes.

Managed cache GC acts only on exactly registered, unchanged roots/inventories
under the writer gate. Replacements, changed/unregistered trees and symlinks are
retained. A request cannot complete while positive disk reservations remain.
Operational loss means reuse/telemetry unavailable, rather than deletion authority
or loss of admitted facts. Search generation validity and authoritative fallback
remain independent of optional rebuild duration/count history.

The migration's [legacy-test map](implementation/separated-runtime-test-map.json)
records exact baseline blobs and named retained/replacement/excluded controls.
`scripts/check_runtime_retirement.py` checks references; actual collection,
execution and independent semantic review are still required. No test total or
source-symbol check is a substitute for those responsibilities.

[Schema 20 CLI](cli.md), [older data model](data-model.md), dated audits and frozen
execution receipts describe their recorded sources. Preserve them as history;
use current source and exact-tree verification for current behavior. Ordinary
prototype development does not require release-only full-suite, native Windows
or CPU/version matrix qualification. Websites follow asynchronously on `web`
under [ADR 0042](adr/0042-asynchronous-web-main-tracking.md), without a maintained
product SHA pin or a main/web freshness gate.
