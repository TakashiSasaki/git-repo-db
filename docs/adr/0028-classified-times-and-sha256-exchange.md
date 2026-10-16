---
status: accepted
date: 2026-10-16
replaces: []
refines:
  - 0027-unauthenticated-external-capture-origin-reports.md
---

# ADR 0028: Classified epoch times and SHA-256-only Exchange integrity

## Decision

The owner explicitly accepted **time Option A** and **SHA-256 only** in the
2026-10-16 task “git-repo-db: freeze decisions, correct P5/P6, independently
validate integration”, sections 4–6. This records that acceptance, not approval or
merging of this design PR, implementation, or executed verification. There are
zero known owner-decision blockers in this scope. This is a full ADR because it
changes shared admission/DDL contracts and the Exchange trust boundary.

Absolute times remain Unix epoch **microseconds**, with `_us` names:

| Semantic origin | Allowed values |
| --- | --- |
| Observation, acquisition, Provider-owned absolute time | NULL or an integer in 1..9223372036854775807 |
| Contractually required observation, including Coverage and terminal coordinates | An integer in 1..9223372036854775807, never NULL |
| Native Git author/committer/tagger absolute time | Signed int64, including zero and negative values |

Classify by field meaning and origin, never by storage in Core or an arbitrary
caller flag. Native Git time keeps its meaning through Exchange; preserve the
exact original Git bytes and OID. Keep a generic signed-int64 conversion separate
from classified input validators. Python/API and JSON boundaries reject booleans,
floats and numeric strings instead of coercing them. SQL constrains stored values;
SQLite affinity/CHECK does not prove the original caller input type.

Unknown observations that the domain permits (including FieldCandidate) become
nullable consistently in types, opt-in DDL, Exchange and readers. Preserve missing
versus explicit NULL. Do not fabricate an unknown time using 0, 1, now or receipt
time, silently turn known invalid input into NULL, infer ordering from NULL or
resolve incomparable candidates by arrival. A genuine new observation may measure
its time when made; retry/forwarding preserves original time. Missing required
coordinates withhold that proof/freshness guarantee while retaining independently
admissible data. Coverage's five columns and actual composite PK/FK stay required.
These restrictions do not apply mechanically to durations, elapsed/wait times,
UTC offsets or counts.

Exchange uses a versioned canonical-data SHA-256 envelope. Export declares the
digest and import recomputes and **compares** it before admission. The wire contract
must specify normalization, UTF-8, binary encoding, hashed scope, digest exclusion,
format version and finite input/decode/body/proof/work limits. Old unreleased wire
compatibility is unnecessary. Native Git OIDs still use their own `object_format`
(SHA-1 or SHA-256), independently of the package digest.

SHA-256 provides content consistency, **not sender authentication**. An attacker
able to replace data and digest can impersonate a claimed origin undetected by
this checksum. Receiver domain, byte and Notes-role validation still apply after
a digest match. P6's keyless SHA-256 cursor is also a checksum, not a signature or
MAC; validate its content independently, including a maliciously recomputed checksum.

## Constraints / Do NOT

- Do not add HMAC, electronic signatures, PKI or key management for this correction;
  optional HMAC is explicitly not adopted. Correct claims that it was implemented.
- Do not trust sender intrinsic/copy-health flags as receiver checks, fabricate
  missing Git referents, store ordinary file blobs or durably stage unproven Notes.
- Do not make all time columns nullable or force the generic signed validator
  positive: both would destroy valid domain meanings.
- Do not replace direct semantic composite keys with storage surrogates, create
  independent Publication, rewrite Capture's two actual UUIDv4 values or change
  permanent repository identity. Git Core stays INSERT-only; Context stays an
  independent authority; Operational/Search stay reconstructible derivatives.
- Do not resume ordinary operations after authoritative corruption using another
  copy inside the same suspect catalog. ADR 0026's persistent stop remains binding.
- Do not activate P8, migrate real catalogs, modify actual backups, merge into main,
  release/tag, enable auto-merge or intentionally publish Pages under this task.

## Context & Reason

The former active agent/spec summaries allowed zero and negative values for every
absolute time and froze all P1–P4 DDL. The owner explicitly changes that convention
for observation/acquisition/Provider times while retaining signed Git-native times.
No ADR containing other binding clauses is retired: no existing accepted ADR
asserted the reversed universal range. The affected convention lives in AGENTS.md
and implementation contracts. This ADR refines ADR 0027's unauthenticated reports
without reversing any of its origin, provenance or identity guarantees. HMAC and
signature terminology overstated checksum integrity; recording a received hash
without comparing a declared hash also failed to establish transport consistency.

## Consequences

Implement a common reviewed shared time/DDL/fingerprint correction, then use the
**same shared commit** in sibling P5 and P6 branches. The intended review DAG is
#79 → this design → shared correction → {P5 correction, P6 correction}; neither
sibling acquires the other's implementation. A tests-only integration PR may
explicitly depend on both siblings. Public default Schema 21 remains unchanged;
only opt-in contracts change, with honest audit disposition and regressions.
Historical receipts keep their original revision/result and are not current PASS.

Required evidence includes NULL, -1, 0, 1, both int64 endpoints, out-of-range,
bool, float, numeric-string and unit-error inputs; signed native-Git preservation
paired with observation rejection; forged-but-rechecksummed packages/cursors;
replay/reorder/late arrival; independently rerun corrected commits; and clean
combined-tree integration plus wheel and sdist-derived-wheel checks. These are
acceptance requirements, not claims that those executions have occurred.

## References

- [ADR index](README.md), [governance](policy.md), [ADR 0001](0001-validation-lifecycle-architecture.md)
- [Four-store and INSERT-only boundary](0003-append-only-git-core-and-context-store.md)
- [Unauthenticated origin reports](0027-unauthenticated-external-capture-origin-reports.md)
- [P5/P6 technical contract](../implementation/p5-p6-technical-contract.md)
- Owner's current task, sections 3–10 and 12 (approval source, reproduced above
  so this decision is usable without access to the conversation).
