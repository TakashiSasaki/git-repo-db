# Core Module: Portable Identity & Registration

Portable UUIDv4 identities, service instances, sources, repositories, bindings, change requests, and identity relations.

- **Store:** Core (`catalog.sqlite3`)
- **Module Tables:** 14

```mermaid
erDiagram
    change_requests {
        TEXT change_request_id PK
        TEXT repository_uuidv4 FK
        TEXT repository_binding_id FK
        TEXT change_request_kind
        INTEGER provider_change_request_number
    }

    database_identity {
        INTEGER singleton PK
        TEXT format_id
        INTEGER schema_version
        TEXT db_instance_id
        INTEGER local_revision
        BLOB ddl_sha256
        TEXT lifecycle
    }

    documents {
        TEXT change_request_id PK "FK"
        TEXT kind PK
        TEXT provider_change_request_document_id PK
    }

    identity_relation_cancellations {
        TEXT cancellation_uuidv4 PK
        TEXT relation_uuidv4 FK
        TEXT evidence_json
        INTEGER asserted_at_us "nullable"
    }

    identity_relation_staging {
        TEXT record_uuidv4 PK
        BLOB content_sha256 PK
        TEXT kind
        TEXT record_json
        TEXT reason
    }

    identity_relations {
        TEXT relation_uuidv4 PK
        TEXT entity_kind
        TEXT left_repository_uuidv4 FK "nullable"
        TEXT right_repository_uuidv4 FK "nullable"
        TEXT left_service_instance_uuidv4 FK "nullable"
        TEXT right_service_instance_uuidv4 FK "nullable"
        TEXT evidence_json
        INTEGER asserted_at_us "nullable"
    }

    repositories {
        TEXT repository_uuidv4 PK "FK"
        TEXT name
        TEXT preferred_repository_endpoint_id FK "nullable"
        TEXT metadata
    }

    repository_bindings {
        TEXT repository_binding_id PK
        TEXT repository_uuidv4 FK
        TEXT service_instance_uuidv4 FK
        TEXT provider_repository_id "nullable"
        TEXT metadata
        INTEGER created_at_us "nullable"
    }

    repository_endpoints {
        TEXT repository_endpoint_id PK
        TEXT repository_uuidv4 FK
        TEXT url
        TEXT transport
        TEXT label "nullable"
        TEXT metadata
        INTEGER created_at_us "nullable"
    }

    repository_names {
        TEXT repository_uuidv4 PK "FK"
        TEXT name PK
        INTEGER observed_at_us "nullable"
        TEXT provenance_json
    }

    review_threads {
        TEXT change_request_id PK "FK"
        TEXT provider_resource_id PK
    }

    service_instances {
        TEXT service_instance_uuidv4 PK
        TEXT service_kind
        TEXT name
        TEXT web_base_url "nullable"
        TEXT api_base_url "nullable"
        TEXT metadata
        INTEGER created_at_us "nullable"
    }

    source_repositories {
        TEXT source_id PK "FK"
        TEXT repository_uuidv4 PK "FK"
        INTEGER first_seen_us "nullable"
        INTEGER last_seen_us "nullable"
        TEXT name "nullable"
        TEXT metadata_json
        TEXT scope_json
        TEXT parser_module "nullable"
        TEXT parser_version "nullable"
        TEXT field_evidence_json
    }

    sources {
        TEXT source_id PK
        TEXT source_registration_uuidv4 UK
        TEXT service_instance_uuidv4 FK "nullable"
        TEXT discovery_kind
        TEXT name
        TEXT settings "nullable"
    }

    change_requests ||--o{ documents : "references (change_request_id)"
    change_requests ||--o{ review_threads : "references (change_request_id)"
    identity_relations ||--o{ identity_relation_cancellations : "references (relation_uuidv4)"
    repositories |o--o{ identity_relations : "references (left_repository_uuidv4)"
    repositories |o--o{ identity_relations : "references (right_repository_uuidv4)"
    repositories ||--o{ repository_bindings : "references (repository_uuidv4)"
    repositories ||--o{ repository_endpoints : "references (repository_uuidv4)"
    repositories ||--o{ repository_names : "references (repository_uuidv4)"
    repositories ||--o{ source_repositories : "references (repository_uuidv4)"
    repository_bindings ||--o{ change_requests : "references (repository_binding_id, repository_uuidv4)"
    repository_endpoints |o--o{ repositories : "references (preferred_repository_endpoint_id, repository_uuidv4)"
    service_instances |o--o{ identity_relations : "references (left_service_instance_uuidv4)"
    service_instances |o--o{ identity_relations : "references (right_service_instance_uuidv4)"
    service_instances |o--o{ sources : "references (service_instance_uuidv4)"
    service_instances ||--o{ repository_bindings : "references (service_instance_uuidv4)"
    sources ||--o{ source_repositories : "references (source_id)"
```

[Back to Core Overview](core-overview.md) | [Back to Architecture Overview](overview.md)
