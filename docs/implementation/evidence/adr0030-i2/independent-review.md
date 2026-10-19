# Independent I2 review

Reviewer: read-only subagent `/root/i2_contract_review`, separate from the
production author. Target HEAD
`3298dfbdc0428ba7ba13fd26331e97554119a74c`, tree
`28b53a862db969e3231bd1a6f08a0c7f20d22874`.
The reviewer verified local clean checkout, remote branch and GitHub commit API.

**Verdict: PASS; unresolved I2 blockers: 0.**

The reviewer independently ran 19 targeted cases (29 deselected), all passing on
SQLite 3.53.1. These exercised original event replay, exact Mapping support,
generic Transfer bypass, event-type unit binding, parent substitution and native
alias contradictions, P7 Stop, and caller-owned Context batch rollback.
Schema/fingerprint, registration, dependency and implementation-boundary audits
passed. No DDL/fingerprint delta or imported I3 implementation was found; the
I2/I3 merge-base is frozen I1.

Earlier WIP review findings were repaired before this target:

- Application still called removed normalizer/Core-UUID interfaces.
- A public qualified role could borrow another Provider's Mapping evaluation.
- A generic Provider scope could attempt Transfer promotion from Resource shape.
- Transfer type evidence needed exact event/clock/provenance/observation binding.
- An explicit parent Resource could override contradictory original coordinates.
- Contradictory fullDatabaseId/databaseId aliases also needed rejection when the
  supplied parent already used the same database namespace.

The reviewer executed the parent counterexamples and verified rejection after
repair, while a genuinely observed Node/database parent alias remains accepted.
No reviewer changed repository files or approved their own production changes.

The I4 handoff caveat is explicit: current affiliation uses
`provider_repository_roles()`. Older materialized Core-target relations alone
cannot represent the latest unresolved Provider owner. This is a deferred I4
consumer integration requirement, not an unresolved I2 blocker.

Broad local/hosted runtime, packaging and combined-tree probes are separate
author-run evidence, not claimed as independently executed by this review.
