# Independent Reviewer B — CAS and Schema Review

## Scope and independence

This was an independent, read-only review of PR #20's CAS and schema changes. I did not edit or commit production files. The initial review was performed against the PR #20 implementation before its corrective changes; I reproduced the rejected-byte staging defect independently. I then re-reviewed the corrective implementation and ran fresh adversarial tests. The implementation lead made the corrections.

The final CAS verification used PR #20 commit `2b5123e0aee1d5cdf65fd14be0ded3d8e4c31bd9`, tree `bf6f5e1b037cf18b798086b9ef56abd68e211380`. This commit merges the corrected PR #19 decision document into the PR #20 branch; the commit itself changes documentation only. CAS and schema source hashes below identify the exact reviewed implementation. The composed production DDL hash was independently recomputed from the checkout. Later, unrelated concurrent edits appeared in `collector.py` and `test_phase1_retirement.py`; those paths are outside this CAS/schema report, and the CAS/schema file hashes remained unchanged.

| Reviewed file | SHA-256 |
| --- | --- |
| `src/repo_catalog/adapters/sqlite/cas_integrity.py` | `2468f3b36237faf135fff6973cabb529f1aee3fef4f496244a1b7eb15f7bcc38` |
| `src/repo_catalog/resources/cas_integrity.sql` | `58fa718c08e7558387602fa7e7266d33e74fbd7bda723b8c88ede4b8a1c97fd1` |
| `src/repo_catalog/adapters/sqlite/store.py` | `b95c4d537e589a93b90f3822b94496d7183e42b43f74ee9c9a637d6e46311229` |
| `src/repo_catalog/adapters/sqlite/schema.py` | `d3b28fbe6cd9cdb7d866a175434abc5e63bfee04729a98cf12dec01c1f5fadec` |
| `tests/integration/test_catalog3_cas_integrity.py` | `6e35deb2e782fafdffddaad07b63f4072a19cecea91827b2ca8f56ce0bb2a694` |

Composed production DDL fingerprint: `16110944d4b6a0942657644fe80383394210af1218a3e7111e331a1651fa211e`, schema version 18. Production composition order is `catalog3.sql`, `git_facts.sql`, `cas_integrity.sql`, `exchange.sql`, `identity_relations.sql`, `current_resources.sql`, `current_collections.sql`, and `json_contracts.sql`.

## Findings and corrections

### High — forged Git representation could stage rejected API bytes

**Affected path:** `stage_verified_payload()` and `payload_admission_staging`.

In the original PR #20 implementation, the helper trusted a `git-object-raw-v1` representation label and checked the SHA-256 of the received body, but did not prove that the supplied Git object format, type, size, and OID described those bytes. A JSON API body with a forged Git descriptor could therefore be retained in the rejected-byte staging table. This violated the raw-Git-only staging invariant and could preserve rejected API originals under a Git label.

Minimal reproducer used in the review:

```python
body = b'{"api":"rejected"}'
ref = PayloadRef("git-object-raw-v1", hashlib.sha256(body).digest())
context = {
    "object_format": "sha1",
    "oid": "0" * 40,
    "object_type": "blob",
    "byte_length": len(body),
}
stage_verified_payload(db, body, ref, context, reason="PAYLOAD_HASH_COLLISION")
```

The original helper accepted this false identity. The first Python-only correction added `validate_git_object()`, which correctly rejected forged descriptors through the function API. An additional independent probe found that direct SQL could still insert the same body and a syntactically valid all-zero OID: the original DDL checked only descriptor shape, not cryptographic identity.

**Correction:** the final helper verifies the body SHA-256 and full Git identity with `validate_git_object()` before staging. The DDL applies a `BEFORE INSERT` trigger using deterministic SQLite UDF `repo_catalog_git_object_identity_valid`; it verifies the Git object hash and physical SHA-256 for direct SQL writers. `Store` registers the function. The staging helper also registers it on a raw connection before its insert. A writer that lacks the function fails closed with `no such function`.

**Final adversarial verification:** true SHA-1 and SHA-256 descriptors can stage through both the helper and registered direct SQL. A false OID, a correct OID with false physical SHA-256, API/legacy representation labels, and an unregistered SQL writer are rejected; rejected inserts leave no additional row. The focused tests covering these checks passed as part of the final no-bootstrap CAS suites below.

## Physical integrity, repair, shared digests, and backup/restore

I reviewed the complete CAS callers and repair behavior, not only the helper bodies.

- Corruption diagnosis records a physical-only diagnostic and quarantine entry after rejected admission rollback; it does not retain incoming API bytes, a second encoding, or retry payload.
- Explicit repair requires at least one retained `git_object_payloads` mapping. It validates replacement bytes against **every** mapped Git object identity, including SHA-1 and SHA-256, and requires the same physical SHA-256 digest and active quarantine. Invalid replacements leave bytes, quarantine, and protection-trigger state unchanged.
- A physical digest legitimately shared by a Git object and an API representation remains repairable only when the true Git mappings validate. API-only bytes, a forged Git label without an object mapping, and a forged canonical OID do not authorize repair. Repair preserves the historical diagnostic while clearing only the active quarantine; re-corruption records a new interval diagnosis.
- Backup scans source and copy; unexplained corruption blocks publication. The backup/restore suite verifies active-quarantine manifest counts, rejects missing/mismatched/invalid counts and unexplained copy corruption, and checks atomic staged publication/retry behavior. Restored known quarantine is preserved.

