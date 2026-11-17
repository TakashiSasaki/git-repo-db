"""Separated identity authority keeps cancellation, conflict and closure semantics."""

from contextlib import closing, contextmanager
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.identity_assertions import IdentityAssertions
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.shared_values import CoreFailure, Provenance


def assertion(kind, left, right, *, ident=None):
    record = {
        "relation_uuidv4": ident or str(uuid4()),
        "entity_kind": kind,
        "left_repository_uuidv4": None,
        "right_repository_uuidv4": None,
        "left_service_instance_uuidv4": None,
        "right_service_instance_uuidv4": None,
        "evidence_json": '{"kind":"explicit-user-assertion"}',
        "asserted_at_us": None,
    }
    suffix = "repository_uuidv4" if kind == "repository" else "service_instance_uuidv4"
    record[f"left_{suffix}"] = left
    record[f"right_{suffix}"] = right
    return record


def cancellation(record):
    return {
        "cancellation_uuidv4": str(uuid4()),
        "relation_uuidv4": record["relation_uuidv4"],
        "evidence_json": "{}",
        "asserted_at_us": 100,
    }


def original(record):
    ident = record.get("cancellation_uuidv4", record["relation_uuidv4"])
    return Provenance(
        "explicit-local-input", ident, "identity-evidence", "typed-json", "1"
    )


class Authority:
    def __init__(self, tmp_path, kind, endpoints, relations):
        self.directory = tmp_path
        self.kind = kind
        self.endpoints = endpoints
        role = "core" if kind == "repository" else "context"
        initialize(tmp_path / f"{role}.sqlite3", role, str(uuid4()), str(uuid4()))
        self.auth, self.admission, self.policy = create_local_admission_service(
            grants=DependencySet(
                provider_registrations=endpoints, identity_assertions=relations
            ),
            selection=AdmissionSelection(all_selected=True),
        )
        with self.open(write=True) as service:
            if kind == "repository":
                for endpoint in endpoints:
                    service.core.admit_repository(endpoint)
            else:
                for endpoint in endpoints:
                    service.context.provider(endpoint, "identity-test")

    @contextmanager
    def open(self, *, write=False):
        if self.kind == "repository":
            with closing(GitCore(self.directory / "core.sqlite3")) as core:
                yield IdentityAssertions(core=core)
        elif write:
            with Context.transaction(
                self.directory, authorization=self.auth, admission=self.admission
            ) as context:
                yield IdentityAssertions(context=context)
        else:
            with Context.snapshot(self.directory) as context:
                yield IdentityAssertions(context=context)


@pytest.mark.parametrize("kind", ["repository", "service"])
def test_transitive_equivalence_cancellation_first_and_no_physical_merge(
    tmp_path, kind
):
    a, b, c = [str(uuid4()) for _ in range(3)]
    first, second = assertion(kind, a, b), assertion(kind, b, c)
    before = cancellation(first)
    authority = Authority(
        tmp_path, kind, {a, b, c}, {first["relation_uuidv4"], second["relation_uuidv4"]}
    )
    role = "core" if kind == "repository" else "context"
    table = "repositories" if kind == "repository" else "providers"
    column = "repository_uuidv4" if kind == "repository" else "service_instance_uuidv4"
    with closing(connect(tmp_path / f"{role}.sqlite3", role)) as db:
        original_identities = {
            row[0] for row in db.execute(f"SELECT {column} FROM {table}")
        }
    assert {a, b, c} <= original_identities
    with authority.open(write=True) as service:
        assert (
            service.admit("cancellation", before, original(before), entity_kind=kind)
            == "accepted"
        )
        assert service.admit("relation", first, original(first)) == "accepted"
        assert not service.status()["active_identity_relations"]
        assert service.admit("relation", first, original(first)) == "duplicate"
        assert (
            service.admit("cancellation", before, original(before), entity_kind=kind)
            == "duplicate"
        )
        assert service.admit("relation", second, original(second)) == "accepted"
    with authority.open() as service:
        status = service.status()
        assert len(status["identity_relations"]) == 2
        assert len(status["identity_relation_cancellations"]) == 1
        closure = status[f"{kind}_equivalence_closure"]
        suffix = (
            "repository_uuidv4" if kind == "repository" else "service_instance_uuidv4"
        )
        assert {(row[suffix], row[f"equivalent_{suffix}"]) for row in closure} == {
            (b, c),
            (c, b),
        }
        assert status["authorities"] == ["core" if kind == "repository" else "context"]
    # Reopen and add a fresh uncancelled A-B assertion: closure becomes transitive.
    fresh = assertion(kind, a, b)
    authority.policy.grants = authority.policy.grants | DependencySet(
        identity_assertions={fresh["relation_uuidv4"]}
    )
    with authority.open(write=True) as service:
        service.admit("relation", fresh, original(fresh))
        assert len(service.status()[f"{kind}_equivalence_closure"]) == 6
    with closing(connect(tmp_path / f"{role}.sqlite3", role)) as db:
        assert {
            row[0] for row in db.execute(f"SELECT {column} FROM {table}")
        } == original_identities
        assert not db.execute(
            "SELECT 1 FROM sqlite_schema WHERE name LIKE '%identity%staging%'"
        ).fetchone()
    assert not (
        tmp_path / ("context.sqlite3" if kind == "repository" else "core.sqlite3")
    ).exists()


