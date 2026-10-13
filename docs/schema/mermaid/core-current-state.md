# Core Module: Current API Values & Projections

Latest state projections for PRs, issues, documents, and review threads with JSON-contract provenance and generated columns.

- **Store:** Core (`catalog.sqlite3`)
- **Module Tables:** 5

```mermaid
erDiagram
    change_request_state {
        TEXT change_request_id PK "FK"
        TEXT kind
        TEXT provider_resource_id "nullable"
        TEXT state "nullable"
        INTEGER draft "nullable"
        INTEGER merged "nullable"
        INTEGER locked "nullable"
        TEXT author "nullable"
        TEXT url "nullable"
        TEXT object_format "nullable"
        BLOB head_oid "nullable"
        BLOB base_oid "nullable"
        BLOB merge_oid "nullable"
        TEXT head_ref "nullable"
        TEXT base_ref "nullable"
        TEXT head_repository_binding_id FK "nullable"
        TEXT base_repository_binding_id FK "nullable"
        INTEGER created_at_us "nullable"
        INTEGER closed_at_us "nullable"
        INTEGER merged_at_us "nullable"
        TEXT repository_uuidv4 FK
        TEXT repository_binding_id FK
        TEXT service_instance_uuidv4 FK
        INTEGER provider_updated_at_us "nullable"
        TEXT provider_clock_scope "nullable"
        INTEGER observed_at_us
        INTEGER last_checked_at_us "nullable"
        INTEGER parsed_at_us
        TEXT parser_module
        TEXT parser_version
        TEXT metadata
        TEXT acquisition_scope_json
        TEXT field_evidence_json
    }

    document_state {
        TEXT change_request_id PK "FK"
        TEXT kind PK "FK"
        TEXT provider_change_request_document_id PK "FK"
        TEXT body_status
        BLOB text_body_sha256 FK "nullable"
        TEXT author "nullable"
        TEXT url "nullable"
        INTEGER deleted
        TEXT repository_uuidv4 FK
        TEXT repository_binding_id FK
        TEXT service_instance_uuidv4 FK
        INTEGER provider_updated_at_us "nullable"
        TEXT provider_clock_scope "nullable"
        INTEGER observed_at_us
        INTEGER last_checked_at_us "nullable"
        INTEGER parsed_at_us
        TEXT parser_module
        TEXT parser_version
        TEXT metadata
        TEXT acquisition_scope_json
        TEXT field_evidence_json
    }

    issue_resources {
        TEXT service_instance_uuidv4 PK "FK"
        TEXT kind PK
        TEXT provider_resource_id PK
        TEXT repository_uuidv4 FK
        TEXT repository_binding_id FK
        INTEGER provider_issue_number
        TEXT parent_provider_resource_id FK "nullable"
        TEXT parent_kind FK "GENERATED STORED"
        BLOB text_body_sha256 FK "nullable"
        TEXT body_status
        TEXT title "nullable"
        TEXT state "nullable"
        TEXT author "nullable"
        TEXT url "nullable"
        INTEGER deleted
        INTEGER provider_updated_at_us "nullable"
        TEXT provider_clock_scope "nullable"
        INTEGER observed_at_us
        INTEGER last_checked_at_us "nullable"
        INTEGER parsed_at_us
        TEXT parser_module
        TEXT parser_version
        TEXT metadata
        TEXT acquisition_scope_json
        TEXT field_evidence_json
    }

    review_resources {
        TEXT change_request_id PK "FK"
        TEXT kind PK
        TEXT provider_change_request_document_id PK
        TEXT repository_uuidv4 FK
        TEXT repository_binding_id FK
        TEXT service_instance_uuidv4 FK
        BLOB text_body_sha256 FK "nullable"
        TEXT body_status
        TEXT state "nullable"
        TEXT author "nullable"
        TEXT url "nullable"
        INTEGER deleted
        INTEGER submitted_at_us "nullable"
        TEXT target_commit_oid "nullable"
        TEXT original_commit_oid "nullable"
        INTEGER original_position "nullable"
        INTEGER current_position "nullable"
        TEXT raw_path "nullable"
        TEXT diff_hunk "nullable"
        TEXT review_provider_resource_id FK "nullable"
        TEXT in_reply_to_provider_resource_id FK "nullable"
        TEXT review_thread_provider_resource_id FK "nullable"
        TEXT parent_review_kind FK "GENERATED STORED"
        TEXT reply_kind FK "GENERATED STORED"
        INTEGER provider_updated_at_us "nullable"
        TEXT provider_clock_scope "nullable"
        INTEGER observed_at_us
        INTEGER last_checked_at_us "nullable"
        INTEGER parsed_at_us
        TEXT parser_module
        TEXT parser_version
        TEXT metadata
        TEXT acquisition_scope_json
        TEXT field_evidence_json
    }

    review_thread_state {
        TEXT change_request_id PK "FK"
        TEXT provider_resource_id PK "FK"
        TEXT kind
        INTEGER resolved "nullable"
        INTEGER outdated "nullable"
        BLOB raw_path "nullable"
        INTEGER line "nullable"
        INTEGER start_line "nullable"
        INTEGER original_line "nullable"
        INTEGER original_start_line "nullable"
        TEXT side "nullable"
        TEXT start_side "nullable"
        TEXT object_format "nullable"
        BLOB commit_oid "nullable"
        BLOB original_commit_oid "nullable"
        TEXT diff_hunk "nullable"
        TEXT repository_uuidv4 FK
        TEXT repository_binding_id FK
        TEXT service_instance_uuidv4 FK
        INTEGER provider_updated_at_us "nullable"
        TEXT provider_clock_scope "nullable"
        INTEGER observed_at_us
        INTEGER last_checked_at_us "nullable"
        INTEGER parsed_at_us
        TEXT parser_module
        TEXT parser_version
        TEXT metadata
        TEXT acquisition_scope_json
        TEXT field_evidence_json
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

    review_threads {
        TEXT change_request_id, provider_resource_id PK "External reference from portable_identity_and_registration"
    }

    service_instances {
        TEXT service_instance_uuidv4 PK "External reference from portable_identity_and_registration"
    }

    text_bodies {
        TEXT text_body_id PK "External reference from retained_content_integrity"
    }

    change_requests ||--o{ change_request_state : "references (change_request_id, repository_uuidv4)"
    change_requests ||--o{ document_state : "references (change_request_id, repository_uuidv4)"
    change_requests ||--o{ review_resources : "references (change_request_id)"
    change_requests ||--o{ review_resources : "references (change_request_id, repository_uuidv4)"
    change_requests ||--o{ review_thread_state : "references (change_request_id, repository_uuidv4)"
    change_requests ||--|o change_request_state : "references (change_request_id)"
    documents ||--|o document_state : "references (change_request_id, kind, provider_change_request_document_id)"
    issue_resources |o--o{ issue_resources : "references (service_instance_uuidv4, parent_kind, parent_provider_resource_id)"
    repositories ||--o{ change_request_state : "references (repository_uuidv4)"
    repositories ||--o{ document_state : "references (repository_uuidv4)"
    repositories ||--o{ issue_resources : "references (repository_uuidv4)"
    repositories ||--o{ review_resources : "references (repository_uuidv4)"
    repositories ||--o{ review_thread_state : "references (repository_uuidv4)"
    repository_bindings |o--o{ change_request_state : "references (base_repository_binding_id)"
    repository_bindings |o--o{ change_request_state : "references (head_repository_binding_id)"
    repository_bindings ||--o{ change_request_state : "references (repository_binding_id, repository_uuidv4)"
    repository_bindings ||--o{ document_state : "references (repository_binding_id, repository_uuidv4)"
    repository_bindings ||--o{ issue_resources : "references (repository_binding_id, repository_uuidv4)"
    repository_bindings ||--o{ review_resources : "references (repository_binding_id, repository_uuidv4)"
    repository_bindings ||--o{ review_thread_state : "references (repository_binding_id, repository_uuidv4)"
    review_resources |o--o{ review_resources : "references (change_request_id, parent_review_kind, review_provider_resource_id)"
    review_resources |o--o{ review_resources : "references (change_request_id, reply_kind, in_reply_to_provider_resource_id)"
    review_threads |o--o{ review_resources : "references (change_request_id, review_thread_provider_resource_id)"
    review_threads ||--|o review_thread_state : "references (change_request_id, provider_resource_id)"
    service_instances ||--o{ change_request_state : "references (service_instance_uuidv4)"
    service_instances ||--o{ document_state : "references (service_instance_uuidv4)"
    service_instances ||--o{ issue_resources : "references (service_instance_uuidv4)"
    service_instances ||--o{ review_resources : "references (service_instance_uuidv4)"
    service_instances ||--o{ review_thread_state : "references (service_instance_uuidv4)"
    text_bodies |o--o{ document_state : "references (text_body_sha256)"
    text_bodies |o--o{ issue_resources : "references (text_body_sha256)"
    text_bodies |o--o{ review_resources : "references (text_body_sha256)"
```

