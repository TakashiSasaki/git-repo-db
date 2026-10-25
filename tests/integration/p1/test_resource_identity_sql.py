"""I1 comparison harness on disposable SQLite databases, not production DDL.

These minimal tables exercise BINARY key equality and compound FK references.
They do not implement generalized Resource storage, known-kind SQL admission,
semantic Parent authority, schema fingerprints, or any later ADR 0031 stage.
Set RESOURCE_IDENTITY_SQL_REPORT to retain actual runtime/settings/case receipts.
"""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.resource_identity import encode_identity, parse_identity

SERVICE = "aad25448-03eb-4f83-a578-ceec84375b5a"
OTHER_SERVICE = "80f5c4f9-6d6b-4691-af3c-00ab02ad9f53"


def _canonical_identity(value):
    """Bounded deterministic SQL predicate; reject SQL NULL/BLOB before parsing."""
    if type(value) is not str:
        return 0
    try:
        parse_identity(value)
    except (TypeError, ValueError):
        return 0
    return 1


DDL = """
CREATE TABLE resources (
    service_instance_uuidv4 TEXT COLLATE BINARY NOT NULL,
    resource_kind TEXT COLLATE BINARY NOT NULL,
    provider_resource_id TEXT COLLATE BINARY NOT NULL
        CHECK(typeof(provider_resource_id) = 'text'
              AND canonical_identity(provider_resource_id) = 1),
    PRIMARY KEY(service_instance_uuidv4, resource_kind, provider_resource_id)
) WITHOUT ROWID;
CREATE TABLE links (
    source_service TEXT COLLATE BINARY NOT NULL,
    source_kind TEXT COLLATE BINARY NOT NULL,
    source_id TEXT COLLATE BINARY NOT NULL,
    target_service TEXT COLLATE BINARY NOT NULL,
    target_kind TEXT COLLATE BINARY NOT NULL,
    target_id TEXT COLLATE BINARY NOT NULL,
    PRIMARY KEY(source_service, source_kind, source_id,
                target_service, target_kind, target_id),
    FOREIGN KEY(source_service, source_kind, source_id)
        REFERENCES resources(service_instance_uuidv4, resource_kind,
                             provider_resource_id),
    FOREIGN KEY(target_service, target_kind, target_id)
        REFERENCES resources(service_instance_uuidv4, resource_kind,
                             provider_resource_id)
) WITHOUT ROWID;
"""


def _write_receipt(db, request):
    report = os.environ.get("RESOURCE_IDENTITY_SQL_REPORT")
    if report is None:
        return
    path = Path(report)
    data = json.loads(path.read_text()) if path.exists() else {"cases": {}}
    data.update(
        scope="I1 disposable BINARY equality/compound FK comparison harness",
        sqlite_version=db.execute("SELECT sqlite_version()").fetchone()[0],
        sqlite_source_id=db.execute("SELECT sqlite_source_id()").fetchone()[0],
        pragmas={
            name: db.execute("PRAGMA " + name).fetchall()
            for name in (
                "foreign_keys",
                "recursive_triggers",
                "encoding",
                "journal_mode",
                "synchronous",
                "trusted_schema",
                "temp_store",
            )
        },
        compile_options=[r[0] for r in db.execute("PRAGMA compile_options")],
    )
    # Pytest/JUnit retains success/failure outcomes; this only records execution.
    data["cases"][request.node.nodeid] = "executed"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


@pytest.fixture
def identity_db(tmp_path, request):
    db = sqlite3.connect(tmp_path / "identity.sqlite3", isolation_level=None)
    db.create_function("canonical_identity", 1, _canonical_identity, deterministic=True)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    db.executescript(DDL)
    assert db.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert db.execute("PRAGMA recursive_triggers").fetchone() == (1,)
    _write_receipt(db, request)
    yield db
    db.close()


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("731", ["731"]),
        ("", []),
        ([""], [[]]),
        (["a", ["b", "c"]], ["a", ["c", "b"]]),
        ("\u00e9", "e\u0301"),
        ("A", "a"),
        (" x", "x"),
        ("x ", "x"),
        ('["project","7"]', ["project", "7"]),
        (["node", "7"], ["database", "7"]),
    ],
    ids=[
        "scalar-array",
        "empty-string-array",
        "nested-empty",
        "nested-order",
        "nfc-nfd",
        "case",
        "leading-space",
        "trailing-space",
        "native-json-looking-string",
        "native-id-namespaces",
    ],
)
def test_binary_key_distinctions(identity_db, left, right):
    db = identity_db
    keys = [
        ResourceKey.from_native(SERVICE, "vendor.resource", v) for v in (left, right)
    ]
    for key in keys:
        db.execute("INSERT INTO resources VALUES(?,?,?)", key.coordinates())
    assert keys[0] != keys[1]
    assert db.execute("SELECT count(*) FROM resources").fetchone() == (2,)
    for key in keys:
        row = db.execute(
            "SELECT * FROM resources WHERE service_instance_uuidv4=? "
            "AND resource_kind=? AND provider_resource_id=?",
            key.coordinates(),
        ).fetchone()
        assert ResourceKey(*row) == key
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        db.execute("INSERT INTO resources VALUES(?,?,?)", keys[0].coordinates())