@pytest.mark.parametrize("kind", ["repository", "service"])
def test_competing_payloads_and_unresolved_endpoints_remain_evidence(tmp_path, kind):
    a, b, c = [str(uuid4()) for _ in range(3)]
    first = assertion(kind, a, b)
    unresolved = assertion(kind, a, c)
    authority = Authority(
        tmp_path,
        kind,
        {a, b},
        {first["relation_uuidv4"], unresolved["relation_uuidv4"]},
    )
    # The explicit local grant may authorize an as-yet unregistered endpoint.
    authority.policy.grants |= DependencySet(provider_registrations={c})
    with authority.open(write=True) as service:
        service.admit("relation", first, original(first))
        suffix = (
            "repository_uuidv4" if kind == "repository" else "service_instance_uuidv4"
        )
        conflict = {**first, f"right_{suffix}": c}
        assert service.admit("relation", conflict, original(conflict)) == "conflict"
        assert service.admit("relation", unresolved, original(unresolved)) == "accepted"
        status = service.status()
        assert len(status["identity_relations"]) == 3
        assert not status["active_identity_relations"]
        assert len(status["identity_conflicts"]) == 1
        assert status["identity_unresolved"][0]["missing_endpoints"] == [c]
        assert all(
            report["provenance"][0] == "explicit-local-input"
            for report in status["identity_relations"]
        )
        assert not status[f"{kind}_equivalence_closure"]


def test_service_cancellation_requires_exact_target_grant_and_revocation_rolls_back(
    tmp_path,
):
    a, b = str(uuid4()), str(uuid4())
    first = assertion("service", a, b)
    before = cancellation(first)
    authority = Authority(tmp_path, "service", {a, b}, set())
    with pytest.raises(AdmissionRefused, match="PERMISSION_DENIED"):
        with authority.open(write=True) as service:
            service.admit(
                "cancellation", before, original(before), entity_kind="service"
            )
    authority.policy.grants |= DependencySet(
        identity_assertions={first["relation_uuidv4"]}
    )
    with pytest.raises(AdmissionRefused, match="PERMISSION_DENIED"):
        with authority.open(write=True) as service:
            assert (
                service.admit(
                    "cancellation", before, original(before), entity_kind="service"
                )
                == "accepted"
            )
            authority.policy.revoke()
    with authority.open() as service:
        assert not service.status()["identity_relation_cancellations"]


def test_repository_identity_rejects_bad_times_false_verification_and_implicit_service(
    tmp_path,
):
    a, b = str(uuid4()), str(uuid4())
    first = assertion("repository", a, b)
    authority = Authority(tmp_path, "repository", {a, b}, set())
    with authority.open(write=True) as service:
        for stamp in (0, -1, True):
            with pytest.raises((ValueError, TypeError)):
                service.admit(
                    "relation", {**first, "asserted_at_us": stamp}, original(first)
                )
        fake = Provenance(
            "reported-source", "original", "identity", "json", "1", "receiver_intrinsic"
        )
        with pytest.raises(CoreFailure, match="reported provenance"):
            service.admit("relation", first, fake)
        with pytest.raises(CoreFailure, match="owning authority"):
            service.admit("relation", assertion("service", a, b), original(first))
        with pytest.raises(CoreFailure, match="identity authority"):
            service.admit("cancellation", cancellation(first), original(first))
        assert not service.status()["identity_relations"]


@pytest.mark.parametrize("kind", ["repository", "service"])
def test_conflicting_cancellation_id_suppresses_every_reported_target(tmp_path, kind):
    a, b, c = [str(uuid4()) for _ in range(3)]
    first, second = assertion(kind, a, b), assertion(kind, b, c)
    authority = Authority(
        tmp_path, kind, {a, b, c}, {first["relation_uuidv4"], second["relation_uuidv4"]}
    )
    before = cancellation(first)
    alternative = {**before, "relation_uuidv4": second["relation_uuidv4"]}
    with authority.open(write=True) as service:
        service.admit("relation", first, original(first))
        service.admit("relation", second, original(second))
        service.admit("cancellation", before, original(before), entity_kind=kind)
        assert (
            service.admit(
                "cancellation", alternative, original(alternative), entity_kind=kind
            )
            == "conflict"
        )
        status = service.status()
        assert len(status["identity_relation_cancellations"]) == 2
        assert status["identity_conflicts"][0]["kind"] == "cancellation"
        assert not status["active_identity_relations"]
        assert not status[f"{kind}_equivalence_closure"]


@pytest.mark.parametrize("kind", ["repository", "service"])
def test_identity_rows_are_append_only_and_finite_read_refusal_does_not_stop(
    tmp_path, kind
):
    import sqlite3

    a, b = str(uuid4()), str(uuid4())
    first = assertion(kind, a, b)
    before = cancellation(first)
    authority = Authority(tmp_path, kind, {a, b}, {first["relation_uuidv4"]})
    with authority.open(write=True) as service:
        service.admit("relation", first, original(first))
        service.admit("cancellation", before, original(before), entity_kind=kind)
    role = "core" if kind == "repository" else "context"
    with closing(connect(tmp_path / f"{role}.sqlite3", role)) as db:
        for suffix in ("assertions", "cancellations"):
            table = f"{kind}_identity_{suffix}"
            for sql in (
                f"DELETE FROM {table}",
                f"UPDATE {table} SET provenance=provenance",
            ):
                with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                    db.execute(sql)
    with authority.open() as service:
        with pytest.raises(ValueError):
            service.status(max_evidence=1)
        assert len(service.status()["identity_relation_cancellations"]) == 1
    assert not (tmp_path / "p1-recovery-stop.json").exists()