## Cross-Module Foreign Keys

| Source Table | Source Column(s) | Target Table | Target Column(s) | Target Module | Action |
|---|---|---|---|---|---|
| `change_request_state` | `change_request_id, repository_uuidv4` | [`change_requests`](core-identity.md) | `change_request_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `change_request_state` | `repository_binding_id, repository_uuidv4` | [`repository_bindings`](core-identity.md) | `repository_binding_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `change_request_state` | `service_instance_uuidv4` | [`service_instances`](core-identity.md) | `service_instance_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `change_request_state` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `change_request_state` | `base_repository_binding_id` | [`repository_bindings`](core-identity.md) | `repository_binding_id` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `change_request_state` | `head_repository_binding_id` | [`repository_bindings`](core-identity.md) | `repository_binding_id` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `change_request_state` | `change_request_id` | [`change_requests`](core-identity.md) | `change_request_id` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `document_state` | `change_request_id, repository_uuidv4` | [`change_requests`](core-identity.md) | `change_request_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `document_state` | `change_request_id, kind, provider_change_request_document_id` | [`documents`](core-identity.md) | `change_request_id, kind, provider_change_request_document_id` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `document_state` | `repository_binding_id, repository_uuidv4` | [`repository_bindings`](core-identity.md) | `repository_binding_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `document_state` | `service_instance_uuidv4` | [`service_instances`](core-identity.md) | `service_instance_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `document_state` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `document_state` | `text_body_sha256` | [`text_bodies`](core-cas.md) | `sha256` | Retained Content Integrity & CAS | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `issue_resources` | `repository_binding_id, repository_uuidv4` | [`repository_bindings`](core-identity.md) | `repository_binding_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `issue_resources` | `text_body_sha256` | [`text_bodies`](core-cas.md) | `sha256` | Retained Content Integrity & CAS | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `issue_resources` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `issue_resources` | `service_instance_uuidv4` | [`service_instances`](core-identity.md) | `service_instance_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_resources` | `change_request_id, review_thread_provider_resource_id` | [`review_threads`](core-identity.md) | `change_request_id, provider_resource_id` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_resources` | `repository_binding_id, repository_uuidv4` | [`repository_bindings`](core-identity.md) | `repository_binding_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_resources` | `change_request_id, repository_uuidv4` | [`change_requests`](core-identity.md) | `change_request_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_resources` | `text_body_sha256` | [`text_bodies`](core-cas.md) | `sha256` | Retained Content Integrity & CAS | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_resources` | `service_instance_uuidv4` | [`service_instances`](core-identity.md) | `service_instance_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_resources` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_resources` | `change_request_id` | [`change_requests`](core-identity.md) | `change_request_id` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_thread_state` | `change_request_id, repository_uuidv4` | [`change_requests`](core-identity.md) | `change_request_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_thread_state` | `change_request_id, provider_resource_id` | [`review_threads`](core-identity.md) | `change_request_id, provider_resource_id` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_thread_state` | `repository_binding_id, repository_uuidv4` | [`repository_bindings`](core-identity.md) | `repository_binding_id, repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_thread_state` | `service_instance_uuidv4` | [`service_instances`](core-identity.md) | `service_instance_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |
| `review_thread_state` | `repository_uuidv4` | [`repositories`](core-identity.md) | `repository_uuidv4` | Portable Identity & Registration | ON UPDATE NO ACTION, ON DELETE NO ACTION |

[Back to Core Overview](core-overview.md) | [Back to Architecture Overview](overview.md)
