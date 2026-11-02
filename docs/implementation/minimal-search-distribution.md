# Minimum Search distributions (OP-05/06)

This increment starts at reviewed paired Query PR #247,
`73f42b1b3bdc375d6786f776e47df0ded8efd618` (tree
`f09fdb7f45ddda29857a0ce1326172938ad96a32`). It implements the Search rows of
[ADR 0037's operation contract](../architecture/module-independence-contract.md)
under [ADR 0038](../adr/0038-scoped-recovery-and-optional-initialization.md).
Execution and independent review are revision-bound in the PR; this document
describes ownership and behavior, not release acceptance.

## Ownership and installation

`repo-catalog-search` depends only on runtime and contracts. Core+Search and
Context+Search each resolve four product distributions, with the other concrete
authority and Access/Operational/high-level acquisition/Exchange absent.
Paired Query is optional. The composed product adds Search to its dependencies
and preserves the existing rich API/import paths through composition/reexports.

| Canonical module | Owner and dependency |
| --- | --- |
| `domain/search_query.py`, `domain/ports/search_query.py` | Search DTOs, finite query/cursor validation and derivative port. No concrete authority imports. |
| `application/search_query.py` | Search orchestration, canonical authority-scan fallback and candidate verification. |
| `application/core_search.py`, `adapters/sqlite/search_core.py` | Search's Core integration, importing Core only when used; exact-Claim Notes and metadata extraction. |
| `application/context_search.py`, `adapters/sqlite/search_context.py` | Search's Context integration, importing Context only when used. Context provenance, qualified relations and unavailable Core references retain Context meaning. |
| `application/paired_search.py` | Search's optional paired integration, importing paired Query only when installed/used. |
| `adapters/sqlite/production_search.py`, `p1_ddl/search.sql` | Search derivative index and DDL, shared bounded document/SQL mechanisms. |
| `adapters/sqlite/search_projection.py` | Legacy SearchProjection facade; paired builders defer the canonical paired validator. Rich coordination reexports this same class. |
| `cli/search_query_features.py` | Search commands and finite explicit authority selection, reusing installed Query CLI features. |

One Search distribution includes dormant integrations for the other authority;
those integration modules are not loaded in a single-authority operation. The
other authority's concrete implementation/models/schema are absent. No model,
pager, Search engine, validator or generic plugin framework is duplicated.
Search types/API/CLI and authority-scan fallback are absent from basic Core and
Context. Shared runtime owns only the existing generic pager and Query mechanics.

## Correctness and refusal boundaries

Search scans the selected pinned authority and verifies candidate keys **and
bodies**, exact counts and complete matches. A matching freshness token alone
does not certify the derivative index. Missing, stale, incomplete, forged,
oversize or corrupt derivative state falls back to that authority scan. Ordinary
reads open an existing Search file read-only; they never initialize/repair it,
including when it disappears between existence check and open. Explicit rebuild
alone initializes/replaces derivative state. Derivative faults do not stop the
catalog; detected authoritative corruption still persists catalog-wide stop.

Core Search reads retained bytes only through the original exact-Claim Notes
checks. Multiple reports about one target retain distinct Claim identities; one
Claim's verified body does not certify another. Context Search retains provider
identity, clocks, provenance, alternatives and evidence-qualified dispositions.
It does not import Core to infer unavailable facts or certify provider reports.
Search is literal and case-sensitive, with bounded query/document/operation work.

Caller query/filter/cursor values are validated before stored-corruption
classification. Actual snapshot-token/cursor binding is checked before authority
body extraction. External SearchIndexPort callbacks/results cross the same opaque
exception boundary as external work callbacks, preserving exception identity
without manufacturing an authority-corruption stop. Genuine extraction remains
inside authority classifiers. In-flight and final completion fences run through
the canonical Query lifecycle, including after snapshot cleanup.

Explicit single-authority modes ignore opaque optional sibling files. Auto/paired
requests needing unavailable integration refuse rather than silently downgrade.
The unchanged rich API, paired behavior and normal Schema21 default remain.
Context Transfer remains unsupported. No new authority initialization, mutation,
Recovery, acquisition or Exchange independence is claimed.

## Development verification

[Installed tests](../../tests/packaging/test_search_distribution.py) resolve
direct and sdist-derived wheels offline outside checkout, use real synthetic
authority data and verify four owners, origins, artifact hashes and physically
absent optional code. The external [consumer](../../tests/support/search_probe.py)
exercises API/CLI parity, pagination/cursor binding, literal text, derivative
fallback without repair, exact Notes Claims, Context without Core, concurrent
snapshots, caller/port/budget distinctions, corruption and completion fences.
Fresh basic installations prove Search remains optional. Selected source and
composed regressions preserve existing paired/legacy consumers; they do not
establish independent acquisition/Exchange/Operational installations.

The next operation boundary is OP-08/09: Git acquisition with durable Operational
progress, optionally Access, without Context/Search. Frozen intent, actual-work
budgets, cumulative continuations/retries and Operational-loss refusal remain
required. OP-10/11 Exchange and full paired Recovery remain separate targets.
