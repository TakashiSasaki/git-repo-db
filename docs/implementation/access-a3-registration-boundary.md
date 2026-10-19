# A3: domain-only Context registrations and Exchange separation

Status: opt-in implementation on A2a PR #98, exact parent
`16c36f989f39aa9f9d2cf175dffb86e52da5a72d`, tree
`2121af0d127a40e7d63c43126851da025ac6404b`. The owner requested continuing the
Access stack on 2026-10-18; main work began at 00:52:22 JST. The active Access
choices and A1/A2 interfaces are preserved. This stage does not retire ADR 0003,
accept all of ADR 0029, merge branches, migrate real data, switch the public
Schema 21 runtime, or implement remote Git/executor access.

## 1. Boundary and physical change

Four Context JSON columns now have one shared, bounded, role-specific contract:

| Table/column | Role | Retained domain meaning |
| --- | --- | --- |
| providers.configuration_json | provider | Descriptive service metadata, not an API route |
| repository_context.configuration_json | repository | Repository descriptions/attributes, not local paths or preference |
| sources.configuration_json | source | Source identity/discovery descriptions, not credentials or polling policy |
| source_repositories.attributes_json | membership | Known-positive association attributes and original provenance |

The column names are retained to limit unrelated churn; they no longer mean a
free-form executable configuration bucket. `domain/context_registration.py`
defines the exact 33 allowed fields and their types. Empty objects remain valid;
explicit null stays distinct from absence for permitted values. Original structured
provenance is preserved, not replaced with a receiver clock or synthetic identity.

Python registration values/writers and four SQL `p1_registration_json` CHECKs use
the same contract. Context opening and persisted registration reads validate the
actual snapshot. Invalid incoming settings are a non-mutating rejection, not
catalog corruption. Persisted values violating the new schema are diagnosed and
stop the affected catalog under existing rules; a writer must not silently repair
that data by replacing it with sanitized metadata.

Only the opt-in Context physical CHECK definitions change. Tables, columns, direct
keys and foreign-key structure do not change. Context DDL SHA-256 is
`75f142fa9127ff6790f9348433f79b2f84e8fa2b20ef32b668d8ff21d924cf3b`.
The packaged fingerprint and physical P1 disposition evidence are regenerated.
Core/Operational/Search DDL and Access's ten-table format2 are unchanged; Access
DDL SHA-256 remains
`89bcafeda815150fa4770f5758edf7d2d36d505b76717aa19054f9ad689765da`.
Exact old Context schema mismatch is a format error, not an automatic migration
or proof of corrupt old-domain data. Existing valid user catalogs are untouched.

## 2. Explicit key-level routing, not blanket movement

The [A3 routing ledger](access-a3-routing.json) lists EVERY one of the 25 legacy P1
column routes into these generic registration JSON columns. `p1-disposition.json`
points explicitly to this later override. Prior routes remain historical lineage,
not current permission to stuff old settings into domain registrations. The new
`audit_context_registration.py` checks the complete route set, all 33 field types,
the four physical CHECKs and the exact Exchange registration section vocabulary.

- Genuine descriptions, names and classified times remain Context metadata.
- Provider-observed URLs belong to attributed resource fields when modeled as
  observations. Historical Git endpoints/paths remain Core RepositoryClaims with
  the original provenance; Access exclusion does not redact those observations.
- Active endpoints, execution environments, credentials references, SSH options
  and access preferences require explicit Access configuration. No Scope UUID,
  registration time, executor binding or approval is inferred from old strings.
- Polling/retry/timeout fields need explicit execution-policy classification. This
  stage does not claim a durable scheduler exists or consign nonreconstructible
  user preferences to disposable Operational storage. Request-specific frozen work
  settings and accounting keep their established Operational ownership.
- Secret values belong in external facilities. Unknown keys require an explicit
  disposition; no silent dropping, executing, or moving an entire JSON object.
- Old Repository endpoint dates are not Scope Locator registration dates. Do not
  manufacture new Scope history from the old endpoint table.

A pure `classify_registration` returns known key categories and counts, not secret
values or a ready-to-execute configuration. It neither reads catalogs nor writes
Access and is not a completed real-data extractor. Diagnostics omit caller values
and unknown field names. Finite validation does not detect secrets intentionally
disguised as prose, IDs or original provenance; ordinary domain text remains data,
never execution authority. This is a persistence/interpretation boundary, not DLP.

## 3. Input, query, and Exchange enforcement

`ProviderRegistration`, `RepositoryRegistration`, `SourceRegistration` and the
source-association metadata validate at construction. Provider batch admission
rechecks the whole registration batch before any write, including mutated frozen
Python values and a caller-owned Context transaction. Four Context writer methods
and raw trusted SQL CHECKs enforce the same rule. P6 registration projections and
P5 exports use checked persisted values rather than sanitizing on output.

