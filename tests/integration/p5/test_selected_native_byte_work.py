"""Actual allowed native metadata byte authorization/verification scales linearly."""

import hashlib
from contextlib import closing
from uuid import uuid4

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain import p1_core
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.p1_core import OID, NativeObject
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from tests.integration.p5.conftest import init_catalog_stores
from tests.integration.p5.test_selected_exchange_work import measured_export


def native(kind, body):
    header = f"{kind} {len(body)}".encode() + b"\0"
    return NativeObject(
        OID("sha1", hashlib.sha1(header + body).hexdigest()),
        kind,
        body,
        len(body),
        hashlib.sha256(body).hexdigest(),
    )


def test_selected_allowed_native_byte_authorization_and_receiver_work_are_linear(
    tmp_path, monkeypatch
):
    actual = {"visits": 0, "bytes": 0, "copies": 0}
    original_performed = p1_core._performed
    original_copy = GitCore.read_metadata_copy

    def performed(unit, amount):
        if unit == "verification_bytes":
            actual["visits"] += 1
            actual["bytes"] += amount
        return original_performed(unit, amount)

    def read_copy(self, *args, **kwargs):
        actual["copies"] += 1
        return original_copy(self, *args, **kwargs)

    monkeypatch.setattr(p1_core, "_performed", performed)
    monkeypatch.setattr(GitCore, "read_metadata_copy", read_copy)
    measured = []
    for count in (16, 64, 256):
        sender, receiver = (
            tmp_path / str(count) / "sender",
            tmp_path / str(count) / "receiver",
        )
        repository, _ = init_catalog_stores(sender, stores=("core", "operational"))
        tree = native("tree", b"")
        commits = tuple(
            native(
                "commit",
                (
                    f"tree {tree.object_oid.object_oid}\n"
                    "author Author <a@example.test> 1700000000 +0000\n"
                    "committer Author <a@example.test> 1700000000 +0000\n\n"
                    f"selected commit {index:08d}\n"
                ).encode(),
            )
            for index in range(count)
        )
        with closing(GitCore(sender / "core.sqlite3")) as core:
            for value in (tree, *commits):
                core.admit_metadata(value, str(uuid4()), UnlimitedWorkBudget())
        selection = ExchangeSelectionScope(
            include_context=False,
            repository_uuidv4s=(repository,),
            object_oids=tuple(value.object_oid for value in commits),
            resource_keys=(),
            source_uuidv4s=(),
        )
        actual.update(visits=0, bytes=0, copies=0)
        package, sql_steps = measured_export(sender, selection)
        exported = dict(actual)
        body_bytes = sum(len(value.body) for value in commits)
        assert len(package.core["retained_metadata"]) == count + 1
        assert {row["native_type"] for row in package.core["retained_metadata"]} == {
            "commit",
            "tree",
        }
        assert exported["copies"] == count + 1
        assert exported["bytes"] >= 2 * body_bytes
        init_catalog_stores(
            receiver, repository_uuidv4=repository, stores=("core", "operational")
        )
        actual.update(visits=0, bytes=0, copies=0)
        ExchangeService(receiver).import_package(
            package, new_request=True, permitted_repository_uuidv4s=(repository,)
        )
        received = dict(actual)
        assert received["bytes"] >= 2 * body_bytes
        with OperationalAcquisitionLedger(receiver) as ledger:
            usage = ledger.work_ledger.usage(
                RequestIdentity(
                    package.sender_catalog_instance_uuidv4, package.package_id
                )
            )
        assert (
            usage["metadata_units"] > 0
            and usage["verification_bytes"] >= received["bytes"]
        )
        with closing(GitCore(receiver / "core.sqlite3")) as core:
            assert core.scalar(commits[-1].object_oid, "message").canonical == [
                "known",
                f"selected commit {count - 1:08d}\n",
            ]
        measured.append((count, body_bytes, exported, received, sql_steps, usage))
    for small, large in zip(measured, measured[1:]):
        ratio = large[1] / small[1]
        for phase in (2, 3):
            assert large[phase]["visits"] <= small[phase]["visits"] * ratio * 1.25 + 100
            assert large[phase]["bytes"] <= small[phase]["bytes"] * ratio * 1.25 + 1024
        assert large[4] <= small[4] * ratio * 1.4 + 5000
        assert (
            large[5]["metadata_units"]
            <= small[5]["metadata_units"] * ratio * 1.3 + 5000
        )
