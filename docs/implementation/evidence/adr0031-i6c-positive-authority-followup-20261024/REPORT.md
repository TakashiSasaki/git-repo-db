# Verification Report — ADR 0031 I6-C Positive Authority & Selection Follow-Up

**Task Target**: Remediate PR #159 GitHub Codex Review Findings (`discussion_r4366014889`, `discussion_r4366014892`, `discussion_r4366014895`)
**Base Commit**: `c00bdbb9246e12504506eaf372a49a1a631fc5f9` (PR #159 HEAD)
**Base Tree**: `cc165ee7fd54bdf9bff452f78dd67f3c6aaa68f6`
**Branch**: `fix/adr0031-i6c-positive-authority-followup-20261024`

---

## 1. Executive Summary

This Author follow-up directly resolves all three GitHub Codex review findings on PR #159:
1. **P1-A (`discussion_r4366014889`) — Paired Provider Authority Forwarding**:
   In `PairedAcquisitionCoordinator.admit_paired`, `_context_unit` constructed nested `ProviderAcquisition(ctx_cap, core=..., operational=...)` without passing `self.authorization` and `self.admission`. This caused `ProviderAcquisition._open_context` to fail closed with `PERMISSION_DENIED` even when valid service-issued authority had been supplied to `admit_paired`. Because `PairCoordinator` commits Core first, this left Core committed and Context rejected (`core_committed=True, context_committed=False`).
   *Resolution*: Forwarded `authorization=self.authorization, admission=self.admission` into `Context.for_transaction` and into nested `ProviderAcquisition` across `admit_paired` and `reconcile_core_dependencies`.

2. **P1-B (`discussion_r4366014892`) — Exchange Import Finite Grants and Fallback**:
   In `ExchangeService.import_package`, the fallback created `LocalAuthorizationPolicy` with `grants=None`. Because `LocalAuthorizationPolicy` denies Resource, Source, MappingClaim, and Disposition dependencies without finite grants, legitimate resource imports failed. Furthermore, if Core committed before Context evaluated resource admission, Core could commit while Context failed.
   *Resolution*: Added an explicit `grants` parameter to `ExchangeService.__init__` and `import_package`. Implemented `_validate_receiver_authority` to pre-validate receiver authority prior to starting the paired transaction. If a receiver supplies repository permission without finite resource grants and the package contains resources, it fails closed immediately with typed `PERMISSION_DENIED` and zero database writes. When receiver supplies finite grants, Resource imports succeed in both Core+Context and Context-only receivers.

3. **P2 (`discussion_r4366014895`) — Selection Tests Do Not Execute Admission**:
   Tests `test_receiver_empty_selection_admits_zero_resources` and `test_receiver_selective_subset_omits_unselected_sender_resources` previously only compared in-memory `ExchangeSelectionScope` objects without calling `import_package`, inspecting database tables, or observing policy leases.
   *Resolution*: Replaced both tests with full end-to-end integration tests using genuine SQLite sender and receiver stores, `export_package`, `import_package`, SQLite database row inspections, and policy call observations confirming exact subset admission and zero unselected admission.

4. **P1 (`discussion_4366462438`) — Prevalidate the Complete Dependency Set Before Committing Core**:
   For a Core+Context package containing a resource and its Provider registration, grants covering the resource and repository but omitting `provider_registrations` passed preflight. The same happened when the repository was permitted but absent from `grants.repositories`. `PairCoordinator` committed Core before Context unit rejected the missing grant, resulting in partial Core writes.
   *Resolution*: Implemented `ExchangeService._extract_context_dependencies` to extract all dependency dimensions (`resources`, `repositories`, `sources`, `source_repository_pairs`, `provider_registrations`, `dispositions`, `mapping_claims`, `object_oids`) and pre-validated the complete dependency set before entering `coordinator.admit` or `Context.transaction`. Missing provider or repository grants now fail closed immediately with typed `PERMISSION_DENIED` and exactly zero writes to Core and Context.

5. **P2 (`discussion_4366462441`) — Validate Authority Through the Authorization Policy Interface**:
   When a receiver supplied a `ContextAdmissionService` backed by a custom `AuthorizationPolicy` (such as `FixturePolicy`), preflight raised `AttributeError` on internal attributes `_principal` or `_permitted_repositories`.
   *Resolution*: Replaced internal attribute accesses with the public `AuthorizationPolicy.lease()` protocol method, allowing any valid `AuthorizationPolicy` implementation to execute cleanly.

6. **P1 (`discussion_4366521739`) — Remove the Autouse SQLite Safety-Guard Bypass**:
   An autouse fixture `_patch_sqlite_version` in `tests/integration/i6/test_i6c_authority_and_exchange.py` monkeypatched `p1_schema.sqlite3.sqlite_version_info` and `sqlite3.sqlite_version_info` to `(3, 51, 3)`, which bypassed the production WAL safety guard and violated ADR 0032.
   *Resolution*: Removed `_patch_sqlite_version` and the unused `p1_schema` import. All 40 integration tests now run and pass against the real runtime SQLite engine (SQLite 3.53.1) without version spoofing or monkeypatching.

---

## 2. Technical Remediation Details

### 2.1 P1-A: Paired Provider Authority Forwarding

#### Root Cause
In `src/repo_catalog/application/acquisition.py`, `PairedAcquisitionCoordinator.admit_paired` defined:
```python
def _context_unit(context_tx: AdmissionTransaction) -> None:
    with Context.for_transaction(context_tx, self.directory) as ctx_cap:
        if provider_batch is not None:
            prov_acq = ProviderAcquisition(
                ctx_cap,
                core=self.directory / "core.sqlite3",
                operational=self.operational,
            )
            provider_report_holder[0] = prov_acq.admit_batch(
                provider_batch, context=ctx_cap
            )
```
`prov_acq` was instantiated without `authorization` or `admission`. When `prov_acq.admit_batch` entered `self._open_context(context)`, it checked:
```python
auth, adm = self.authorization, self.admission
if auth is None or adm is None:
    raise AdmissionRefused("PERMISSION_DENIED")
```
Because both were `None`, it threw `PERMISSION_DENIED` even though valid service-issued authority had been passed to `admit_paired`.

#### Fix
1. In `PairedAcquisitionCoordinator.admit_paired._context_unit`:
   ```python
   with Context.for_transaction(
       context_tx,
       self.directory,
       authorization=self.authorization,
       admission=self.admission,
   ) as ctx_cap:
       if provider_batch is not None:
           prov_acq = ProviderAcquisition(
               ctx_cap,
               core=self.directory / "core.sqlite3",
               operational=self.operational,
               authorization=self.authorization,
               admission=self.admission,
           )
           provider_report_holder[0] = prov_acq.admit_batch(
               provider_batch, context=ctx_cap
           )
   ```
2. In `PairedAcquisitionCoordinator.reconcile_core_dependencies._context_reconcile`:
   Forwarded `authorization=self.authorization, admission=self.admission` into `Context.for_transaction`.

---

### 2.2 P1-B: Exchange Import Finite Grants and Pre-Transaction Validation

#### Root Cause
In `ExchangeService._import_package`:
1. When `auth` and `adm` were omitted, `create_local_admission_service` was invoked without `grants` (`grants=None`).
2. `LocalAuthorizationPolicy` denies all dependencies containing resources, sources, mapping claims, or dispositions when `grants is None`.
3. If Core objects were imported in `_core_unit`, `core.commit()` was executed before `_context_unit` attempted resource admission. If resource admission failed with `PERMISSION_DENIED`, Core remained committed, causing partial database state.

#### Fix
1. Added `grants: Any = None` to `ExchangeService.__init__` and `ExchangeService.import_package`.
2. Implemented `_validate_receiver_authority(auth, adm, context_data)`:
   - Validates that `auth` is an authentic `ContextAdmissionService` and `adm` was issued by `auth`.
   - Validates caller principal against policy principal.
   - If `context_data` contains resources, sources, mapping claims, or dispositions:
     - Verifies `policy.grants is not None`.
     - Verifies all context resources are a subset of `policy.grants.resources`.
     - Verifies all context sources are a subset of `policy.grants.sources`.
   - Verifies all context repositories are within `policy._permitted_repositories`.
   - Verifies no dependencies intersect `policy.denied`.
   - Fails closed with typed `AdmissionRefused("PERMISSION_DENIED")` BEFORE `coordinator.admit` or `Context.transaction` is entered, ensuring zero database writes to either Core or Context on unauthorized attempts.
3. Forwarded `authorization=auth, admission=adm` to `Context.for_transaction` in `_context_unit`.

---

### 2.3 P2: Behavioral Execution of Selection Regressions

#### Root Cause
In `tests/integration/i6/test_i6c_authority_and_exchange.py`, `test_receiver_empty_selection_admits_zero_resources` and `test_receiver_selective_subset_omits_unselected_sender_resources` only constructed `ExchangePackage` and `ExchangeSelectionScope` in memory and asserted on their attributes without calling `import_package`.

#### Fix
Replaced both tests with full end-to-end integration tests:
1. `test_receiver_empty_selection_admits_zero_resources`:
   - Populates sender with two distinct resources (`rk1`, `rk2`) and exports an `ExchangePackage`.
   - Initializes a fresh receiver SQLite catalog (`init_catalog_stores`).
   - Configures receiver selection with `resource_keys=()`.
   - Executes `ExchangeService(receiver_dir).import_package(...)`.
   - Asserts `report.admitted_context_resources == 0`.
   - Queries receiver SQLite database (`context.sqlite3`): `SELECT count(*) FROM resources` is 0.
   - Observes `policy.calls`: zero lease requests for resources.
2. `test_receiver_selective_subset_omits_unselected_sender_resources`:
   - Populates sender with two distinct resources (`rk1`, `rk2`) and exports an `ExchangePackage`.
   - Initializes a fresh receiver SQLite catalog.
   - Configures receiver selection with `resource_keys=(rk1,)` and finite grants for `rk1` only.
   - Executes `import_package`.
   - Asserts `report.admitted_context_resources == 1`.
   - Queries receiver SQLite database: only `rk1` is present; `rk2` is completely absent.
   - Observes `policy.calls`: lease requests observed for `rk1`, never for `rk2`.

---

### 2.4 P1: Remove Autouse SQLite Safety-Guard Bypass

#### Root Cause
In `tests/integration/i6/test_i6c_authority_and_exchange.py`, an autouse fixture `_patch_sqlite_version` monkeypatched `p1_schema.sqlite3.sqlite_version_info` and `sqlite3.sqlite_version_info` to `(3, 51, 3)` to pass `p1_schema._open` checks. Per ADR 0032 and `AGENTS.md`, tests must run against the execution environment's actual loaded SQLite library without monkeypatching or version spoofing.

#### Fix
Removed `_patch_sqlite_version` and the unused `p1_schema` import from `tests/integration/i6/test_i6c_authority_and_exchange.py`. All 40 integration tests execute and pass naturally on the environment's runtime engine (SQLite 3.53.1) with full WAL safety and schema verification intact.

---

## 3. Verification Evidence

### 3.1 Test Suite Results
- `tests/integration/i6/test_i6c_authority_and_exchange.py`: **40 passed** in 17.64s (see `raw/test_i6c_authority_and_exchange.log`).
- `tests/unit/test_sqlite_validation_policy.py`: **31 passed** in 0.195s (see `raw/unit_sqlite_validation_policy.log`).
- `tests/unit/test_ci_python_runtime.py`: **4 passed** in 0.010s (see `raw/unit_ci_python_runtime.log`).
- `scripts/check_sqlite_validation_policy.py`: **PASS** (see `raw/sqlite_validation_policy.log`).
- `tests/integration/i3/test_selective_exchange.py::test_cross_seed_permission_identity_replay`: **PASS**.

### 3.2 Static Analysis & Formatting
- `ruff check src tests scripts`: **All checks passed!** (see `raw/ruff_check.log`).
- `ruff format --check src tests scripts`: **452 files already formatted** (see `raw/ruff_format.log`).

### 3.3 Packaging Verification
- Built direct wheel and source distribution via `uv build`.
- Extracted source distribution to an isolated temporary directory and rebuilt sdist-derived wheel via `uv build --wheel`.
- Computed complete raw-byte SHA-256 hashes without stripping:
  - Direct wheel: `repo_catalog-0.2.0-py3-none-any.whl`, 793,473 bytes, SHA-256: `1368b7943966ef63dc6ccb50fca41c2525e65e5c5f85842abc5dd8a00ae29d6d`
  - Sdist-derived wheel: `repo_catalog-0.2.0-py3-none-any.whl`, 793,473 bytes, SHA-256: `1368b7943966ef63dc6ccb50fca41c2525e65e5c5f85842abc5dd8a00ae29d6d`
  - Equality: **Byte-for-byte identical (True)**.

---

## 4. Invariant Boundaries

- **Transfer Stage Fences**: Ordinary Transfer triggers and fences remain active; no Transfer bypass enabled.
- **Seven Resource Columns**: Enforced unconditionally in storage and wire envelopes.
- **Distinct Scanner Track**: The I155-M01 Admission scanner work-budget correction is maintained in its dedicated branch (`fix/adr0031-i155-m01-iterator-followup-20261024`, PR #160) and is not merged or cherry-picked here.
