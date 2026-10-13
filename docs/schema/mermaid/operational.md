# Operational Store Schema (operational.sqlite3)

Execution management, worker progress, and packfile cache leases under **Operational Schema Version 1**.

- **Physical Database:** `operational.sqlite3`
- **DDL SHA-256:** `dafdc014ebf3e54e1695ffb0bb3fd953f1a1c893d5b0b13d812740ee2f288def`
- **Product Tables:** 10
- **Physical Foreign Keys:** 9
- **Triggers:** 20
- **Physical Invariant:** Completely physically separate from `catalog.sqlite3`. Loss of Operational DB never compromises Core facts (ADR 0002 §2 PF-P06, PF-P12).

## Physical ER Diagram

```mermaid
erDiagram
    acquisition_progress {
        TEXT git_acquisition_id PK
        TEXT job_id FK
        INTEGER attempt FK
        TEXT state
        INTEGER generation
        INTEGER ended_at_us "nullable"
        TEXT active_cache_entry_id FK "nullable"
    }

    active_cache_entries {
        TEXT active_cache_entry_id PK
        TEXT cache_locator_id FK
        INTEGER generation
        TEXT state
        INTEGER last_used_us
        INTEGER bytes
    }

    cache_leases {
        TEXT active_cache_entry_id PK "FK"
        TEXT job_id PK "FK"
        INTEGER attempt PK "FK"
        INTEGER acquired_at_us
    }

    cache_locators {
        TEXT cache_locator_id PK
        TEXT repository_uuidv4
        TEXT path
        TEXT access
        TEXT state
    }

    collection_progress {
        TEXT fetch_collection_id PK
        TEXT job_id FK
        INTEGER attempt FK
        TEXT state
        TEXT cursor "nullable"
        TEXT reason "nullable"
    }

    job_attempts {
        TEXT job_id PK "FK"
        INTEGER attempt PK
        TEXT state
        INTEGER created_at_us "nullable"
        INTEGER updated_at_us "nullable"
        INTEGER not_before_us "nullable"
        TEXT checkpoint
        TEXT reason "nullable"
    }

    jobs {
        TEXT job_id PK "FK"
        TEXT kind
        TEXT request
        INTEGER current_attempt FK "nullable"
        INTEGER created_at_us "nullable"
    }

    operational_identity {
        INTEGER singleton PK "nullable"
        TEXT format_id
        INTEGER schema_version
        TEXT operational_instance_id
        TEXT catalog_db_instance_id
        INTEGER created_at_us
        BLOB ddl_sha256
    }

    search_rebuild_metrics {
        INTEGER rebuild_id PK "nullable"
        INTEGER started_at_us
        INTEGER ended_at_us
        INTEGER duration_ms
        INTEGER documents_indexed
        INTEGER bytes_indexed
        TEXT status
    }

    space_reservations {
        TEXT job_id PK "FK"
        INTEGER attempt PK "FK"
        INTEGER reserved
        INTEGER consumed
    }

    active_cache_entries |o--o{ acquisition_progress : "references (active_cache_entry_id)"
    active_cache_entries ||--o{ cache_leases : "references (active_cache_entry_id)"
    cache_locators ||--o{ active_cache_entries : "references (cache_locator_id)"
    job_attempts |o--o{ jobs : "references (job_id, current_attempt)"
    job_attempts ||--o{ acquisition_progress : "references (job_id, attempt)"
    job_attempts ||--o{ cache_leases : "references (job_id, attempt)"
    job_attempts ||--o{ collection_progress : "references (job_id, attempt)"
    job_attempts ||--|o space_reservations : "references (job_id, attempt)"
    jobs ||--o{ job_attempts : "references (job_id)"
```

## Logical Cross-Store References to Core

Operational tables maintain application-level references to Core identities without SQLite foreign key constraints:

| Operational Table | Operational Column | Core Target Table | Core Column | Invariant & ADR Reference |
|---|---|---|---|---|
| `operational_identity` | `catalog_db_instance_id` | `database_identity` | `db_instance_id` | Strict 1:1 ownership binding between Operational DB and Core Catalog (ADR 0002 §2 PF-P11). |
| `acquisition_progress` | `git_acquisition_id` | `git_acquisitions` | `git_acquisition_id` | Git acquisition worker progress tracking Core acquisition entity (ADR 0002 §3.2, PF-P04). |
| `collection_progress` | `fetch_collection_id` | `fetch_collections` | `fetch_collection_id` | API collection worker progress tracking Core fetch collection (ADR 0002 §3.2, PF-P03). |
| `cache_locators` | `repository_uuidv4` | `repositories` | `repository_uuidv4` | Physical cache directory mapping. Core incomplete preservation obligations block cache GC even if locator disappears (three-store-invariants §1). |

[Back to Architecture Overview](overview.md)
