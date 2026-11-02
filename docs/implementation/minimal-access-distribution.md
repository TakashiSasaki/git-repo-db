# Independent Access distribution (OP-07)

This bounded experiment implements ADR0037's OP-07 configuration/approval and
Access-only coherent backup minimum. It also preserves the existing inactive
restore and Scope fork APIs. It does not implement OP-08/09 installation minima,
change accepted architecture, or activate the opt-in format in normal Schema 21.
Executed results and artifact hashes are recorded in the implementation PR.

## Ownership and dependency graph

`repo-catalog-access==0.2.0` owns 17 existing Python modules and two SQL resources
under `packages/access/src/repo_catalog`. These are relocated byte-for-byte from
the composed product. There is no copied implementation or new domain abstraction.
The 17 modules are the four Access domain values, their four ports, four SQLite
adapters, workflow and maintenance applications, the local directory executor,
and workflow/maintenance CLIs. The two resources are `access_ddl/registry.sql` and
`access_ddl/connections.sql`. All existing import names remain unchanged.

Access has **no Python runtime dependency**, including contracts or runtime:
its validators and local SQLite/approval/backup primitives were already a closed
Access responsibility. Core and Context dependencies are unchanged. The root
product gains one exact-version Access dependency; its acquisition, Operational,
Search, Exchange and paired Recovery implementations stay in `src`.

```
repo-catalog-access -> Python standard library
repo-catalog -> access + core + context + contracts + httpx
core/context -> runtime + contracts
runtime -> contracts
```

All owners share the PEP 420 namespace and synchronized version. No new namespace
initializer or version-module copy is introduced. Installing a package opens no
catalog. Explicit `access_schema.initialize(path)` creates only the selected
Access DB. Existing public APIs and `python -m repo_catalog.cli.access_workflow`
and `python -m repo_catalog.cli.access_maintenance` retain their behavior.
There is no new comprehensive registration CLI or transport executor.

## Preserved boundaries

Repository UUIDs are typed logical references and need no Core row. Scope UUIDs
and dated registrations remain immutable, with equal-time ambiguity and no
permission-based fallback. Reviewed grants bind the exact route/configuration,
revalidate current settings and are revoked on material changes, including ABA.
Synthetic reviewer callbacks establish test behavior, not actual human approval.
Approval/preflight CLI still requires a local terminal.

The Access backup format and resource limits are unchanged. A coherent snapshot
includes committed WAL state and complete history. Restore uses a fresh private
destination without overwriting existing targets, removes executable grants and
disables routes. Local reapproval is required even on identity continuation. An
independent fork creates a new Scope and real registration without changing the
original history. This is configuration maintenance, not domain recovery.

Isolated Access absence/corruption refuses Access operations and retains its own
stop diagnostics. It does not certify or stop otherwise sound Core/Context.
Composed acquisition keeps domain stop fences, frozen intent and cumulative
Operational accounting. No existing SQLite/filesystem/approval safeguard is
relaxed by this ownership change.

## Verification inputs and limits

`tests/packaging/test_access_distribution.py` uses the hardened build helpers for
both direct and independently sdist-derived wheels. Each minimum consumer runs
outside the checkout with normal offline dependency resolution, only Access
installed, no editable installation or checkout import path. The probe imports
every owned Python module, checks origins/metadata/file ownership and optional
implementation absence, and executes registry, workflow, CLI and maintenance
positive and negative cases. The composed variants retain the existing A1/A2/A4/A5
installed smoke with local synthetic Git; unrelated Context Exchange stages are
excluded explicitly. Access integration tests retain the broader safety cases.

The existing source ownership audit, build cache binding, sdist member/resource
and content-equivalence checks remain authoritative. Raw logs/timing stay local.
One verified Python/SQLite environment and architecture suffice for this
prototype; no release qualification or power-loss proof is claimed. Packaging
success alone establishes no long-term maintenance saving.
