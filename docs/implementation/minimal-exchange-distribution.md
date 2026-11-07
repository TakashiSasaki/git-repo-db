# Minimum selective Exchange distribution (OP-10/11)

This increment builds on #250 at
`eba5a99baf006d7c7f291542504c2a866f282136`, tree
`9c026826c594794460642d084ccbf5c17e9f7d82`. The accepted
[operation contract](../architecture/module-independence-contract.md),
[selective Exchange contract](../architecture/selective-exchange-contract.md),
[ADR 0030](../adr/0030-context-repository-relations-and-selective-exchange.md)
and [ADR 0036](../adr/0036-ref-observations-and-shared-notes-mappings.md)
remain binding. Prototype operation proofs are distinct from release acceptance.

## Installation and ownership

`repo-catalog-exchange` depends on Core, runtime and contracts. Core-only export
therefore resolves four products. Core-only reception additionally requires an
explicit Operational installation and initialized durable ledger: five products.
Export never requires Operational. Neither minimum installs concrete Context,
Access, Search, Git acquisition, paired Query or the rich product.

One distribution contains both entry points; Operational is loaded only for
reception. Installation creates no databases and performs no external work.
The existing opt-in `application.exchange.ExchangeService` API and v8 format
remain canonical. The normal Schema21 `application.exchange_service` and
`adapters.sqlite.exchange` implementation remain composed and unchanged; this
increment does not replace the default CLI or invent a new Exchange CLI.

| Canonical installed file | Owner |
| --- | --- |
| `application/exchange.py` | X: bounded selection/export and durable reception orchestration, explicit optional integrations |
| `application/ref_exchange.py` | X: original Ref/Claim/Enumeration and Notes selection/admission; pure models/codecs/reconstruction stay C |
| `domain/exchange.py`, `exchange_rows.py`, `selective_exchange.py` | X: canonical package/digest, exact row grammar, complete selections and section validation |
| `adapters/sqlite/admission_transaction.py` | runtime: one transaction-owner guard; no Context admission semantics |
| `adapters/sqlite/context_transaction.py` | T: live Context admission binding over that guard |
| `adapters/sqlite/paired_admission.py` | paired Query integration: canonical PairCoordinator admission/backup methods; rich coordination reexports the same class |

The existing paired distribution already depends on C/T/runtime/contracts.
Core-only Exchange does not require it. Its relocation removes accidental rich
O/Search imports from the pair mechanism, without claiming independent paired
Recovery activation or changing its reconstruction obligations.

## Topology, supplied sections and durable work

Core-only selection does not exempt coexisting Context from identity and paired
authority checks. Every supplied Context section, including an unselected or
empty section, requires its actual validator. Missing Context/paired capability
refuses explicitly; opaque Context is never opened without its implementation.
Selection never bypasses full supplied-section validation. Concrete Context
admission remains authorization-scoped and optional, and Transfer remains
intentionally unsupported.

Reception reserves finite preflight/decode/admission work before performing it,
uses the original request and frozen semantics, and binds PackageKey to one
canonical-content SHA-256 in Operational. Exact resend and conflicting content
retain distinct outcomes. Core commit and checkpoint precede selected Context
commit and checkpoint; committed independent units survive honest partial results.
Operational loss never resets an old request's expenditure. Existing request
issuance witnesses remain distinct; no durable Exchange Witness is added.

Supplied work must use canonical durable NotesWorkBudget and WorkLedger with
matching physical identity, request and continuation. Supported custom frozen
scopes remain valid. A subclass overriding charges cannot replace accounting.
Identity cleanup is fenced before Operational writes. Normal completion checks
accounting and fences after owned Operational and paired connection/lease
cleanup. Stored authority corruption stops the catalog; caller, capability and
budget failures retain their own classifications. Reads never repair authority.

## Evidence and remaining boundary

`tests/packaging/test_exchange_distribution.py` builds direct and sdist-derived
artifacts and resolves ordinary offline external consumers. It records physical
absence, unique file ownership, actual loaded origins and hashes. Synthetic Core
fixtures contain actual metadata/ref/Notes bytes; producer acquisition is separate
from the consumer, which has no G installation. Focused source tests and
independent source/artifact counterexamples cover the affected composed paths.
Exact outcomes, failures and reused source bindings are recorded in the PR.

OP-12 remains a separate tranche: paired consistent backup, fresh restore/typed
merge and activation must preserve both authority validations and existing O/S
reconstruction. Provider acquisition remains composed. No release qualification,
CPU/SQLite matrix, general Transfer repair, live collection or real catalogs are
part of these operation proofs.