def test_scoped_document_exact_key_and_compound_fk_roundtrip(identity_db):
    db = identity_db
    parent = ResourceKey.from_native(SERVICE, "pull_request", ["project", "73"])
    document = ResourceKey.document(
        parent, "document", "body", ["thread", "\U0001f600"]
    )
    assert document.provider_resource_id == encode_identity(
        ["pull_request", parent.provider_resource_id, "body", ["thread", "\U0001f600"]]
    )
    parsed = parse_identity(document.provider_resource_id)
    assert parsed[1] == '["project","73"]'
    assert type(parsed[1]) is str
    for key in (parent, document):
        db.execute("INSERT INTO resources VALUES(?,?,?)", key.coordinates())
    db.execute(
        "INSERT INTO links VALUES(?,?,?,?,?,?)",
        (*document.coordinates(), *parent.coordinates()),
    )
    row = db.execute(
        "SELECT * FROM resources WHERE resource_kind='document'"
    ).fetchone()
    assert row == document.coordinates()
    assert ResourceKey(*row).coordinates() == document.coordinates()
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


@pytest.mark.parametrize("coordinate", ["service", "kind", "identity"])
def test_compound_fk_needs_exact_entire_key(identity_db, coordinate):
    db = identity_db
    source = ResourceKey.from_native(SERVICE, "vendor.source", "source")
    first = ResourceKey.from_native(SERVICE, "vendor.alpha", "ID")
    second = ResourceKey.from_native(OTHER_SERVICE, "vendor.beta", "id")
    for key in (source, first, second):
        db.execute("INSERT INTO resources VALUES(?,?,?)", key.coordinates())
    db.execute(
        "INSERT INTO links VALUES(?,?,?,?,?,?)",
        (*source.coordinates(), *first.coordinates()),
    )
    wrong = list(first.coordinates())
    index = {"service": 0, "kind": 1, "identity": 2}[coordinate]
    wrong[index] = second.coordinates()[index]
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        db.execute(
            "INSERT INTO links VALUES(?,?,?,?,?,?)", (*source.coordinates(), *wrong)
        )
    assert db.execute("SELECT count(*) FROM links").fetchone() == (1,)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("column", [0, 1, 2])
def test_resource_key_components_cannot_be_sql_null(identity_db, column):
    coordinates = list(
        ResourceKey.from_native(SERVICE, "vendor.resource", "").coordinates()
    )
    coordinates[column] = None
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
        identity_db.execute("INSERT INTO resources VALUES(?,?,?)", coordinates)
    assert identity_db.execute("SELECT count(*) FROM resources").fetchone() == (0,)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "null",
        "7",
        '["x",null]',
        '"\\u0061"',
        '"\\/"',
        ' "a"',
        '"\u00e9"',
        '\ufeff"a"',
        b'"a"',
        b'"\xff"',
        "",
        '"' + "a" * 262_143 + '"',
        "[" * 33 + "]" * 33,
        "[" + ",".join(['""'] * 4096) + "]",
    ],
    ids=[
        "sql-null",
        "json-null",
        "json-number",
        "nested-null",
        "alternate-escape",
        "escaped-solidus",
        "outer-whitespace",
        "literal-nonascii",
        "bom",
        "blob",
        "invalid-utf8-blob",
        "missing-text",
        "bytes-limit-plus-one",
        "depth-33",
        "nodes-4097",
    ],
)
def test_sql_identity_guard_rejects_noncanonical_and_nontext(identity_db, value):
    db = identity_db
    assert db.execute("SELECT canonical_identity(?)", (value,)).fetchone() == (0,)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO resources VALUES(?,?,?)", (SERVICE, "vendor.resource", value)
        )
    assert db.execute("SELECT count(*) FROM resources").fetchone() == (0,)


def _nested_empty(depth):
    value = []
    for _ in range(depth - 1):
        value = [value]
    return value


@pytest.mark.parametrize(
    "native",
    ["a" * 262_142, "/literal/[]", [], _nested_empty(32), [""] * 4095],
    ids=["bytes-limit", "ordinary-string", "empty-array", "depth-32", "nodes-4096"],
)
def test_sql_identity_guard_preserves_valid_text(identity_db, native):
    db = identity_db
    text = encode_identity(native)
    assert db.execute("SELECT canonical_identity(?)", (text,)).fetchone() == (1,)
    db.execute(
        "INSERT INTO resources VALUES(?,?,?)", (SERVICE, "vendor.resource", text)
    )
    assert db.execute("SELECT provider_resource_id FROM resources").fetchone() == (
        text,
    )
