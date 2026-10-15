"""Receiver checks cannot relabel an earlier source report via callback SQL."""

import hashlib
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.p1_core import Core
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.p1_coordination import AdmissionFailure, PairAdmission
from repo_catalog.domain.p1_core import (
    OID,
    NativeObject,
    Provenance,
    RelationGroup,
    ScalarClaim,
    native_oid,
)


class Budget:
    def require(self, unit, amount=1):
        pass

    def charge(self, unit, amount):
        pass


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
@pytest.mark.parametrize("kind", ["scalar", "group"])
def test_callback_cannot_promote_original_report(tmp_path, object_format, kind):
    repository, instance = str(uuid4()), str(uuid4())
    for store in ("core", "context"):
        initialize(tmp_path / f"{store}.sqlite3", store, repository, instance)
    oid = OID(object_format, native_oid(object_format, "tree", b""))
    native = NativeObject(oid, "tree", b"", 0, hashlib.sha256(b"").hexdigest())
    provenance = Provenance("original", "observation", kind, "source-parser", "1")
    copy = str(uuid4())
    core = Core(tmp_path / "core.sqlite3")
    try:
        if kind == "scalar":
            report = ScalarClaim(oid, "type", "tree", provenance)
            core.admit_claim(report)
            table = "intrinsic_claims"

            def projection():
                return core.scalar(oid, "type")
        else:
            report = RelationGroup(
                oid,
                "tree_entries",
                "original-entire-tree",
                "known_empty",
                (),
                provenance,
            )
            core.admit_group(report)
            table = "intrinsic_groups"

            def projection():
                return core.relations(oid, "tree_entries")

        core.admit_metadata(native, copy, Budget())
        before = projection()
        original = [
            item
            for item in before.alternatives
            if item["provenance"] == list(provenance.key)
        ]
        assert len(original) == 1 and original[0]["checked"] is False
        assert before.canonical is not None

        def promote(tx):
            values = (*report.key, copy)
            tx.execute(
                f"INSERT INTO {table} VALUES({','.join('?' for _ in values)})",
                values,
            )

        with pytest.raises(
            AdmissionFailure, match="outside checked intrinsic scope"
        ) as error:
            PairCoordinator(tmp_path).admit(promote, lambda tx: None)
        assert error.value.outcome == PairAdmission(False, False)
        assert projection() == before
        assert not (tmp_path / "p1-recovery-stop.json").exists()

        # Independently emitted receiver evidence remains valid and replays;
        # rejection changes neither the original report nor the checked value.
        core.admit_metadata(native, copy, Budget())
        assert projection() == before
    finally:
        core.close()
