# Core Module: Domain Enumeration & Coverage Evidence

Collections, memberships, completion markers, typed coverage scopes/claims, and code listing assessments.

- **Store:** Core (`catalog.sqlite3`)
- **Module Tables:** 19

```mermaid
erDiagram
    change_request_events {
        TEXT change_request_event_uuidv4 PK
        TEXT change_request_id FK
        TEXT repository_uuidv4 FK
        TEXT provider_event_id "nullable"
        TEXT event_kind
        TEXT actor "nullable"
        INTEGER created_at_us "nullable"
        TEXT object_format "nullable"
        BLOB commit_oid "nullable"
        TEXT metadata
        INTEGER observed_at_us "nullable"
        TEXT parser_module
        TEXT parser_version
    }

    code_acquisitions {
        TEXT code_assessment_id PK "FK"
        TEXT role PK
        TEXT object_format
        BLOB oid
        INTEGER acquisition_root_id FK "nullable"
    }

    code_assessments {
        TEXT code_assessment_id PK
        TEXT change_request_id FK
        TEXT repository_uuidv4 FK
        TEXT commit_code_listing_id FK "nullable"
        TEXT file_code_listing_id FK "nullable"
        TEXT state
        TEXT object_format "nullable"
        BLOB head_oid "nullable"
        BLOB base_oid "nullable"
        INTEGER observed_at_us "nullable"
        TEXT parser_module
        TEXT parser_version
        TEXT details_json
    }

    code_commits {
        TEXT code_listing_id PK "FK"
        INTEGER position PK
        TEXT repository_uuidv4 FK
        TEXT object_format
        BLOB oid
        TEXT metadata
    }

    code_file_changes {
        TEXT code_listing_id PK "FK"
        INTEGER position PK
        TEXT repository_uuidv4 FK
        BLOB raw_path
        BLOB previous_path "nullable"
        TEXT status "nullable"
        TEXT object_format "nullable"
        BLOB oid "nullable"
        INTEGER additions "nullable"
        INTEGER deletions "nullable"
        INTEGER changes "nullable"
        TEXT patch "nullable"
        TEXT patch_status "nullable"
        TEXT metadata
    }

    code_listing_progress {
        TEXT code_listing_id PK "FK"
        TEXT state
        INTEGER terminal
        INTEGER page_count
        INTEGER context_proven
    }

    code_listings {
        TEXT code_listing_id PK
        TEXT change_request_id FK
        TEXT fetch_collection_id FK
        TEXT kind
        TEXT resume_scope_id "nullable"
        TEXT object_format "nullable"
        BLOB head_oid "nullable"
        BLOB base_oid "nullable"
    }

    collection_memberships {
        TEXT fetch_collection_id PK "FK"
        TEXT change_request_id PK "FK"
        TEXT kind PK "FK"
        TEXT provider_change_request_document_id PK "FK"
        INTEGER ordinal
    }

    completion_markers {
        TEXT completion_marker_uuidv4 UK
        INTEGER completion_marker_id PK "nullable"
        TEXT resume_scope_id "nullable"
        TEXT fetch_collection_id FK
        TEXT asserted_state
        TEXT evidence
        INTEGER observed_at_us "nullable"
    }

    coverage_claim_markers {
        INTEGER coverage_claim_id PK "FK"
        TEXT completion_marker_uuidv4 PK "FK"
    }

    coverage_claims {
        INTEGER coverage_claim_id PK "nullable"
        TEXT coverage_scope_id FK
        TEXT coverage_state
        INTEGER observed_at_us
        TEXT details_json "nullable"
    }

    coverage_scopes {
        TEXT coverage_scope_id PK
        TEXT repository_uuidv4 FK
        TEXT change_request_id FK "nullable"
        TEXT kind
    }

    current_collection_pages {
        TEXT fetch_collection_id PK "FK"
        INTEGER ordinal PK
        INTEGER observed_at_us
        INTEGER has_next
        TEXT members
        INTEGER status
        TEXT parser_module
        TEXT parser_version
    }

    fetch_collections {
        TEXT fetch_collection_id PK
        TEXT repository_uuidv4 FK
        TEXT change_request_id FK "nullable"
        TEXT source_id FK "nullable"
        TEXT kind
        TEXT resume_scope_id "nullable"
        INTEGER observed_at_us "nullable"
        TEXT scope_json
    }

    resume_scopes {
        TEXT resume_scope_id PK
        TEXT repository_uuidv4 FK
        TEXT repository_binding_id FK "nullable"
        TEXT source_id FK "nullable"
        TEXT principal_ref "nullable"
        TEXT api_version "nullable"
        TEXT endpoint "nullable"
        TEXT request_context
        TEXT parser_version
        TEXT confidence
    }

    source_inventory_assessments {
        TEXT source_id PK "FK"
        TEXT scope_key
        TEXT scope_json PK
        INTEGER observed_at_us PK
        TEXT state PK
        INTEGER terminal PK
        TEXT members_json PK
        TEXT parser_module
        TEXT parser_version
        TEXT reason "nullable"
    }

    thread_collection_continuations {
        TEXT fetch_collection_id PK "FK"
        TEXT provider_resource_id PK
        TEXT child_cursor "nullable"
        INTEGER observed_at_us
    }

    thread_collection_requirements {
        TEXT fetch_collection_id PK "FK"
        TEXT provider_resource_id PK
        TEXT child_fetch_collection_id FK "nullable"
        INTEGER required_observed_at_us
        TEXT object_format "nullable"
        BLOB head_oid "nullable"
        BLOB base_oid "nullable"
    }

    thread_collection_targets {
        TEXT fetch_collection_id PK "FK"
        TEXT role PK
        TEXT object_format "nullable"
        BLOB oid "nullable"
        INTEGER observed_at_us
    }

    acquisition_roots {
        TEXT acquisition_root_id PK "External reference from git_identity_intrinsic_and_capture"
    }

    change_requests {
        TEXT change_request_id PK "External reference from portable_identity_and_registration"
    }

    documents {
        TEXT change_request_id, kind, provider_change_request_document_id PK "External reference from portable_identity_and_registration"
    }

    repositories {
        TEXT repository_uuidv4 PK "External reference from portable_identity_and_registration"
    }

    repository_bindings {
        TEXT repository_binding_id PK "External reference from portable_identity_and_registration"
    }

    sources {
        TEXT source_id PK "External reference from portable_identity_and_registration"
    }

    acquisition_roots |o--o{ code_acquisitions : "references (acquisition_root_id)"
    change_requests |o--o{ coverage_scopes : "references (change_request_id, repository_uuidv4)"
    change_requests |o--o{ fetch_collections : "references (change_request_id, repository_uuidv4)"
    change_requests ||--o{ change_request_events : "references (change_request_id, repository_uuidv4)"
    change_requests ||--o{ code_assessments : "references (change_request_id, repository_uuidv4)"
    code_assessments ||--o{ code_acquisitions : "references (code_assessment_id)"
    code_listings |o--o{ code_assessments : "references (commit_code_listing_id, change_request_id)"
    code_listings |o--o{ code_assessments : "references (file_code_listing_id, change_request_id)"
    code_listings ||--o{ code_commits : "references (code_listing_id)"
    code_listings ||--o{ code_file_changes : "references (code_listing_id)"
    code_listings ||--|o code_listing_progress : "references (code_listing_id)"
    completion_markers ||--o{ coverage_claim_markers : "references (completion_marker_uuidv4)"
    coverage_claims ||--o{ coverage_claim_markers : "references (coverage_claim_id)"
    coverage_scopes ||--o{ coverage_claims : "references (coverage_scope_id)"
    documents ||--o{ collection_memberships : "references (change_request_id, kind, provider_change_request_document_id)"
    fetch_collections |o--o{ thread_collection_requirements : "references (child_fetch_collection_id)"
    fetch_collections ||--o{ code_listings : "references (fetch_collection_id, change_request_id)"
    fetch_collections ||--o{ collection_memberships : "references (fetch_collection_id)"
    fetch_collections ||--o{ completion_markers : "references (fetch_collection_id)"
    fetch_collections ||--o{ current_collection_pages : "references (fetch_collection_id)"
    fetch_collections ||--o{ thread_collection_continuations : "references (fetch_collection_id)"
    fetch_collections ||--o{ thread_collection_requirements : "references (fetch_collection_id)"
    fetch_collections ||--o{ thread_collection_targets : "references (fetch_collection_id)"
    repositories ||--o{ code_commits : "references (repository_uuidv4)"
    repositories ||--o{ code_file_changes : "references (repository_uuidv4)"
    repositories ||--o{ coverage_scopes : "references (repository_uuidv4)"
    repositories ||--o{ fetch_collections : "references (repository_uuidv4)"
    repositories ||--o{ resume_scopes : "references (repository_uuidv4)"
    repository_bindings |o--o{ resume_scopes : "references (repository_binding_id, repository_uuidv4)"
    sources |o--o{ fetch_collections : "references (source_id)"
    sources |o--o{ resume_scopes : "references (source_id)"
    sources ||--o{ source_inventory_assessments : "references (source_id)"
```

