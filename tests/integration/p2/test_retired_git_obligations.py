"""Native identity, partial metadata and provenance obligations on separated Core."""

import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_core import (
    CoreFailure,
    GitObservation,
    Provenance,
    RelationGroup,
    RelationMember,
    ScalarClaim,
)
from tests.integration.p1.test_core import Budget, native, oid, provenance
from tests.integration.p2.test_native import commit_body, entry, git, repository, write
from tests.integration.p5.test_exchange_core_import_independence import catalog

__all__ = ["repository"]


@pytest.mark.parametrize("later_header", ["object", "type"])
def test_later_tag_extensions_preserve_git_initial_identity_and_exact_bytes(
    core, repository, later_header
):
    store, _, _ = core
    path, fmt = repository
    tree = write(path, fmt, "tree", b"")
    first = write(path, fmt, "commit", commit_body(tree.object_oid))
    other = write(
        path, fmt, "commit", commit_body(tree.object_oid, message=b"unrelated target\n")
    )
    extra = (
        b"object " + other.object_oid.object_oid.encode()
        if later_header == "object"
        else b"type blob"
    )
    body = (
        b"object "
        + first.object_oid.object_oid.encode()
        + b"\ntype commit\ntag extensions\ntagger T <t@invalid> 1 +0000\n"
        + extra
        + b"\n\nmessage\n"
    )
    tag = write(path, fmt, "tag", body)
    assert (
        git(path, "rev-parse", tag.object_oid.object_oid + "^{}").strip().decode()
        == first.object_oid.object_oid
    )
    assert git(path, "cat-file", "tag", tag.object_oid.object_oid) == body
    actual = GitNativeSource(path).metadata(tag.object_oid)
    store.admit_metadata(actual, str(uuid4()), Budget())
    assert store.read_metadata(tag.object_oid) == body
    assert store.relations(tag.object_oid, "tag_target").canonical == [
        "complete",
        [[0, *first.object_oid.key]],
    ]
    assert (
        bytes.fromhex(store.scalar(tag.object_oid, "header_data").canonical[1])
        == body.partition(b"\n\n")[0]
    )
    assert {row[0] for row in store.sql("SELECT object_oid FROM git_objects")} == {
        tag.object_oid.object_oid,
        first.object_oid.object_oid,
    }
    assert store.scalar(first.object_oid, "type").canonical is None


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("bad_first", ["object", "type"])
def test_later_valid_tag_extension_cannot_repair_invalid_initial_identity(
    core, fmt, bad_first
):
    store, path, _ = core
    target = oid("a", fmt).object_oid.encode()
    first_object = b"bad" if bad_first == "object" else target
    first_type = b"file" if bad_first == "type" else b"commit"
    body = (
        b"object "
        + first_object
        + b"\ntype "
        + first_type
        + b"\ntag invalid\nobject "
        + target
        + b"\ntype commit\n\nmessage"
    )
    with pytest.raises(CoreFailure) as error:
        store.admit_metadata(native("tag", body, fmt), str(uuid4()), Budget())
    assert error.value.code == "NATIVE_SYNTAX"
    assert store.sql("SELECT count(*) FROM git_objects")[0][0] == 0
    assert store.sql("SELECT count(*) FROM retained_metadata")[0][0] == 0
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize(
    "damage", ["truncated-target", "valid-prefix-trailing-junk", "signed-mode"]
)
def test_exact_legacy_malformed_tree_shapes_leave_no_partial_metadata(
    core, fmt, damage
):
    store, path, _ = core
    raw_target = bytes.fromhex(oid("a", fmt).object_oid)
    body = {
        "truncated-target": b"100644 a\0bad",
        "valid-prefix-trailing-junk": b"100644 a\0" + raw_target + b"invalid",
        "signed-mode": b"+100644 a\0" + raw_target,
    }[damage]
    with pytest.raises(CoreFailure) as error:
        store.admit_metadata(native("tree", body, fmt), str(uuid4()), Budget())
    assert error.value.code == "NATIVE_SYNTAX"
    for table in (
        "git_objects",
        "retained_metadata",
        "scalar_claims",
        "relation_groups",
        "intrinsic_claims",
        "intrinsic_groups",
    ):
        assert store.sql(f"SELECT count(*) FROM {table}")[0][0] == 0
    assert not (path.parent / "p1-recovery-stop.json").exists()
    healthy = native("tree", b"", fmt)
    store.admit_metadata(healthy, str(uuid4()), Budget())
    assert store.read_metadata(healthy.object_oid) == b""


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("kind", ["tree", "commit"])
def test_interruption_after_checked_relation_write_rolls_back_entire_native_unit(
    core, fmt, kind, monkeypatch
):
    store, path, _ = core
    unrelated = native("tree", b"", fmt)
    store.admit_metadata(unrelated, str(uuid4()), Budget())
    target = oid("a", fmt)
    body = (
        b"".join(entry(b"100644", name, target) for name in (b"a", b"b", b"c"))
        if kind == "tree"
        else commit_body(target, (oid("b", fmt), oid("b", fmt)))
    )
    incoming = native(kind, body, fmt)
    tables = (
        "git_objects",
        "scalar_claims",
        "relation_groups",
        "intrinsic_claims",
        "intrinsic_groups",
    )
    before = {
        table: [tuple(row) for row in store.sql(f"SELECT * FROM {table}")]
        for table in tables
    }
    copies = [
        tuple(row)
        for row in store.sql(
            "SELECT object_oid,physical_copy_uuidv4 FROM retained_metadata"
        )
    ]
    original = type(store)._insert
    fired = []

    def interrupt(self, table, values):
        result = original(self, table, values)
        if table == "intrinsic_groups" and not fired:
            fired.append(table)
            raise CoreFailure(
                "CANCELLED", incoming.object_oid, "after actual checked relation write"
            )
        return result

    with monkeypatch.context() as patch:
        patch.setattr(type(store), "_insert", interrupt)
        with pytest.raises(CoreFailure) as error:
            store.admit_metadata(incoming, str(uuid4()), Budget())
        assert error.value.code == "CANCELLED"
    assert fired == ["intrinsic_groups"]
    assert {
        table: [tuple(row) for row in store.sql(f"SELECT * FROM {table}")]
        for table in tables
    } == before
    assert [
        tuple(row)
        for row in store.sql(
            "SELECT object_oid,physical_copy_uuidv4 FROM retained_metadata"
        )
    ] == copies
    assert store.read_metadata(unrelated.object_oid) == unrelated.body
    assert not (path.parent / "p1-recovery-stop.json").exists()
    store.admit_metadata(incoming, str(uuid4()), Budget())
    assert store.read_metadata(incoming.object_oid) == body


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("attack", ["name", "child", "inflated-prefix"])
def test_whole_checked_tree_group_refuses_matching_count_or_prefix_forgery(
    core, fmt, attack
):
    store, path, _ = core
    target, other = oid("a", fmt), oid("b", fmt)
    body = entry(b"100644", b"a", target) + entry(b"100644", b"b", target)
    incoming = native("tree", body, fmt)
    copy = str(uuid4())
    store.admit_metadata(incoming, copy, Budget())
    store.admit_object(other)
    membership = [
        RelationMember(["100644", b"a".hex()], target),
        RelationMember(["100644", b"b".hex()], target),
    ]
    if attack == "name":
        membership[0] = RelationMember(["100644", b"forged".hex()], target)
    elif attack == "child":
        membership[0] = RelationMember(["100644", b"a".hex()], other)
    else:
        membership.pop()
    forged = RelationGroup(
        incoming.object_oid,
        "tree_entries",
        "false-whole-group",
        "complete",
        tuple(membership),
        replace(provenance(), qualification="receiver_intrinsic"),
    )
    expected = store.relations(incoming.object_oid, "tree_entries").canonical
    db = connect(path, "core")
    try:
        db.execute("BEGIN")
        db.execute("INSERT INTO relation_groups VALUES(?,?,?,?,?,?,?)", forged.key)
        with pytest.raises(sqlite3.IntegrityError, match="checked intrinsic scope"):
            db.execute(
                "INSERT INTO intrinsic_groups VALUES(?,?,?,?,?,?,?,?)",
                (*forged.key, copy),
            )
        db.rollback()
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        db.close()
    assert store.relations(incoming.object_oid, "tree_entries").canonical == expected
    assert store.read_metadata(incoming.object_oid) == body
    assert store.scalar(other, "size").canonical is None


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("width", [2, 2048])
def test_one_reported_name_cannot_swallow_multiple_native_tree_entries(
    core, fmt, width
):
    store, path, _ = core
    target = oid("a", fmt)
    entries = [
        entry(b"100644", f"n{index:04}".encode(), target) for index in range(width)
    ]
    incoming = native("tree", b"".join(entries), fmt)
    store.admit_metadata(incoming, str(uuid4()), Budget())
    swallowed = b"".join(entries)[: -len(bytes.fromhex(target.object_oid)) - 1]
    with pytest.raises(CoreFailure) as error:
        RelationGroup(
            incoming.object_oid,
            "tree_entries",
            "swallowed-name",
            "complete",
            (RelationMember(["100644", swallowed.hex()], target),),
            provenance(),
        )
    assert error.value.code == "GROUP"
    canonical = store.relations(incoming.object_oid, "tree_entries").canonical
    assert canonical[0] == "complete" and len(canonical[1]) == width
    assert [bytes.fromhex(member[0][1]) for member in canonical[1]] == [
        f"n{index:04}".encode() for index in range(width)
    ]
    assert store.read_metadata(incoming.object_oid) == incoming.body
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("family", ["author", "name"])
@pytest.mark.parametrize(
    "encoding,errors",
    [
        ("utf-8", "strict"),
        ("utf-8", "replace"),
        ("utf-8", "backslashreplace"),
        ("latin-1", "strict"),
        ("latin-1", "replace"),
        ("latin-1", "backslashreplace"),
    ],
)
def test_independent_decoder_reports_preserve_settings_attribution_without_ranked_winner(
    core, family, encoding, errors
):
    store, _, _ = core
    target = oid()
    raw = (
        b"genuine caf\xc3\xa9"
        if family == "name"
        else b"genuine caf\xc3\xa9 <a@invalid> 1 +0000"
    )
    body = (
        entry(b"100644", raw, target)
        if family == "name"
        else (
            b"tree "
            + target.object_oid.encode()
            + b"\nauthor "
            + raw
            + b"\ncommitter C <c@invalid> 2 +0000\n\nmessage"
        )
    )
    incoming = native("tree" if family == "name" else "commit", body)
    store.admit_metadata(incoming, str(uuid4()), Budget())
    settings = json.dumps(
        {"metadata_encoding": encoding, "metadata_errors": errors},
        sort_keys=True,
        separators=(",", ":"),
    )
    source = Provenance(
        "actual-independent-source",
        "original-observation",
        family + ":" + raw.hex() + ":" + settings,
        "independent.supported.producer",
        "unranked",
    )
    field = "decoded_name" if family == "name" else "author"
    claim = ScalarClaim(
        incoming.object_oid, field, raw.decode(encoding, errors), source
    )
    store.admit_claim(claim)
    store.admit_claim(
        ScalarClaim(incoming.object_oid, "decoder_settings", settings, source)
    )
    before = store.sql("SELECT count(*) FROM scalar_claims")[0][0]
    store.admit_claim(claim)
    assert store.sql("SELECT count(*) FROM scalar_claims")[0][0] == before
    reported = [
        candidate
        for candidate in store.scalar(incoming.object_oid, field).alternatives
        if candidate["provenance"] == list(source.key)
    ]
    assert len(reported) == 1 and reported[0]["checked"] is False
    assert reported[0]["value"] == ["known", raw.decode(encoding, errors)]
    settings_reports = store.scalar(
        incoming.object_oid, "decoder_settings"
    ).alternatives
    assert any(
        candidate["provenance"] == list(source.key)
        and candidate["value"] == ["known", settings]
        for candidate in settings_reports
    )
    if family == "author":
        assert store.scalar(incoming.object_oid, "author").canonical == [
            "known",
            raw.decode("utf-8", "surrogateescape"),
        ]
    else:
        assert store.scalar(incoming.object_oid, "decoded_name").canonical is None
        assert store.relations(incoming.object_oid, "tree_entries").canonical == [
            "complete",
            [[["100644", raw.hex()], *target.key]],
        ]
    assert store.read_metadata(incoming.object_oid) == body


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_reanalysis_replays_exact_metadata_without_new_capture_or_git_access(
    core, fmt, monkeypatch
):
    store, path, repository_uuid = core
    store.admit_repository(repository_uuid)
    target = oid("a", fmt)
    incoming = native(
        "commit", commit_body(target, (oid("b", fmt), oid("c", fmt))), fmt
    )
    observation = GitObservation(
        str(uuid4()),
        str(uuid4()),
        repository_uuid,
        "snapshot",
        ("original selected scope",),
        {"roots": [incoming.object_oid.key], "predecessor": None, "observed_at_us": 10},
        provenance("real acquisition"),
    )
    store.admit_observation(observation)
    copy = str(uuid4())
    store.admit_metadata(incoming, copy, Budget())
    tables = (
        "git_objects",
        "git_observations",
        "scalar_claims",
        "relation_groups",
        "intrinsic_claims",
        "intrinsic_groups",
    )
    before = {
        table: [tuple(row) for row in store.sql(f"SELECT * FROM {table}")]
        for table in tables
    }
    copies = [
        tuple(row)
        for row in store.sql(
            "SELECT object_oid,physical_copy_uuidv4 FROM retained_metadata"
        )
    ]

    def forbidden_git(*args, **kwargs):
        raise AssertionError("retained metadata reanalysis must not contact Git")

    monkeypatch.setattr("subprocess.run", forbidden_git)
    monkeypatch.setattr("subprocess.Popen", forbidden_git)
    retained = store.read_metadata(incoming.object_oid)
    parsed = parse_metadata(fmt, "commit", retained)
    assert parsed.relations["commit_parents"] == [
        [0, *oid("b", fmt).key],
        [1, *oid("c", fmt).key],
    ]
    store.admit_metadata(native("commit", retained, fmt), copy, Budget())
    assert {
        table: [tuple(row) for row in store.sql(f"SELECT * FROM {table}")]
        for table in tables
    } == before
    assert [
        tuple(row)
        for row in store.sql(
            "SELECT object_oid,physical_copy_uuidv4 FROM retained_metadata"
        )
    ] == copies
    assert tuple(store.sql("SELECT * FROM git_observations")[0]) == observation.key
    assert not (path.parent / "context.sqlite3").exists()
    assert not (path.parent / "search.sqlite3").exists()
    assert store.scalar(target, "size").canonical is None


