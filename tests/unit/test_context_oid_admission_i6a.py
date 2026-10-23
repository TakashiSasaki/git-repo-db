"""OID grants apply to required links and every reported-reference input route."""

import sqlite3
from contextlib import contextmanager

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    DependencySet,
    dependencies,
)
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.production_context import CoreReference, ResourceObservation
from tests.support.context_admission import fixture_context, fixture_service

SERVICE = "aad25448-03eb-4f83-a75e-cb7055fd33be"
REPOSITORY = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
KEY = ResourceKey.from_native(SERVICE, "issue", "7")
OBJECT = OID("sha1", "a" * 40)
PROVENANCE = canonical({"source": "synthetic", "evidence": "original-oid"})


@pytest.fixture
def product_db():
    db = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(db)
    p1_schema.configure(db)
    db.executescript(p1_schema.compose("context"))
    db.execute(
        "INSERT INTO store_identity VALUES('context',?,?)", (REPOSITORY, SERVICE)
    )
    db.execute("INSERT INTO providers VALUES(?,?,?)", (SERVICE, "synthetic", "{}"))
    db.execute(
        "INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id) VALUES(?,?,?)",
        KEY.coordinates(),
    )
    yield db
    db.close()


@pytest.mark.parametrize(
    ("adapter", "route"),
    [
        ("store", "required"),
        ("store", "field"),
        ("facade", "required"),
        ("facade", "reported"),
        ("facade", "field"),
        ("facade", "observation"),
    ],
)
@pytest.mark.parametrize("replay", [False, True])
def test_t08_oid_denial_precedes_lookup_and_replay(
    product_db, tmp_path, adapter, route, replay
):
    service, policy = fixture_service(
        dependencies(KEY) | DependencySet(object_oids={OBJECT})
    )
    admission = fixture_context(service)
    callbacks = []
    candidate = FieldCandidate(
        KEY,
        "reported_core_reference:head",
        canonical(OBJECT.key),
        FieldClock("oid", 3),
        PROVENANCE,
        4,
    )

    @contextmanager
    def transaction():
        if adapter == "facade":
            with Context.owned_transaction(
                product_db, tmp_path, authorization=service, admission=admission
            ) as capability:
                yield capability
        else:
            store = ContextStore(product_db, authorization=service)
            with store.admission_transaction(admission=admission):
                yield store

    def submit(capability):
        if route == "required":
            capability.link_core(
                KEY,
                "head",
                *OBJECT.key,
                PROVENANCE,
                lambda *args: callbacks.append(args) or True,
            )
        elif route == "reported":
            capability.report_core_reference(
                CoreReference(KEY, "head", OBJECT, PROVENANCE),
                clock=candidate.clock,
                observed_at_us=candidate.observed_at_us,
            )
        elif route == "field":
            capability.admit_field(candidate)
        else:
            capability.observe(ResourceObservation(KEY, (candidate,)))

    if replay:
        with transaction() as capability:
            submit(capability)
    policy.denied = DependencySet(object_oids={OBJECT})
    callbacks.clear()
    before = tuple(
        product_db.execute(f"SELECT * FROM {table}").fetchall()
        for table in ("resources", "core_references", "field_candidates")
    )
    with pytest.raises(AdmissionRefused) as error:
        with transaction() as capability:
            submit(capability)
    assert error.value.code == "PERMISSION_DENIED"
    assert not callbacks
    assert not product_db.in_transaction
    assert policy.active == 0
    after = tuple(
        product_db.execute(f"SELECT * FROM {table}").fetchall()
        for table in ("resources", "core_references", "field_candidates")
    )
    assert after == before
