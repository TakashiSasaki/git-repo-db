# Core Module: Exchange Staging & Admissions

Staging area for catalog synchronization, admission receipts, and conflicting candidate resolution.

- **Store:** Core (`catalog.sqlite3`)
- **Module Tables:** 4

```mermaid
erDiagram
    exchange_admissions {
        TEXT record_key PK
        TEXT table_name
        TEXT local_key_json
        BLOB content_sha256
    }

    exchange_blocked_coverage_claims {
        INTEGER coverage_claim_id PK "FK"
    }

    exchange_local_identities {
        TEXT table_name PK
        TEXT local_key_json PK
        TEXT record_key UK
    }

    exchange_staging {
        TEXT record_key PK
        BLOB content_sha256 PK
        TEXT table_name
        TEXT repository_uuidv4
        TEXT origin_catalog_uuidv4
        TEXT record_json
        TEXT reason
    }

    coverage_claims {
        TEXT coverage_claim_id PK "External reference from domain_enumeration_and_coverage"
    }

    coverage_claims |o--|o exchange_blocked_coverage_claims : "references (coverage_claim_id)"
```

## Cross-Module Foreign Keys

| Source Table | Source Column(s) | Target Table | Target Column(s) | Target Module | Action |
|---|---|---|---|---|---|
| `exchange_blocked_coverage_claims` | `coverage_claim_id` | [`coverage_claims`](core-coverage.md) | `coverage_claim_id` | Domain Enumeration & Coverage Evidence | ON UPDATE NO ACTION, ON DELETE NO ACTION |

[Back to Core Overview](core-overview.md) | [Back to Architecture Overview](overview.md)
