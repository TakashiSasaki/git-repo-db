"""Executed ADR 0031 canonicalization vectors and finite codec boundaries."""

from __future__ import annotations

import json

import pytest

from repo_catalog.domain import resource_identity as codec
from repo_catalog.domain.resource_identity import (
    MAX_IDENTITY_ARRAY_DEPTH,
    MAX_IDENTITY_BYTES,
    MAX_IDENTITY_NODES,
    IdentityValue,
    encode_identity,
    parse_identity,
)

# Every applicable positive row of the schema's specification-vector table.
VECTORS: list[tuple[IdentityValue, str]] = [
    ("731", '"731"'),
    (["731"], '["731"]'),
    ("00731", '"00731"'),
    ("", '""'),
    ([], "[]"),
    ([""], '[""]'),
    ([[]], "[[]]"),
    (["project-a", ["731", []]], '["project-a",["731",[]]]'),
    (["a", "b"], '["a","b"]'),
    (["b", "a"], '["b","a"]'),
    ([["a"], "b"], '[["a"],"b"]'),
    ("\u00e9", r'"\u00e9"'),
    ("e\u0301", r'"e\u0301"'),
    ("日本", r'"\u65e5\u672c"'),
    ("😀", r'"\ud83d\ude00"'),
    ('"\\/', r'"\"\\/"'),
    ("\n\t\0\x7f", r'"\n\t\u0000\u007f"'),
    (" A ", '" A "'),
    ("a", '"a"'),
    (
        "12345678901234567890123456789012345678901234567890",
        '"12345678901234567890123456789012345678901234567890"',
    ),
    ("\b\f\r", r'"\b\f\r"'),
    ("\x01\x1f", r'"\u0001\u001f"'),
    ("\u0080\uffff\U0010ffff", r'"\u0080\uffff\udbff\udfff"'),
]


@pytest.mark.parametrize(("native", "serialized"), VECTORS)
def test_specification_positive_vectors(native, serialized):
    assert encode_identity(native) == serialized
    assert parse_identity(serialized) == native
    assert encode_identity(parse_identity(serialized)) == serialized
    assert serialized.isascii()


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("731", ["731"]),
        ("00731", "731"),
        ("", []),
        ([], [""]),
        ([""], [[]]),
        (["a", "b"], ["b", "a"]),
        ([["a"], "b"], ["a", "b"]),
        ("é", "e\u0301"),
        (" A ", "a"),
        ('["project","731"]', ["project", "731"]),
        ('"731"', "731"),
    ],
)
def test_native_identity_distinctions(left, right):
    assert encode_identity(left) != encode_identity(right)


@pytest.mark.parametrize(
    "text",
    [
        '"é"',
        '"😀"',
        r'"\u0061"',
        r'"\/"',
        r'"\u00E9"',
        r'"\uD83D\uDE00"',
        r'"\u000a"',
        r'"\u0009"',
        ' ["731"] ',
        '[ "731"]',
        '["a", "b"]',
        '"731"\n',
        '"731" "732"',
        '\ufeff"731"',
        "731",
        "true",
        "false",
        "null",
        "{}",
        '{"id":"731"}',
        '{"id":"731","id":"731"}',
        '["731",null]',
        "[1]",
        "[[false]]",
        "[{}]",
        r'"\ud800"',
        r'"\udc00"',
        r'"\udc00\ud800"',
        r'"\ud800\ud800"',
        r'"\ud800a"',
        r'"\ud800\n"',
        r'"\ud800\udc00\udc00"',
        '"\ud800"',
        "",
        '"unterminated',
        '"unescaped\x00"',
        '"unescaped\n"',
        "NaN",
        "Infinity",
        "-Infinity",
        "[",
        "]",
        "[,]",
        '["a",]',
        '["a"',
        '["a" "b"]',
        '"a"[]',
        r'"\x41"',
        r'"\u123"',
        r'"\u12xz"',
        '"trailing\\',
    ],
)
def test_noncanonical_malformed_and_forbidden_serialized_vectors(text):
    with pytest.raises(ValueError):
        parse_identity(text)


@pytest.mark.parametrize(
    "value",
    [
        1,
        -1,
        1.0,
        float("nan"),
        float("inf"),
        True,
        False,
        None,
        {},
        (),
        b"731",
        object(),
    ],
)
@pytest.mark.parametrize("array_depth", [0, 1, 2, 31])
def test_nonidentity_native_types_rejected_at_every_depth(value, array_depth):
    for _ in range(array_depth):
        value = [value]
    with pytest.raises(TypeError):
        encode_identity(value)


@pytest.mark.parametrize("token", ["0", "1.0", "true", "false", "null", "{}"])
@pytest.mark.parametrize("array_depth", [0, 1, 2, 32])
def test_nonidentity_serialized_types_rejected_at_every_depth(token, array_depth):
    with pytest.raises(ValueError):
        parse_identity("[" * array_depth + token + "]" * array_depth)


@pytest.mark.parametrize("value", ["\ud800", "\udfff", "\ud83d\ude00", "a\udc00b"])
@pytest.mark.parametrize("nested", [False, True])
def test_native_surrogate_codepoints_are_not_unicode_scalars(value, nested):
    with pytest.raises(ValueError):
        encode_identity([value] if nested else value)