## Cross-Module Foreign Keys

| Source Table | Source Column(s) | Target Table | Target Column(s) | Target Module | Action |
|---|---|---|---|---|---|
| `change_request_events` | `change_request_id, repository_uuidv4` | [`change_requests`](core-identity.md) | `change_request_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `code_acquisitions` | `acquisition_root_id` | [`acquisition_roots`](core-git.md) | `acquisition_root_id` | Git Identity, Intrinsic DAG & Capture | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `code_assessments` | `change_request_id, repository_uuidv4` | [`change_requests`](core-identity.md) | `change_request_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `code_commits` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `code_file_changes` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `collection_memberships` | `change_request_id, kind, provider_change_request_document_id` | [`documents`](core-identity.md) | `change_request_id, kind, provider_change_request_document_id` | Portable Identity & Registration | ON UPDATE RESTRICT, ON DELETE RESTRICT |
| `coverage_scopes` | `change_request_id, repository_uuidv4` | [`change_requests`](core-identity.md) | `change_request_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE RESTRICT, ON DELETE RESTRICT |
| `coverage_scopes` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE RESTRICT, ON DELETE RESTRICT |
| `fetch_collections` | `change_request_id, repository_uuidv4` | [`change_requests`](core-identity.md) | `change_request_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE RESTRICT, ON DELETE RESTRICT |
| `fetch_collections` | `source_id` | [`sources`](core-identity.md) | `source_id` | Portable Identity & Registration | ON UPDATE RESTRICT, ON DELETE RESTRICT |
| `fetch_collections` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE RESTRICT, ON DELETE RESTRICT |
| `resume_scopes` | `repository_binding_id, repository_uuidv4` | [`repository_bindings`](core-identity.md) | `repository_binding_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE RESTRICT, ON DELETE RESTRICT |
| `resume_scopes` | `source_id` | [`sources`](core-identity.md) | `source_id` | Portable Identity & Registration | ON UPDATE RESTRICT, ON DELETE RESTRICT |
| `resume_scopes` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE RESTRICT, ON DELETE RESTRICT |
| `source_inventory_assessments` | `source_id` | [`sources`](core-identity.md) | `source_id` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |

[Back to Core Overview](core-overview.md) | [Back to Architecture Overview](overview.md)
