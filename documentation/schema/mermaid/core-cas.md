# Core Module: Retained Content Integrity & CAS

Shared CAS payload storage, quarantine, unreferenced bodies, and durable preservation obligations.

- **Store:** Core (`catalog.sqlite3`)
- **Module Tables:** 7

```mermaid
erDiagram
    payload_admission_staging {
        TEXT stage_uuidv4 PK
        TEXT representation
        BLOB sha256
        BLOB body
        TEXT context_json
        TEXT reason
        INTEGER received_at_us
    }

    payload_quarantine {
        BLOB sha256 PK "FK"
        INTEGER unresolved_payload_id FK
    }

    payloads {
        TEXT representation PK
        BLOB sha256 PK "FK"
    }

    preservation_obligations {
        TEXT git_acquisition_id PK "FK"
        INTEGER roots_fixed
        INTEGER structure_done
        INTEGER digest_done
        INTEGER text_done
        INTEGER complete
    }

    stored_bytes {
        BLOB sha256 PK
        BLOB body
        INTEGER byte_length
    }

    text_bodies {
        INTEGER text_body_id PK
        TEXT body
        INTEGER byte_length
        BLOB sha256 UK
    }

    unresolved_payloads {
        BLOB stored_sha256 FK
        INTEGER detected_at_us
        TEXT diagnostic_json
        INTEGER unresolved_payload_id PK
        TEXT reason
    }

    git_acquisitions {
        TEXT git_acquisition_id PK "External reference from git_identity_intrinsic_and_capture"
    }

    git_acquisitions ||--o| preservation_obligations : "references (git_acquisition_id)"
    stored_bytes ||--o{ payloads : "references (sha256)"
    stored_bytes ||--o{ unresolved_payloads : "references (stored_sha256)"
    stored_bytes ||--o| payload_quarantine : "references (sha256)"
    unresolved_payloads ||--o| payload_quarantine : "references (unresolved_payload_id)"
```

## Cross-Module Foreign Keys

| Source Table | Source Column(s) | Target Table | Target Column(s) | Target Module | Action |
|---|---|---|---|---|---|
| `preservation_obligations` | `git_acquisition_id` | [`git_acquisitions`](core-git.md) | `git_acquisition_id` | Git Identity, Intrinsic DAG & Capture | ON UPDATE RESTRICT, ON DELETE RESTRICT |

[Back to Core Overview](core-overview.md) | [Back to Architecture Overview](overview.md)
