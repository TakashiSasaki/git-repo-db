# Experimental contract and source map

This experiment is authorized by the owner's task, “git-repo-db: Independently
test U3=C′ using real SQLite.” It is an isolated feasibility investigation, not
product implementation, architecture acceptance, or a migration. All fixtures
are synthetic. The task's selected contract is sufficient independently of the
design Draft PR.

## Fixed inputs

The reproducible product reference is commit
`efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`, tree
`117d580b31098ecb8287281bd843894fdfad71fc`. Freshly fetched main matched it.
[Source bindings](results/source-bindings.json) records actual inspection time,
refs and hashes of the product inputs. This branch starts directly at that
baseline; it does not merge or cherry-pick either documentation branch.

- [Audit Draft #113](https://github.com/TakashiSasaki/git-repo-db/pull/113):
  `24f593861327328fa00dab0b83f956cec330a0ac`, tree
  `7318fdb1cb5ef4959d685bf2a3a1d9d91385c89e`.
- [Design Draft #114](https://github.com/TakashiSasaki/git-repo-db/pull/114):
  `5244b98a9a302f082a07a526480faf438fc91838`, tree
  `4e44d04c9425942cdd1392a2a748f80f2ad485ed`.

The audit's findings/options and main report were inspected at that ref. Its
runtime tests establish only the old product behavior; none count as candidate
tests. The design PR explicitly says C′ is unproven. Its proposed ADR number
and acceptance status are not changed here. No other open experiment PR existed
at the initial inspection.

## Owner-selected constraints

| Decision | Required meaning in this experiment |
| --- | --- |
| A3 | Extensible kinds with reserved known typed contracts; malformed known input cannot escape via a generic fallback |
| B3 | Identification namespaces and semantic Parent reports are separate; Resources need not form a tree and Documents need not be leaves |
| U3=C′ | Parent authority in existing `resource_relations`; no new Parent, Mapping, Witness, Event-header or verification-history authority |
| U4=B | Complete child admitted without Parent; withhold missing-reference report and dependent unit; no fabricated Parent or durable pending body; actual report must be supplied again |
| U5=A | Unknown kinds retain the known common format and explicit selection/dependency rules, without inferred specific semantics |
| U1=B | Kind meaning is Provider-instance scoped except reserved common typed contracts; names are stable key components |
| U2=A | ResourceKey is service UUIDv4, kind, canonical JSON TEXT identity; recursive strings/arrays only |
| U2-E2 | Genuine complete empty coordinates allowed; `""`, `[]`, `[""]`, `[[]]` are different, never missing-ID replacements |

Preserve exact strings and array order/nesting, including huge decimal strings,
case, whitespace and Unicode distinctions. No content hash, receipt timestamp,
row number or new local UUID replaces a semantic identity. Preserve applicable
PR Document coordinates, six Resource-to-Core-Repository roles, permanent Core
repository UUIDs, Core INSERT-only, the five-store boundary, Context mapping
authority, positive Source membership, five-column Coverage, original clocks,
and absence of Witness/Publication mechanisms.

## Product source findings

All paths below refer to the frozen baseline, not modified product inputs.

| Source | Relevant inspected contract |
| --- | --- |
| `AGENTS.md`, ADR index/policy, ADR 0017 | Direct semantic PK/FK; no storage-only surrogate; immutable evidence; scoped owner authorization and no architecture acceptance by a passing test |
| ADR 0028 | Observation/Provider time is positive integer or NULL; preserve original values; SHA-256 consistency is not authentication |
| ADR 0029 | Durable Context and separate Access; full Context backup pairs Core+Context; Core remains INSERT-only |
| ADR 0030 Q-S5/Q-S10/Q-E5/Q-E6 | Exact Event/report grouping; typed Timeline Event FK plus actual-event admission; bounded selected coherent units |
| `src/repo_catalog/adapters/sqlite/p1_ddl/context.sql` | Mandatory Resource Parent FK and known document CHECKs; five-column typed Transfer FK; full seven-column `resource_relations` key; immutable relation triggers |
| `src/repo_catalog/adapters/sqlite/p1_schema.py` | Composes Context DDL with store identity and shared Coverage; minimum 3.51.3; registers deterministic functions; sets FKs and recursive triggers before transactions; exact schema validation |
| `src/repo_catalog/domain/p1_context.py` | Existing document identity encoding, Timeline Event contract, EventReportKey `(EventResourceKey, clock_json, provenance_json)`, genuine event type and endpoint agreement |
| `src/repo_catalog/adapters/sqlite/p1_context.py` | Whole Transfer report savepoint; exact replay checks scope/member/endpoint sets and original observation time; missing Issue blocks admission |
| `src/repo_catalog/adapters/sqlite/production_context.py` | Relation member referents, explicit inherited fields, immutable report time and known Collection owner semantics |
| `src/repo_catalog/domain/selective_exchange.py` | `transfer_reports` validates scope/endpoint coherence; `bound_sections` preserves Transfer units; no receipt replaces actual committed data |
| `src/repo_catalog/adapters/sqlite/recovery_validation.py` | Stored semantic admission guards are distinct from SQLite integrity/FK checks; Transfer scope and Issue Parent revalidated |
| `src/repo_catalog/adapters/sqlite/recovery.py` | Context backup checks exact schema, encoding, stored guards, integrity, FKs and bytes; paired identity and manifest validated before restore |
| `docs/architecture/selective-exchange-contract.md` | Independent selection, whole groups, unadmitted dependencies without staging, actual keys/clocks, no permission expansion from an FK |

The existing `transfer_event_report` row is already a coherent report in
`resource_relations`, not permission to introduce another header table. The
candidate must preserve its atomic meaning while relocating Parent authority.
The baseline's mandatory child-to-Parent FK cannot remain as the operative
authority in a purported U4=B demonstration.

## Required evidence families

T01 identity and genuine empty coordinates; T02 child before Parent; T03 later
dependencies and exact replay; T04 typed-reference rejection; T05 exact support
and report coherence; T06 attributable alternatives; T07 NULL/JSON/cardinality
bypasses; T08 mutation/conflict paths; T09 transactions/reopens/configuration;
T10 general groups and Collection completeness; T11 selected reconstruction and
snapshot boundaries; T12 SQL versus admission/evaluation enforcement.

The reviewer must inspect frozen executable inputs, rerun positive/adversarial
cases independently, and distinguish FK, CHECK, trigger, typed admission and
read-time qualification. Author and reviewer executions overlap and must not
be added into a fictitious distinct-case total.

## Limits that apply regardless of test outcome

An FK establishes stored referents and structural compatibility. It cannot
authenticate an issuer or prove an external event happened. A synthetic adapter
can declare a genuine empty identity contract; SQLite cannot discover it.
Experimental reconstruction/snapshot tests are not product Exchange/backup
acceptance: product fingerprint and semantic decoders deliberately still expect
the baseline. Misconfiguration and arbitrary schema/file replacement are outside
the supported connection boundary. This task does not authorize changing that
boundary, accepted ADRs, runtime defaults, real catalogs, or either other PR.
