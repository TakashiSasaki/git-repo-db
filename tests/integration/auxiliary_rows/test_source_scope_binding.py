"""Captured Source scope owners are checked even for an empty inventory."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.production_context import ContextError
from repo_catalog.domain.shared_values import encode
from tests.integration.auxiliary_rows.test_source_inventory_history import prepare


@pytest.mark.parametrize("method", ["inventory", "admit_inventory_history"])
@pytest.mark.parametrize(
    "key", ["source_registration_uuidv4", "service_instance_uuidv4"]
)
@pytest.mark.parametrize("empty", [False, True], ids=["members", "empty"])
def test_source_reserved_scope_owner_refuses_typed_and_raw_sql_without_writes(
    tmp_path, method, key, empty
):
    old, _, authorization, admission, policy = prepare(tmp_path)
    actual_service = old.provider_repositories[0].service_instance_uuidv4
    wrong_source, wrong_service = str(uuid4()), str(uuid4())
    policy.grants |= DependencySet(
        sources={wrong_source}, provider_registrations={wrong_service}
    )
    if empty:
        old = replace(old, repositories=(), provider_repositories=())
    scope = encode({key: wrong_source if key.startswith("source_") else wrong_service})
    if key == "source_registration_uuidv4":
        with pytest.raises(ContextError, match="SOURCE_SCOPE"):
            replace(old, scope_json=scope)
        # A mutated frozen input must also be revalidated at the trusted adapter.
        malformed = replace(old)
        object.__setattr__(malformed, "scope_json", scope)
    else:
        malformed = replace(old, scope_json=scope)
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        context.provider(wrong_service, "synthetic")
        # Another Source on the same service isolates the exact Source owner
        # check from the independently enforced foreign-origin service check.
        context.source(wrong_source, actual_service)
        with pytest.raises(ContextError, match="SOURCE_SCOPE|SOURCE_SERVICE"):
            getattr(context, method)(malformed)
        assert (
            context.db.execute(
                "SELECT count(*) FROM source_inventory_evidence"
            ).fetchone()[0]
            == 0
        )
        assert (
            context.db.execute("SELECT count(*) FROM source_repositories").fetchone()[0]
            == 0
        )
    with closing(connect(tmp_path / "context.sqlite3", "context")) as db:
        values = list(old.values)
        values[1] = scope
        before = db.total_changes
        with pytest.raises(
            sqlite3.IntegrityError, match="Source inventory scope owner"
        ):
            db.execute(
                "INSERT INTO source_inventory_evidence VALUES(?,?,?,?,?,?,?,?)", values
            )
        assert db.total_changes == before
        assert (
            db.execute("SELECT count(*) FROM source_inventory_evidence").fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("method", ["inventory", "admit_inventory_history"])
@pytest.mark.parametrize("scope_shape", ["object", "scalar", "list"])
def test_actual_scope_fields_and_detached_provenance_preserved_independently(
    tmp_path, method, scope_shape
):
    old, _, authorization, admission, policy = prepare(tmp_path)
    service = old.provider_repositories[0].service_instance_uuidv4
    detached = str(uuid4())
    policy.grants |= DependencySet(sources={detached})
    scope = encode(
        {
            "source_registration_uuidv4": old.source_registration_uuidv4,
            "service_instance_uuidv4": service,
            "endpoint": "actual captured endpoint",
            "opaque": {"source_registration_uuidv4": detached},
        }
        if scope_shape == "object"
        else "actual captured scope"
        if scope_shape == "scalar"
        else ["actual", "scope"]
    )
    provenance = encode(
        {
            "source": "independent parser",
            "evidence": {"source_registration_uuidv4": detached},
        }
    )
    observation = replace(old, scope_json=scope, provenance_json=provenance)
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        getattr(context, method)(observation)
        assert (
            tuple(
                context.db.execute("SELECT * FROM source_inventory_evidence").fetchone()
            )
            == observation.values
        )
        assert (
            context.db.execute(
                "SELECT 1 FROM sources WHERE source_registration_uuidv4=?", (detached,)
            ).fetchone()
            is None
        )
    assert not (tmp_path / "repository.sqlite3").exists()