These paths are covered by `tests/integration/test_catalog3_cas_integrity.py`, including `test_repair_accepts_real_git_content_even_when_api_proof_shares_its_bytes` for both object formats, forged-OID repair rejection, atomic repair/rollback, shared-incumbent diagnosis, backup corruption detection, and restore quarantine/count validation. The entire test file passed in the final focused run.

## Schema verification

Fresh schema 18 DDL audit results:

| Measure | Main/schema 17 baseline | Reviewed/schema 18 |
| --- | ---: | ---: |
| Product tables | 103 | 103 |
| Product columns | 667 | 665 |
| FK constraints | 227 | 226 |
| FK components | 360 | 358 |
| Views | 48 | 48 |
| Triggers | 497 | 498 |
| Explicit indexes | 107 | 106 |
| Implicit indexes | 144 | 144 |

The schema change removes `unresolved_payloads.payload_representation` and `payload_sha256`, their composite logical-payload foreign key, and one explicit FK-supporting index. The added Git staging identity trigger explains the trigger increase from 497 to 498. No product tables or views were removed.

The fresh composed DDL and fresh initialized catalog both passed. `foreign_key_check` returned no rows; `integrity_check` returned `ok`; all 48 views and trigger DML on 97 tables compiled. Foreign keys and recursive triggers were enabled. The remaining JSON contract audit classified 57 fields, left reference vocabulary unchanged, and confirmed generated guard SQL hash `b2216e19c1a602af778addfba6347ec58058a84ac755afdf789890be7d81c01d` matches the generator.

Commands independently executed:

```sh
uv run --no-sync python scripts/audit_api_original_retirement.py \
  --output /tmp/review-b-inventory.json \
  --summary /tmp/review-b-summary.json
uv run --no-sync python scripts/validate_remaining_contracts.py \
  --output /tmp/review-b-contracts.json
```

Both completed successfully. Contract runtime: Python 3.12.14, SQLite 3.53.1, Git 2.52.0, uv 0.12.19, Linux x86_64. The disposable contract report had `status: passed`, schema 18, the DDL hash above, and fresh-init `foreign_key_check: []`, `integrity_check: ["ok"]`; fresh init required no test-only parser bootstrap.

## Executed test evidence

All commands below used `uv run --no-sync pytest` without `REPO_CATALOG_TEST_BOOTSTRAP` and without live-provider tests. Counts overlap; do not add them.

| Selection | Result |
| --- | --- |
| `tests/integration/test_catalog3_cas_integrity.py tests/integration/test_catalog3_payload_cas.py` | **72 passed** in 16.28s on the final reviewed files |
| `tests/integration/test_catalog3_cas_integrity.py tests/integration/test_catalog3_adversarial_model.py tests/integration/test_catalog3_store.py` | **94 passed** in 21.94s; overlaps the first selection |
| `tests/integration/test_catalog3_schema.py tests/integration/test_catalog3_exchange_integrity_audit.py` | **23 passed** |

After the PR #19 documentation merge commit, I re-ran the CAS + payload-CAS selection against commit `2b5123e0aee1d5cdf65fd14be0ded3d8e4c31bd9`: **72 passed** in 16.28s. The corrected source/test hashes and DDL hash match the values recorded above.

Parser-certificate provenance was independently checked without changing the repository. The captured parser definition and bootstrap JUnit XML report **1,715 tests, 0 failures, 0 errors, 0 skips**. Re-running `scripts/verify_builtin_parser.py --snapshot artifacts/parser-definition.json --junit artifacts/bootstrap.xml --output /tmp/reviewer-b-parser-certificates.json` reported nine verified capabilities and 1,715 passed cases. The generated temporary certificate file was byte-identical to the checked-in resource (SHA-256 `6e34b19a378e8c5fea2eb6dd764c45abb7dde6c0b96b7d2f4906aa76a8d1a029`). This bootstrap run is certificate-generation evidence, not ordinary final suite acceptance.

## Boundaries not exercised

No authenticated provider traffic or user catalog was used. I did not exercise hardware power-loss durability or non-Linux atomic restore publication; the disposable remaining-contract report explicitly lists these as not executed. This review does not choose API-original retention/GC policy, historical proof replacement, or any deferred lifecycle/completeness architecture. Schema 18 is an unreleased fresh-init schema; no migration or old-catalog compatibility path is claimed.

## Conclusion

The initial high-severity rejected-byte staging defect was reproducible. The final PR #20 implementation closes both the Python helper and direct SQL paths with true Git object and physical SHA-256 validation. The independent no-bootstrap CAS/schema/repair/backup checks passed. No remaining CAS/schema defect was reproduced in the reviewed snapshot.