@pytest.mark.parametrize("terminal_kind", ["blob", "tree", "commit"])
def test_nested_tags_survive_onward_partial_and_late_metadata_delivery(
    core, repository, tmp_path, terminal_kind
):
    from contextlib import closing

    store, core_path, repository_uuid = core
    git_path, fmt = repository
    tree = write(git_path, fmt, "tree", b"")
    terminal_body = (
        b"tree "
        + tree.object_oid.object_oid.encode()
        + b"\nauthor A <a@invalid> 1 +0000\ncommitter C <c@invalid> 2 +0000\n\nterminal commit\n"
        if terminal_kind == "commit"
        else b"excluded ordinary file"
    )
    terminal = (
        tree
        if terminal_kind == "tree"
        else write(
            git_path,
            fmt,
            terminal_kind,
            terminal_body,
        )
    )
    target, target_type = terminal.object_oid, terminal_kind
    tags = []
    for number in range(3):
        body = (
            b"object "
            + target.object_oid.encode()
            + b"\ntype "
            + target_type.encode()
            + b"\ntag nested-"
            + str(number).encode()
            + b"\ntagger T <t@invalid> 1 +0000\n\nexact tag message\n"
        )
        incoming = write(git_path, fmt, "tag", body)
        tags.append(incoming)
        target, target_type = incoming.object_oid, "tag"
    assert (
        git(git_path, "rev-parse", tags[-1].object_oid.object_oid + "^{}")
        .strip()
        .decode()
        == terminal.object_oid.object_oid
    )
    store.admit_repository(repository_uuid)
    source = GitNativeSource(git_path)
    store.admit_metadata(source.metadata(tags[-1].object_oid), str(uuid4()), Budget())
    selection = ExchangeSelectionScope(all_selected=True, include_context=False)
    source_service = ExchangeService(core_path.parent)
    first = source_service.export_package(selection=selection, exported_at_us=10)
    receiver_path, onward_path = tmp_path / "receiver", tmp_path / "onward"
    for destination in (receiver_path, onward_path):
        catalog(destination, repository_uuid, str(uuid4()), operational=True)
    receiver = ExchangeService(receiver_path)
    assert receiver.import_package(
        first, new_request=True, permitted_repository_uuidv4s=(repository_uuid,)
    ).core_imported
    partial = receiver.export_package(selection=selection, exported_at_us=11)
    onward = ExchangeService(onward_path)
    assert onward.import_package(
        partial, new_request=True, permitted_repository_uuidv4s=(repository_uuid,)
    ).core_imported
    for destination in (receiver_path, onward_path):
        with closing(GitCore(destination / "core.sqlite3")) as saved:
            assert saved.read_metadata(tags[-1].object_oid) == tags[-1].body
            assert saved.relations(tags[-1].object_oid, "tag_target").canonical == [
                "complete",
                [[0, *tags[-2].object_oid.key]],
            ]
            assert saved.relations(tags[-2].object_oid, "tag_target").canonical is None
            with pytest.raises(CoreFailure) as unavailable:
                saved.read_metadata(tags[-2].object_oid)
            assert unavailable.value.code == "BYTES_UNAVAILABLE"
            assert saved.sql("SELECT count(*) FROM retained_metadata")[0][0] == 1
    for incoming in tags[:-1]:
        store.admit_metadata(
            source.metadata(incoming.object_oid), str(uuid4()), Budget()
        )
    if terminal_kind != "blob":
        store.admit_metadata(
            source.metadata(terminal.object_oid), str(uuid4()), Budget()
        )
    late = source_service.export_package(selection=selection, exported_at_us=12)
    for service, destination in ((receiver, receiver_path), (onward, onward_path)):
        assert service.import_package(
            late, new_request=True, permitted_repository_uuidv4s=(repository_uuid,)
        ).core_imported
        with closing(GitCore(destination / "core.sqlite3")) as saved:
            for number, incoming in enumerate(tags):
                expected = (
                    terminal.object_oid if number == 0 else tags[number - 1].object_oid
                )
                assert saved.read_metadata(incoming.object_oid) == incoming.body
                assert saved.relations(incoming.object_oid, "tag_target").canonical == [
                    "complete",
                    [[0, *expected.key]],
                ]
            assert saved.sql("SELECT count(*) FROM retained_metadata")[0][0] == (
                3 if terminal_kind == "blob" else 4
            )
            if terminal_kind == "blob":
                with pytest.raises(CoreFailure) as unavailable:
                    saved.read_metadata(terminal.object_oid)
                assert unavailable.value.code == "BYTES_UNAVAILABLE"
            else:
                assert saved.read_metadata(terminal.object_oid) == terminal.body
        assert not (destination / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("terminal_kind", ["blob", "tree", "commit"])
def test_native_ref_terminal_peel_is_bounded_pinned_to_enumerated_oid_and_metered(
    repository, terminal_kind, monkeypatch
):
    from repo_catalog.adapters.git.notes import GitNotesSource

    path, fmt = repository
    tree = write(path, fmt, "tree", b"")
    terminal = (
        tree
        if terminal_kind == "tree"
        else write(
            path,
            fmt,
            terminal_kind,
            b"ordinary terminal bytes"
            if terminal_kind == "blob"
            else commit_body(tree.object_oid),
        )
    )
    other = write(path, fmt, "blob", b"new ref target after enumeration")
    target, kind = terminal.object_oid, terminal_kind
    for number in range(3):
        tag = write(
            path,
            fmt,
            "tag",
            f"object {target.object_oid}\ntype {kind}\ntag depth-{number}\ntagger T <t@invalid> 1 +0000\n\nmessage\n".encode(),
        )
        target, kind = tag.object_oid, "tag"
    git(path, "update-ref", "refs/tags/nested", target.object_oid)
    git(path, "update-ref", "refs/tags/lightweight", terminal.object_oid.object_oid)
    source = GitNativeSource(path)
    actual_output = GitNotesSource._output
    commands, received = [], []

    def output(self, args, cap, work, **kwargs):
        value = actual_output(self, args, cap, work, **kwargs)
        commands.append(args)
        received.append(value)
        if args[0] == "for-each-ref":
            git(path, "update-ref", "refs/tags/nested", other.object_oid.object_oid)
        return value

    work = Budget()
    monkeypatch.setattr(GitNotesSource, "_output", output)
    records = source.ref_records(work)
    by_name = {record.name: record for record in records}
    assert by_name[b"refs/tags/nested"].target == target
    assert by_name[b"refs/tags/nested"].peeled == terminal.object_oid
    assert by_name[b"refs/tags/lightweight"].peeled is None
    assert (
        git(path, "rev-parse", "refs/tags/nested^{}").strip().decode()
        == other.object_oid.object_oid
    )
    assert commands[1] == ("rev-parse", "--verify", target.object_oid + "^{}")
    assert work.counts["metadata_units"] == len(commands) + len(records)
    assert work.counts["input_bytes"] == sum(map(len, received))
    assert len(commands) == 2


def test_native_ref_peel_budget_refuses_before_process_and_can_retry(
    repository, monkeypatch
):
    import subprocess

    path, fmt = repository
    tree = write(path, fmt, "tree", b"")
    inner = write(
        path,
        fmt,
        "tag",
        f"object {tree.object_oid.object_oid}\ntype tree\ntag inner\ntagger T <t@invalid> 1 +0000\n\nmessage\n".encode(),
    )
    outer = write(
        path,
        fmt,
        "tag",
        f"object {inner.object_oid.object_oid}\ntype tag\ntag outer\ntagger T <t@invalid> 1 +0000\n\nmessage\n".encode(),
    )
    git(path, "update-ref", "refs/tags/nested", outer.object_oid.object_oid)
    source = GitNativeSource(path)
    actual_popen = subprocess.Popen
    commands = []

    def popen(args, **kwargs):
        commands.append(args)
        return actual_popen(args, **kwargs)

    class Finite(Budget):
        def __init__(self, metadata_units):
            super().__init__()
            self.caps = {"metadata_units": metadata_units, "input_bytes": 1024 * 1024}

        def require(self, unit, amount=1):
            super().require(unit, amount)
            if self.counts.get(unit, 0) + amount > self.caps[unit]:
                raise CoreFailure("BUDGET", unit, "finite ref test work cap")

    monkeypatch.setattr(subprocess, "Popen", popen)
    stopped = Finite(2)
    with pytest.raises(CoreFailure) as error:
        source.ref_records(stopped)
    assert error.value.code == "BUDGET"
    assert len(commands) == 1 and "for-each-ref" in commands[0]
    assert stopped.counts["metadata_units"] == 2
    assert stopped.counts["input_bytes"] > 0
    records = source.ref_records(Finite(10))
    assert len(records) == 1
    assert (
        records[0].target == outer.object_oid and records[0].peeled == tree.object_oid
    )
    assert len(commands) == 3 and "rev-parse" in commands[-1]


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_explicit_authority_validation_detects_typed_byte_contradiction_and_preserves_source(
    core, fmt, tmp_path
):
    from repo_catalog.adapters.sqlite.core_recovery import CoreRecoveryAdapter
    from repo_catalog.adapters.sqlite.core_recovery_validation import (
        validate_stored_admission_guards,
        validate_stored_checks,
    )
    from repo_catalog.domain.p1_core import claim_value
    from repo_catalog.domain.recovery import (
        BackupScope,
        BackupValidationError,
        CorruptionDetectedError,
    )

    store, path, _ = core
    incoming = native("commit", commit_body(oid("a", fmt)), fmt)
    store.admit_metadata(incoming, str(uuid4()), Budget())
    statements = []
    store._db.set_trace_callback(statements.append)
    try:
        assert store.scalar(incoming.object_oid, "message").canonical == [
            "known",
            "message\n",
        ]
    finally:
        store._db.set_trace_callback(None)
    assert not any("retained_metadata" in statement.lower() for statement in statements)

    # Disposable privileged damage changes matching typed source/evidence keys,
    # leaving CHECKs, FK endpoints, retained bytes and restored guards intact.
    forged = claim_value("message", "typed but byte-contradictory message")
    db = connect(path, "core")
    try:
        names = (
            "p1_immutable_scalar_claims_update",
            "p1_immutable_intrinsic_claims_update",
        )
        guards = [
            db.execute(
                "SELECT sql FROM sqlite_schema WHERE name=?", (name,)
            ).fetchone()[0]
            for name in names
        ]
        db.execute("PRAGMA foreign_keys=OFF")
        for name in names:
            db.execute(f'DROP TRIGGER "{name}"')
        for table in ("scalar_claims", "intrinsic_claims"):
            db.execute(
                f"UPDATE {table} SET value=? WHERE object_format=? AND object_oid=? AND field='message'",
                (forged, *incoming.object_oid.key),
            )
        for guard in guards:
            db.execute(guard)
        db.execute("PRAGMA foreign_keys=ON")
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        before = {
            table: [tuple(row) for row in db.execute(f"SELECT * FROM {table}")]
            for table in ("retained_metadata", "scalar_claims", "intrinsic_claims")
        }
        validate_stored_checks(db, "core", retained_bytes=False)
        validate_stored_checks(db, "core", retained_bytes=True)
        with pytest.raises(BackupValidationError, match="intrinsic_claim_guard"):
            validate_stored_admission_guards(db, "core")
    finally:
        db.close()
    destination = tmp_path / "must-not-publish-backup"
    with pytest.raises(CorruptionDetectedError, match="intrinsic_claim_guard"):
        CoreRecoveryAdapter().create_consistent_backup(
            path.parent, destination, BackupScope.GIT_ONLY
        )
    assert (path.parent / "p1-recovery-stop.json").exists()
    assert not destination.exists()
    with pytest.raises(CoreFailure) as stopped:
        store.scalar(incoming.object_oid, "message")
    assert stopped.value.code == "RECOVERY_STOP"
    diagnostic = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        after = {
            table: [tuple(row) for row in diagnostic.execute(f"SELECT * FROM {table}")]
            for table in before
        }
        assert after == before
        assert after["retained_metadata"][0][4] == incoming.body
    finally:
        diagnostic.close()


def reparse_fixture(core, incoming):
    from repo_catalog.adapters.sqlite.p1_schema import initialize
    from repo_catalog.domain.git_acquisition import GitMetadataInput

    store, path, repository_uuid = core
    store.admit_repository(repository_uuid)
    store.admit_metadata(incoming, str(uuid4()), Budget())
    instance = store.sql("SELECT catalog_instance_uuidv4 FROM store_identity")[0][0]
    initialize(
        path.parent / "operational.sqlite3", "operational", repository_uuid, instance
    )
    unit = GitMetadataInput(
        repository_uuid,
        str(uuid4()),
        str(uuid4()),
        "actual-independent-source",
        10,
        incoming.object_oid.object_format,
    )
    return store, path, unit


@pytest.mark.parametrize("family", ["author", "name"])
@pytest.mark.parametrize(
    "encoding,errors",
    [
        ("utf-8", "strict"),
        ("utf-8", "replace"),
        ("utf-8", "backslashreplace"),
        ("latin-1", "strict"),
        ("latin-1", "replace"),
        ("latin-1", "backslashreplace"),
    ],
)
def test_actual_reparse_preserves_supported_settings_and_original_producer(
    core, family, encoding, errors
):
    from repo_catalog.application.git_history_query import GitHistoryQuery
    from repo_catalog.application.metadata_reparse import reparse
    from repo_catalog.domain.git_native import DECODER, DECODER_VERSION
    from repo_catalog.domain.p1_coordination import RequestIdentity
    from repo_catalog.domain.p1_core import encode

    target = oid()
    raw = (
        b"caf\xc3\xa9.txt"
        if family == "name"
        else b"genuine caf\xc3\xa9 <a@invalid> 1 +0000"
    )
    body = (
        entry(b"100644", raw, target) + entry(b"100644", b"other.txt", target)
        if family == "name"
        else b"tree "
        + target.object_oid.encode()
        + b"\nauthor "
        + raw
        + b"\ncommitter C <c@invalid> 2 +0000\n\nmessage"
    )
    incoming = native("tree" if family == "name" else "commit", body)
    store, path, unit = reparse_fixture(core, incoming)
    settings = {
        "text_encoding": "utf-8",
        "errors": "surrogateescape",
        "metadata_encoding": encoding,
        "metadata_errors": errors,
    }
    request = RequestIdentity(str(uuid4()), str(uuid4()))
    reparse(
        path.parent,
        unit,
        (incoming.object_oid,),
        request=request,
        new_request=True,
        metadata_encoding=encoding,
        metadata_errors=errors,
    )
    field = "decoded_name" if family == "name" else "author"
    coordinate = (
        encode(["reparse-tree-entry", raw.hex()])
        if family == "name"
        else "reparse-author"
    )
    expected = [
        unit.source_attribution,
        encode(
            [unit.capture_origin_uuidv4, unit.capture_uuidv4, *incoming.object_oid.key]
        ),
        coordinate,
        DECODER,
        DECODER_VERSION + ":" + encode(settings),
        "reported",
    ]
    reported = [
        candidate
        for candidate in store.scalar(incoming.object_oid, field).alternatives
        if candidate["provenance"] == expected
    ]
    assert len(reported) == 1 and reported[0]["checked"] is False
    assert reported[0]["value"] == ["known", raw.decode(encoding, errors)]
    before = store.sql("SELECT count(*) FROM scalar_claims")[0][0]
    reparse(
        path.parent,
        unit,
        (incoming.object_oid,),
        request=request,
        metadata_encoding=encoding,
        metadata_errors=errors,
    )
    assert store.sql("SELECT count(*) FROM scalar_claims")[0][0] == before
    assert store.read_metadata(incoming.object_oid) == body
    if family == "name":
        items = {
            item["path"]: item
            for item in GitHistoryQuery(path.parent).tree(incoming.object_oid)["items"]
        }
        assert items[raw]["decoded_name"] == raw.decode(encoding, errors)
        assert not items[raw]["decoder_conflict"]
        assert items[raw]["decoded_name_candidates"] == [
            {
                "decoded_name": raw.decode(encoding, errors),
                "decoder_settings": settings,
                "provenance": expected,
                "qualification": "reported",
            }
        ]
        assert items[b"other.txt"]["decoded_name"] == "other.txt"
        assert (
            items[b"other.txt"]["decoded_name_candidates"][0]["provenance"][2]
            != coordinate
        )
        assert all(
            item["qualification"] == "receiver_intrinsic" for item in items.values()
        )
    else:
        assert store.scalar(incoming.object_oid, "author").canonical == [
            "known",
            raw.decode("utf-8", "surrogateescape"),
        ]


@pytest.mark.parametrize(
    "raw,conflicting",
    [(b"\xff.txt", True), (b"ascii.txt", False), (b"caf\xc3\xa9.txt", True)],
    ids=["different-values", "same-values", "utf8-different-values"],
)
def test_actual_tree_decoder_alternatives_remain_entry_specific_without_a_winner(
    core, raw, conflicting
):
    from repo_catalog.application.git_history_query import GitHistoryQuery
    from repo_catalog.application.metadata_reparse import reparse
    from repo_catalog.domain.p1_coordination import RequestIdentity

    target = oid()
    body = b"".join(
        entry(b"100644", name, target) for name in sorted([raw, b"other.txt"])
    )
    incoming = native("tree", body)
    store, path, unit = reparse_fixture(core, incoming)
    original_group = store.relations(incoming.object_oid, "tree_entries").canonical
    for encoding, errors in [("utf-8", "backslashreplace"), ("latin-1", "strict")]:
        reparse(
            path.parent,
            unit,
            (incoming.object_oid,),
            request=RequestIdentity(str(uuid4()), str(uuid4())),
            new_request=True,
            metadata_encoding=encoding,
            metadata_errors=errors,
        )
    items = {
        item["path"]: item
        for item in GitHistoryQuery(path.parent).tree(incoming.object_oid)["items"]
    }
    candidates = items[raw]["decoded_name_candidates"]
    assert len(candidates) == 2
    assert {candidate["decoded_name"] for candidate in candidates} == {
        raw.decode("utf-8", "backslashreplace"),
        raw.decode("latin-1", "strict"),
    }
    assert items[raw]["decoder_conflict"] is conflicting
    assert items[raw]["decoded_name"] == (None if conflicting else "ascii.txt")
    assert {candidate["qualification"] for candidate in candidates} == {"reported"}
    assert len({tuple(candidate["provenance"]) for candidate in candidates}) == 2
    assert items[b"other.txt"]["decoded_name"] == "other.txt"
    assert not items[b"other.txt"]["decoder_conflict"]
    assert all(
        candidate["decoded_name"] == "other.txt"
        for candidate in items[b"other.txt"]["decoded_name_candidates"]
    )
    assert (
        store.relations(incoming.object_oid, "tree_entries").canonical == original_group
    )
    assert store.read_metadata(incoming.object_oid) == body


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("invalid_part", ["header", "message", "name"])
def test_strict_reparse_failure_preserves_native_authority_and_charges_failed_decode(
    core, fmt, invalid_part
):
    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
    from repo_catalog.application.metadata_reparse import reparse
    from repo_catalog.domain.p1_coordination import RequestIdentity

    target = oid("a", fmt)
    if invalid_part == "name":
        incoming = native("tree", entry(b"100644", b"\xff.txt", target), fmt)
    else:
        author = (
            b"A\xff <a@invalid> 1 +0000"
            if invalid_part == "header"
            else b"A <a@invalid> 1 +0000"
        )
        message = b"\xff" if invalid_part == "message" else b"message"
        incoming = native(
            "commit",
            b"tree "
            + target.object_oid.encode()
            + b"\nauthor "
            + author
            + b"\ncommitter C <c@invalid> 2 +0000\n\n"
            + message,
            fmt,
        )
    store, path, unit = reparse_fixture(core, incoming)
    tables = (
        "git_objects",
        "git_observations",
        "scalar_claims",
        "intrinsic_claims",
        "relation_groups",
        "intrinsic_groups",
    )
    before = {
        table: [tuple(row) for row in store.sql(f"SELECT * FROM {table}")]
        for table in tables
    }
    request = RequestIdentity(str(uuid4()), str(uuid4()))
    with pytest.raises(CoreFailure) as error:
        reparse(
            path.parent,
            unit,
            (incoming.object_oid,),
            request=request,
            new_request=True,
            errors="strict",
            metadata_errors="strict",
        )
    assert error.value.code == "PARSER_DECODE"
    assert isinstance(error.value.__cause__, UnicodeDecodeError)
    assert {
        table: [tuple(row) for row in store.sql(f"SELECT * FROM {table}")]
        for table in tables
    } == before
    assert store.read_metadata(incoming.object_oid) == incoming.body
    assert not (path.parent / "p1-recovery-stop.json").exists()
    with OperationalAcquisitionLedger(path.parent) as ledger:
        failed_usage = ledger.work_ledger.usage(request)
    assert failed_usage["verification_bytes"] > 0 and failed_usage["input_bytes"] > 0
    reparse(
        path.parent,
        unit,
        (incoming.object_oid,),
        request=RequestIdentity(str(uuid4()), str(uuid4())),
        new_request=True,
        errors="replace",
        metadata_errors="replace",
    )
    with OperationalAcquisitionLedger(path.parent) as ledger:
        assert ledger.work_ledger.usage(request) == failed_usage
    assert store.read_metadata(incoming.object_oid) == incoming.body


@pytest.mark.parametrize(
    "false_first", [True, False], ids=["false-first", "real-first"]
)
def test_tree_query_refuses_fabricated_decoding_but_keeps_qualified_original_report(
    core, false_first
):
    from repo_catalog.application.git_history_query import GitHistoryQuery
    from repo_catalog.application.metadata_reparse import reparse
    from repo_catalog.domain.p1_coordination import RequestIdentity
    from repo_catalog.domain.p1_core import encode

    raw = b"caf\xc3\xa9.txt"
    incoming = native("tree", entry(b"100644", raw, oid()))
    store, path, unit = reparse_fixture(core, incoming)
    original = store.relations(incoming.object_oid, "tree_entries").canonical
    source = Provenance(
        "unverified-original-source",
        "original-observation",
        encode(["reparse-tree-entry", raw.hex()]),
        "independent.producer",
        "unranked",
    )
    settings = encode(
        {
            "text_encoding": "utf-8",
            "errors": "surrogateescape",
            "metadata_encoding": "utf-8",
            "metadata_errors": "backslashreplace",
        }
    )

    def legitimate():
        reparse(
            path.parent,
            unit,
            (incoming.object_oid,),
            request=RequestIdentity(str(uuid4()), str(uuid4())),
            new_request=True,
        )

    if not false_first:
        legitimate()
    for field, value in [
        ("raw_name_hex", raw.hex()),
        ("decoded_name", "fabricated-name"),
        ("decoder_settings", settings),
    ]:
        store.admit_claim(ScalarClaim(incoming.object_oid, field, value, source))
    if false_first:
        legitimate()
    result = GitHistoryQuery(path.parent).tree(incoming.object_oid)["items"][0]
    assert result["path"] == raw and result["qualification"] == "receiver_intrinsic"
    assert result["decoded_name"] == "caf\u00e9.txt" and not result["decoder_conflict"]
    assert len(result["decoded_name_candidates"]) == 1
    assert (
        result["decoded_name_candidates"][0]["provenance"][0] == unit.source_attribution
    )
    reports = store.scalar(incoming.object_oid, "decoded_name")
    assert reports.reported_conflict
    assert any(
        candidate["provenance"] == list(source.key)
        and candidate["value"] == ["known", "fabricated-name"]
        and not candidate["checked"]
        for candidate in reports.alternatives
    )
    assert store.relations(incoming.object_oid, "tree_entries").canonical == original
    assert store.read_metadata(incoming.object_oid) == incoming.body


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_large_tree_decoder_processing_reads_one_copy_and_query_does_not_rehydrate(
    core, fmt, monkeypatch
):
    from repo_catalog.application.git_history_query import GitHistoryQuery
    from repo_catalog.application.metadata_reparse import reparse
    from repo_catalog.domain.p1_coordination import RequestIdentity

    width = 2048
    target = oid("a", fmt)
    names = [f"entry-{number:05}".encode() for number in range(width)]
    incoming = native(
        "tree", b"".join(entry(b"100644", name, target) for name in names), fmt
    )
    store, path, unit = reparse_fixture(core, incoming)
    # CoreQueryService.open_snapshot binds the production GitCore reader.
    original = GitCore.read_metadata_copy
    copies = []

    def read_copy(self, subject, *args, **kwargs):
        copies.append(subject.key)
        return original(self, subject, *args, **kwargs)

    monkeypatch.setattr(GitCore, "read_metadata_copy", read_copy)
    reparse(
        path.parent,
        unit,
        (incoming.object_oid,),
        request=RequestIdentity(str(uuid4()), str(uuid4())),
        new_request=True,
    )
    assert copies == [incoming.object_oid.key]
    result = GitHistoryQuery(path.parent).tree(incoming.object_oid, max_entries=width)
    assert not result["limited"] and len(result["items"]) == width
    assert [item["path"] for item in result["items"]] == names
    assert all(
        item["decoded_name"] == name.decode()
        and len(item["decoded_name_candidates"]) == 1
        for item, name in zip(result["items"], names, strict=True)
    )
    assert copies == [incoming.object_oid.key]
    assert store.sql("SELECT count(*) FROM retained_metadata")[0][0] == 1


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_absent_native_child_stays_nominal_until_matching_real_bytes_are_acquired(
    core, fmt
):
    import hashlib

    store, path, _ = core
    child = native("tree", b"", fmt)
    parent = native("commit", commit_body(child.object_oid), fmt)
    store.admit_metadata(parent, str(uuid4()), Budget())
    store.admit_claim(
        ScalarClaim(
            child.object_oid, "type", "tree", provenance("external type report")
        )
    )
    original = store.relations(parent.object_oid, "commit_tree").canonical
    assert original == ["complete", [[0, *child.object_oid.key]]]
    assert store.scalar(child.object_oid, "type").canonical is None
    with pytest.raises(CoreFailure) as unavailable:
        store.read_metadata(child.object_oid)
    assert unavailable.value.code == "BYTES_UNAVAILABLE"
    forged = replace(
        child,
        body=b"fake",
        declared_size=4,
        digest_sha256=hashlib.sha256(b"fake").hexdigest(),
    )
    with pytest.raises(CoreFailure) as mismatch:
        store.admit_metadata(forged, str(uuid4()), Budget())
    assert mismatch.value.code == "NATIVE_INTEGRITY"
    assert store.sql("SELECT count(*) FROM retained_metadata")[0][0] == 1
    assert store.scalar(child.object_oid, "type").canonical is None
    assert not (path.parent / "p1-recovery-stop.json").exists()
    store.admit_metadata(child, str(uuid4()), Budget())
    assert store.read_metadata(child.object_oid) == b""
    assert store.scalar(child.object_oid, "type").canonical == ["known", "tree"]
    assert any(
        candidate["checked"] is False
        for candidate in store.scalar(child.object_oid, "type").alternatives
    )
    assert store.relations(parent.object_oid, "commit_tree").canonical == original
    assert store.sql("SELECT count(*) FROM retained_metadata")[0][0] == 2
