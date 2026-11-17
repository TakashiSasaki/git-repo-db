"""Full owner coordinates distinguish nominal keys and preserve caller units."""

import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import CoverageScope, ResourceKey
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.production_context import ContextError
from tests.integration.p5.conftest import init_catalog_stores


def prepare(path):
    repository, _ = init_catalog_stores(path, stores=("context", "operational"))
    other, absent, service = str(uuid4()), str(uuid4()), str(uuid4())
    parent = ResourceKey.from_native(service, "pull_request", other)
    wrong = (
        ResourceKey.from_native(other, "pull_request", other),
        ResourceKey.from_native(service, "pull_request", "absent"),
        ResourceKey.from_native(service, "issue", other),
    )
    grants = DependencySet(
        resources={parent, *wrong},
        repositories={repository, other, absent},
        provider_registrations={service, other},
    )
    auth, admission, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    with Context.transaction(path, authorization=auth, admission=admission) as context:
        context.provider(service, "reported-provider")
        context.repository(repository)
        context.repository(other)
        context.resource(parent)
    return auth, admission, parent, other, absent, wrong


def test_equal_text_repository_and_pr_identifiers_keep_distinct_explicit_coverage_owners(
    tmp_path,
):
    auth, admission, parent, repository, _, _ = prepare(tmp_path)
    repo_scope, pr_scope = (
        CoverageScope.repository(repository, "metadata"),
        CoverageScope.resource(parent, "metadata"),
    )
    assert repo_scope != pr_scope and repo_scope.encoded != pr_scope.encoded
    with Context.transaction(
        tmp_path, authorization=auth, admission=admission
    ) as context:
        for scope, state in ((repo_scope, "complete"), (pr_scope, "partial")):
            context.scope(scope)
            context.admit_coverage(CoverageClaim(scope, 100, state))
    with Context.snapshot(tmp_path) as context:
        repository_coverage = context.coverage(repo_scope)
        assert repository_coverage.state == "unknown"
        assert repository_coverage.claims[0].state == "complete"
        assert context.coverage(pr_scope).state == "partial"
        assert (
            context.db.execute("SELECT count(*) FROM coverage_scopes").fetchone()[0]
            == 2
        )


@pytest.mark.parametrize(
    "which",
    ["foreign-namespace", "missing-pr", "missing-repository", "wrong-resource-kind"],
)
def test_unknown_full_coverage_owner_refuses_without_writes_inside_the_caller_transaction(
    tmp_path, which
):
    auth, admission, _, _, absent, wrong = prepare(tmp_path)
    scope = {
        "foreign-namespace": CoverageScope.resource(wrong[0], "metadata"),
        "missing-pr": CoverageScope.resource(wrong[1], "metadata"),
        "missing-repository": CoverageScope.repository(absent, "metadata"),
        "wrong-resource-kind": CoverageScope.resource(wrong[2], "metadata"),
    }[which]
    with Context.transaction(
        tmp_path, authorization=auth, admission=admission
    ) as context:
        before = context.db.execute("SELECT * FROM coverage_scopes").fetchall()
        with pytest.raises(
            (sqlite3.IntegrityError, ContextError, AdmissionRefused)
        ) as error:
            context.scope(scope)
            context.admit_coverage(CoverageClaim(scope, 100, "complete"))
        if isinstance(error.value, AdmissionRefused):
            assert error.value.code == "MISSING_DEPENDENCY"
        assert context.db.execute("SELECT * FROM coverage_scopes").fetchall() == before
        assert (
            context.db.execute("SELECT count(*) FROM coverage_scopes").fetchone()[0]
            == 0
        )
        assert (
            context.db.execute("SELECT count(*) FROM coverage_claims").fetchone()[0]
            == 0
        )
        assert context.db.in_transaction
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_explicit_coverage_owner_preserves_original_advisory_bytes_and_caller_rollback(
    tmp_path,
):
    auth, admission, parent, repository, _, _ = prepare(tmp_path)
    scope = CoverageScope.resource(parent, "metadata")
    other = CoverageScope.repository(repository, "metadata")
    original = '{"reason":"first original advisory"}'
    # Authored advisory objects use the explicit canonical metadata grammar.
    with pytest.raises(ValueError, match="canonical"):
        CoverageClaim(
            scope, 100, "complete", '{ "reason" : "first original advisory" }'
        )
    with Context.transaction(
        tmp_path, authorization=auth, admission=admission
    ) as context:
        context.scope(scope)
        context.scope(other)
        assert (
            context.admit_coverage(CoverageClaim(scope, 100, "complete", original))
            == "insert"
        )
        assert (
            context.admit_coverage(
                CoverageClaim(scope, 100, "complete", '{"reason":"duplicate advisory"}')
            )
            == "duplicate"
        )
        assert context.admit_coverage(CoverageClaim(scope, 99, "partial")) == "stale"
        before = context.db.execute("SELECT * FROM coverage_claims").fetchall()
        assert (
            context.db.execute("SELECT details_json FROM coverage_claims").fetchone()[0]
            == original
        )
    with pytest.raises(RuntimeError, match="caller rollback"):
        with Context.transaction(
            tmp_path, authorization=auth, admission=admission
        ) as context:
            context.admit_coverage(CoverageClaim(other, 200, "complete"))
            context.admit_coverage(CoverageClaim(scope, 200, "partial"))
            raise RuntimeError("caller rollback")
    with Context.snapshot(tmp_path) as context:
        assert context.db.execute("SELECT * FROM coverage_claims").fetchall() == before
        assert context.coverage(scope).state == "unknown"
        assert context.coverage(scope).claims[0].state == "complete"
        assert context.coverage(other).state == "unknown"