class StringSubclass(str):
    pass


class ListSubclass(list):
    pass


@pytest.mark.parametrize("value", [StringSubclass("731"), ListSubclass(["731"])])
def test_native_subclasses_are_rejected(value):
    with pytest.raises(TypeError):
        encode_identity(value)
    with pytest.raises(TypeError):
        encode_identity([value])


@pytest.mark.parametrize(
    "value",
    [
        None,
        731,
        ["731"],
        StringSubclass('"731"'),
        b'"731"',
        b'"\xff"',
        b'"\xc0\x80"',
        b'"\xed\xa0\x80"',
        b'"\xf0\x9f"',
        bytearray(b'"731"'),
    ],
)
def test_parse_requires_exact_text_including_rejection_of_invalid_utf8_bytes(value):
    with pytest.raises(TypeError):
        parse_identity(value)


@pytest.mark.parametrize(
    "native",
    [
        "a" * (MAX_IDENTITY_BYTES - 2),
        "\0" * ((MAX_IDENTITY_BYTES - 2) // 6) + "aa",
        "😀" * ((MAX_IDENTITY_BYTES - 2) // 12) + "aa",
        ["a" * (MAX_IDENTITY_BYTES - 4)],
    ],
)
def test_exact_canonical_byte_boundary_and_limit_plus_one(native):
    text = encode_identity(native)
    assert len(text.encode("utf-8")) == MAX_IDENTITY_BYTES
    assert parse_identity(text) == native
    excessive = native + "a" if type(native) is str else [native[0] + "a"]
    with pytest.raises(ValueError, match="byte"):
        encode_identity(excessive)
    # The extra ASCII scalar adds exactly one canonical byte.
    excessive_text = json.dumps(excessive, ensure_ascii=True, separators=(",", ":"))
    assert len(excessive_text) == MAX_IDENTITY_BYTES + 1
    with pytest.raises(ValueError):
        parse_identity(excessive_text)


@pytest.mark.parametrize("leaf", ["", []])
def test_array_depth_boundary_and_limit_plus_one(leaf):
    value = leaf
    wrappers = MAX_IDENTITY_ARRAY_DEPTH - (type(leaf) is list)
    for _ in range(wrappers):
        value = [value]
    text = encode_identity(value)
    assert parse_identity(text) == value
    with pytest.raises(ValueError, match="depth"):
        encode_identity([value])
    with pytest.raises(ValueError, match="depth"):
        parse_identity("[" + text + "]")


@pytest.mark.parametrize(
    "value",
    [
        [""] * (MAX_IDENTITY_NODES - 1),
        [[""]] * ((MAX_IDENTITY_NODES - 2) // 2) + [""],
    ],
)
def test_total_node_boundary_includes_arrays_strings_and_root(value):
    text = encode_identity(value)
    assert parse_identity(text) == value
    excessive = value + [""]
    with pytest.raises(ValueError, match="node"):
        encode_identity(excessive)
    with pytest.raises(ValueError, match="node"):
        parse_identity(text[:-1] + ',""]')


def test_native_cycle_and_extreme_depth_fail_without_recursion_exhaustion():
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="depth"):
        encode_identity(cycle)
    deep = ""
    for _ in range(10_000):
        deep = [deep]
    with pytest.raises(ValueError, match="depth"):
        encode_identity(deep)


@pytest.mark.parametrize(
    "text",
    [
        "[" * 10_000 + '"]"' + "]" * 10_000,
        "[" + ",".join(['""'] * MAX_IDENTITY_NODES) + "]",
        '"' + "a" * MAX_IDENTITY_BYTES + '"',
        "[{}]",
        "[null]",
    ],
)
def test_parser_refuses_structural_and_byte_overruns_before_json_decoding(
    monkeypatch, text
):
    def forbidden_decode(*args, **kwargs):
        pytest.fail("Unbounded or forbidden identity reached json.loads")

    monkeypatch.setattr(codec.json, "loads", forbidden_decode)
    with pytest.raises(ValueError):
        parse_identity(text)


@pytest.mark.parametrize(
    "value",
    [
        [""] * MAX_IDENTITY_NODES,
        "\0" * (MAX_IDENTITY_BYTES // 6 + 1),
        "😀" * (MAX_IDENTITY_BYTES // 12 + 1),
    ],
)
def test_encoder_refuses_node_and_escape_expansion_overruns_before_dumps(
    monkeypatch, value
):
    def forbidden_encode(*args, **kwargs):
        pytest.fail("Over-limit identity reached json.dumps")

    monkeypatch.setattr(codec.json, "dumps", forbidden_encode)
    with pytest.raises(ValueError):
        encode_identity(value)


def test_brackets_inside_strings_do_not_count_as_arrays_and_results_are_fresh():
    value = ["[" * 100, '\\"[]', [[]]]
    text = encode_identity(value)
    first = parse_identity(text)
    second = parse_identity(text)
    first[2][0].append("changed")
    assert second == value
    assert encode_identity(second) == text