The wire contract is now `git-repo-db/p5-exchange-v3`. Its registration JSON and
four exact row envelopes are validated even when Context is not selected or absent
at the receiver. A hostile but correctly rechecksummed envelope cannot smuggle an
extra executable sibling field through an otherwise valid row, or cause partial
Core admission before the registration error is found. V2 is rejected rather than
silently reinterpreted. SHA-256 remains a checksum, NOT sender authentication.

This does not filter away incoming settings: an inadmissible package is rejected.
A supported domain-only package preserves the original registration facts, Source
known-positive membership, domain fields and Core provenance. Domain Exchange does
not instantiate, open or approve an Access store. Configuration transfer remains a
separate explicit operation; no automatic configuration importer is added here.

## 4. Discovered pre-existing RepositoryClaim codec defect

At the exact parent, `_import_core_units` treated a RepositoryClaim JSON value as
ScalarClaim's tagged `["known", value]` / `["unknown"]` encoding. RepositoryClaim
actually stores a direct JSON string/integer/null. Indexing a URI string with `[1]`
therefore silently reduced the imported historical URI to its SECOND CHARACTER;
other scalar values could fail or be misinterpreted.

A3's positive preservation test reproduced this defect. The fix decodes direct
RepositoryClaim values without ScalarClaim tag extraction and prevalidates their
canonical typed values before any Core write. Nine dedicated field/value round-trip
cases cover one-character/empty names, Unicode paths, URLs, object format, nullable
and positive observation times, identity assertions and cancellations. Repeated
import and reverse export retain the exact original direct keys. Actual ScalarClaim
encoding is unchanged. No Core DDL or historical stored claim is rewritten.

## 5. Tests and verification scope

The parent Access cohort (282 tests) passed on actual SQLite 3.51.3 before editing.
An initial risk-cohort run passed 1,142 tests, including P1/P3/P5/P6 and P7 recovery,
with four existing Python-3.13 fork-in-multithreaded-process warnings in P7 tests.
The current final cohort adds the route-audit test and six invalid-kind cases;
exact final counts and source binding are recorded in the PR/execution receipt.
Repeated runs are not additional distinct tests. No runtime-minimum override is used.

Six deliberately removed defenses are detected by test failures with no setup
errors in the corrected experiment: shared domain validation, physical CHECKs,
Exchange registration preflight, persisted registration scanning, direct
RepositoryClaim decoding, and exact registration envelopes. The physical-CHECK
mutation regenerates its disposable compiled fingerprint so it tests the data
constraint, rather than being rejected earlier as a mismatched schema. Final
product files and the real packaged manifest are restored byte-for-byte afterward.
These are author-run mutation tests, not an independent review or exhaustive score.

The dedicated CI now runs Access plus the relevant Context/Exchange/query/recovery
cohort, both installed wheel variants, four existing audits and the new route audit.
Installed smoke includes raw SQL rejection of executable registration settings and
an exact historical URL Exchange round-trip without an Access store or HTTP library.
Hosted results must be read at the actual final HEAD/effective tree; local success
alone does not claim hosted or installed-wheel execution.

Retained initial failures: an unsupported GitCore context-manager test fixture;
an older P3 fault stub raising during the new earlier constructor scan rather than
its intended text read; local subprocess imports in an uninstalled source archive;
and the real historical-URL codec regression. Fixtures/import setup were corrected
without weakening product defenses. Long foreground tool calls timed out before
finishing broad suites; an explicit within-task worker later completed the cohort.
The first mutation attempt hit packaged-schema drift and had a wrong replacement
coordinate; those setup failures remain separate from the corrected detections.

Local Python is 3.13.5 with an actual 3.51.3 library from the hash-verified parent
CI artifact. A local venv links the source and existing development dependencies so
subprocess tests import the reviewed package; that is NOT an installed-wheel test.
The supported release source ID was checked. The source archive's full tree equals
the remote parent, but it is not a full-history clone. No independent subagent was
available/launched. MkDocs and complete release-wide testing remain unexecuted.

## 6. Costs and remaining stages

Context construction now scans all four registration relations in its pinned
snapshot: O(registration count), with bounded individual JSON values. This avoids
silent output/repair of invalid authority, but is not a large-catalog throughput
claim. Any optimization must preserve equivalent validation and stop semantics.

A4 still owns actual Git acquisition, multi-repository seed reconciliation and
original retry-plan binding. A5 still owns Access backup, disabled-on-restore
consent and Scope continuity/fork; A6 owns independent exact-tree integration and
ADR replacement closure. A3 introduces no new transport, live endpoint discovery,
secret lookup, domain data deletion, or implicit executable Access transfer.
