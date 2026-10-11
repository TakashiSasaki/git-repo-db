"""Explicit synthetic typed domain facts without transport or parser authority."""

import json
import sqlite3

from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, SCHEMA_VERSION, schema_sql

SERVICE = "00000000-0000-4000-8000-000000000101"
SOURCE = "00000000-0000-4000-8000-000000000201"
TIME_US = 1_791_244_800_000_000


def repository_uuid(number):
    return f"10000000-0000-4000-8000-{number:012d}"


def insert(db, table, **values):
    return db.execute(
        f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
        tuple(values.values()),
    )


def fresh_domain_db(sql=None):
    db = sqlite3.connect(":memory:", isolation_level=None)
    register_git_object_sql_function(db)
    db.executescript(sql or schema_sql())
    insert(
        db,
        "database_identity",
        singleton=1,
        format_id="repo-catalog/catalog3",
        schema_version=SCHEMA_VERSION,
        db_instance_id="00000000-0000-4000-8000-000000000301",
        local_revision=0,
        ddl_sha256=DDL_SHA256,
        lifecycle="validated",
    )
    seed_owners(db)
    return db


def seed_owners(db):
    insert(
        db,
        "service_instances",
        service_instance_uuidv4=SERVICE,
        service_kind="github",
        name="synthetic",
        metadata="{}",
    )
    insert(
        db,
        "sources",
        source_registration_uuidv4=SOURCE,
        source_id="source",
        service_instance_uuidv4=SERVICE,
        discovery_kind="github_inventory",
        name="synthetic",
        settings="{}",
    )
    for number in (1, 2):
        repository = repository_uuid(number)
        insert(
            db,
            "repositories",
            repository_uuidv4=repository,
            name=f"synthetic/repo{number}",
            metadata="{}",
        )
        insert(
            db,
            "repository_bindings",
            repository_binding_id=f"binding-{number}",
            repository_uuidv4=repository,
            service_instance_uuidv4=SERVICE,
            provider_repository_id=str(number),
            metadata="{}",
        )
        insert(
            db,
            "change_requests",
            change_request_id=f"pr{number}",
            repository_uuidv4=repository,
            repository_binding_id=f"binding-{number}",
            change_request_kind="pull_request",
            provider_change_request_number=1,
        )


def candidate(
    number=1,
    *,
    kind="change-request",
    clock=TIME_US,
    observed_at_us=TIME_US,
    parser_version="1",
    **fields,
):
    owner = {
        "repository_uuidv4": repository_uuid(number),
        "repository_binding_id": f"binding-{number}",
        "service_instance_uuidv4": SERVICE,
        "change_request_id": f"pr{number}",
    }
    scopes = {
        "change-request": "github-pr-updated-at",
        "pr-title": "github-pr-updated-at",
        "pr-body": "github-pr-updated-at",
        "issue-comment": "github-issue-comment-updated-at",
    }
    return {
        **owner,
        "kind": kind,
        "provider_updated_at_us": clock if kind != "review-thread" else None,
        "provider_clock_scope": scopes.get(kind),
        "observed_at_us": observed_at_us,
        "parsed_at_us": observed_at_us,
        "parser_module": "synthetic.domain-contract",
        "parser_version": parser_version,
        "acquisition_scope": {**owner, "endpoint": "synthetic-current"},
        **fields,
    }


def admit_pr(db, number=1, **fields):
    return CurrentApiState(db).admit(
        "change_request_state", candidate(number, **fields), source="import"
    )


def admit_document(db, number=1, *, kind="pr-body", resource="123", **fields):
    return CurrentApiState(db).admit(
        "document_state",
        candidate(
            number, kind=kind, provider_change_request_document_id=resource, **fields
        ),
        source="import",
    )


def admit_thread(db, number=1, *, resource="thread", **fields):
    return CurrentApiState(db).admit(
        "review_thread_state",
        candidate(
            number, kind="review-thread", provider_resource_id=resource, **fields
        ),
        source="import",
    )


def collection(db, number=1, *, identity="collection", kind="files", context=None):
    """An exact domain enumeration scope, independent of resource admission."""
    scope_id = "scope-" + identity
    insert(
        db,
        "resume_scopes",
        resume_scope_id=scope_id,
        repository_uuidv4=repository_uuid(number),
        repository_binding_id=f"binding-{number}",
        request_context="{}",
        parser_version="1",
        confidence="proven",
    )
    insert(
        db,
        "fetch_collections",
        fetch_collection_id=identity,
        repository_uuidv4=repository_uuid(number),
        change_request_id=f"pr{number}",
        kind=kind,
        resume_scope_id=scope_id,
        scope_json=json.dumps(
            {
                "repository_uuidv4": repository_uuid(number),
                "repository_binding_id": f"binding-{number}",
                "service_instance_uuidv4": SERVICE,
                "change_request_id": f"pr{number}",
                "endpoint": "synthetic-enumeration",
                "request_context": context or {},
            }
        ),
    )
    return scope_id
