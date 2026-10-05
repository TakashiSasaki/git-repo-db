import copy
import json
import sqlite3
import struct

import pytest

from scripts.schema_contract import ROOT, archive_bytes, scalar, validate


def test_contract_matches_constructed_target_and_all_source_columns():
    contract, target = validate()
    assert len(contract["source_columns"]) == 287
    assert len(target) == 74
    assert all(
        r["archive"]["value_column"] == "value_bytes"
        for r in contract["source_columns"]
    )
    assert all(p.get("recipe") or p.get("factory") for p in contract["productions"])


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("missing_source", "source column"),
        ("missing_target", "target table"),
        ("missing_required", "reverse coverage"),
        ("undefined_rule", "transform rule"),
        ("undefined_dependency", "dependency"),
        ("broken_archive", "archive"),
        ("null_required", "Required target"),
        ("wrong_type", "Output type"),
        ("bad_input", "source input"),
        ("cycle", "dependency cycle"),
        ("ddl_hash", "DDL hash"),
        ("undefined_validation", "validation"),
        ("bad_destination", "destination"),
    ],
)
def test_invalid_conversion_contract_is_rejected(mutation, error):
    c = copy.deepcopy(json.loads((ROOT / "conversion-contract.json").read_text()))
    p = next(p for p in c["productions"] if p["target"] == "repositories")
    e = p["outputs"]["name"]
    if mutation == "missing_source":
        c["source_columns"].pop()
    if mutation == "missing_target":
        p["target"] = "nonexistent"
    if mutation == "missing_required":
        p["outputs"].pop("name")
    if mutation == "undefined_rule":
        e["rule"] = "undefined"
    if mutation == "undefined_dependency":
        p["dependencies"] = ["not-defined"]
    if mutation == "broken_archive":
        c["source_columns"][0]["archive"]["value_column"] = "nowhere"
    if mutation == "null_required":
        e.update(rule="null", inputs=[])
    if mutation == "wrong_type":
        e["type"] = "BLOB"
    if mutation == "bad_input":
        e["inputs"] = ["source.repositories.nonexistent"]
    if mutation == "cycle":
        p["dependencies"] = ["repositories"]
    if mutation == "ddl_hash":
        c["ddl_sha256"] = "0" * 64
    if mutation == "undefined_validation":
        c["source_columns"][0]["validation"] = ["not-defined"]
    if mutation == "bad_destination":
        c["source_columns"][0]["outputs"] = [
            {"production": "repositories", "column": "no-field"}
        ]
    with pytest.raises(ValueError, match=error):
        validate(c)


def test_typed_archive_preserves_sqlite_storage_and_exact_bytes():
    # Invalid UTF-8 TEXT is archived through CAST AS BLOB without Python decoding.
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE source(value)")
    for sql, params in [
        ("INSERT INTO source VALUES(NULL)", ()),
        ("INSERT INTO source VALUES(?)", (123,)),
        ("INSERT INTO source VALUES(?)", (1.25,)),
        ("INSERT INTO source VALUES(CAST(x'ff0041' AS TEXT))", ()),
        ("INSERT INTO source VALUES(?)", (b"\xff\x00A",)),
    ]:
        db.execute(sql, params)
    archived = []
    for kind, value, raw in db.execute(
        "SELECT typeof(value), CASE WHEN typeof(value) IN ('integer','real') THEN value END, CAST(value AS BLOB) FROM source"
    ):
        archived.append(
            (kind, archive_bytes(kind, value if kind in ("integer", "real") else raw))
        )
    assert archived == [
        ("null", b""),
        ("integer", b"123"),
        ("real", struct.pack(">d", 1.25)),
        ("text", b"\xff\x00A"),
        ("blob", b"\xff\x00A"),
    ]
    db.close()


def test_scalar_rules_do_not_silently_repair_invalid_oid():
    assert scalar("oid_decode", "AB" * 20) == b"\xab" * 20
    assert scalar("byte_length", "日本語") == 9
    assert scalar("source_kind", "git-url") == "manual_git"
    with pytest.raises(ValueError):
        scalar("oid_decode", "x" * 40)
    with pytest.raises(KeyError):
        scalar("source_kind", "invented")


def test_tagged_keys_and_rows_distinguish_types_names_and_boundaries():
    from scripts.schema_contract import row_digest, tagged_key

    assert (
        len(
            {
                tagged_key([(t, v)])
                for t, v in [
                    ("null", None),
                    ("integer", 1),
                    ("real", 1.0),
                    ("text", b"1"),
                    ("blob", b"1"),
                ]
            }
        )
        == 5
    )
    assert tagged_key([("text", b"a"), ("text", b"bc")]) != tagged_key(
        [("text", b"ab"), ("text", b"c")]
    )
    assert row_digest([("a", "text", b"1")]) != row_digest([("b", "text", b"1")])
    assert row_digest([("a", "text", b"1")]) != row_digest([("a", "blob", b"1")])
