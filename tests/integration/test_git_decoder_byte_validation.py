"""Native decoder admission and every ordinary reader agree with real bytes."""

import hashlib
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.git.parsing import GitParsing, validate_git_fact
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.git_query_context import decoded_fact, decoded_name
from repo_catalog.domain.git_decoding import DECODER_FIELDS, decode_blob, decode_commit
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_git_runtime import runtime
from tests.integration.test_git_direct_objects import oid


@pytest.fixture
def store(tmp_path):
    with runtime(tmp_path) as value:
        yield value


def key(settings):
    return hashlib.sha256(
        json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def subject(store, family, fmt="sha1", **settings):
    parser = GitParsing(store, **settings)
    row = dict(decoder_key=parser.decoder_key, **parser.decoder)
    if family == "text":
        raw = b"genuine caf\xc3\xa9 content"
        obj = parser.install_object(
            fmt, oid(fmt, "blob", raw), "blob", raw, decode=False
        )
        state, text = decode_blob(raw, parser.encoding, parser.limit)
        row.update(
            git_fact_uuidv4=str(uuid.uuid4()),
            git_object_id=obj,
            content_id=store.one(
                "SELECT content_id FROM blob_content_map WHERE git_object_id=?", (obj,)
            )[0],
            text_state=state,
            raw_text=text,
        )
    elif family == "commit":
        raw = (
            b"tree "
            + oid(fmt, "tree", b"").hex().encode()
            + b"\nauthor caf\xc3\xa9\n\ngenuine caf\xc3\xa9 message"
        )
        obj = parser.install_object(
            fmt, oid(fmt, "commit", raw), "commit", raw, decode=False
        )
        message, metadata = decode_commit(fmt, raw, parser.decoder)
        row.update(
            git_fact_uuidv4=str(uuid.uuid4()),
            git_object_id=obj,
            message_text=message,
            metadata=json.dumps(metadata),
        )
    else:
        name = b"caf\xc3\xa9.txt"
        raw = b"100644 " + name + b"\0" + oid(fmt, "blob", b"absent")
        obj = parser.install_object(
            fmt, oid(fmt, "tree", raw), "tree", raw, decode=False
        )
        row.update(
            tree_git_object_id=obj, raw_name=name, decoded_name=parser.decode(name)
        )
    return obj, row


def insert(store, family, row):
    store.execute(
        f"INSERT INTO git_{family}_facts("
        + ",".join(row)
        + ") VALUES("
        + ",".join("?" for _ in row)
        + ")",
        tuple(row.values()),
    )


def forged(row, family, *, part="value"):
    row = dict(row)
    row.update(parser_module="independent.native.sql", parser_version="unranked")
    row["decoder_key"] = key({field: row[field] for field in DECODER_FIELDS})
    if "git_fact_uuidv4" in row:
        row["git_fact_uuidv4"] = str(uuid.uuid4())
    if family == "text":
        row.update(text_state="nul", raw_text=None) if part == "state" else row.update(
            raw_text="fabricated byte interpretation"
        )
    elif family == "commit":
        row.update(
            metadata='{"author":"fabricated author"}'
        ) if part == "metadata" else row.update(
            message_text="fabricated byte interpretation"
        )
    else:
        row["decoded_name"] = "fabricated-name"
    return row


def read(store, obj, family, decoder_key=None):
    if family == "name":
        name = store.one(
            "SELECT raw_name FROM tree_entries WHERE tree_git_object_id=?", (obj,)
        )[0]
        return decoded_name(store, obj, name, decoder_key=decoder_key)
    return decoded_fact(
        store, obj, "blob" if family == "text" else "commit", decoder_key=decoder_key
    )


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize(
    "family,part",
    [
        ("text", "value"),
        ("text", "state"),
        ("commit", "value"),
        ("commit", "metadata"),
        ("name", "value"),
    ],
)
@pytest.mark.parametrize("false_first", [True, False])
def test_actual_ddl_rejects_fabricated_value_without_poisoning_either_arrival_order(
    store, fmt, family, part, false_first
):
    obj, genuine = subject(store, family, fmt)
    false = forged(genuine, family, part=part)
    if not false_first:
        insert(store, family, genuine)
    with pytest.raises(sqlite3.IntegrityError, match="decoder value contradicts"):
        insert(store, family, false)
    if false_first:
        insert(store, family, genuine)
    assert store.one(f"SELECT count(*) FROM git_{family}_facts")[0] == 1
    assert not read(store, obj, family)["decoder_conflict"]
    assert len(read(store, obj, family)["candidates"]) == 1
    explicit = read(store, obj, family, false["decoder_key"])
    assert explicit.get("fact", explicit.get("decoded_name")) is None
    assert len(explicit["candidates"]) == 1
    assert check_catalog(store, full=True) == []


@pytest.mark.parametrize("family", ["text", "commit", "name"])
def test_retained_false_candidate_is_not_a_value_or_a_default_conflict_and_fullcheck_reports_it(
    store, family
):
    obj, genuine = subject(store, family)
    insert(store, family, genuine)
    false = forged(genuine, family)
    # Model externally damaged retained state, then restore the actual guard.
    guard = store.one(
        "SELECT sql FROM sqlite_schema WHERE name=?", (f"git_{family}_facts_bytes",)
    )[0]
    with store.transaction():
        store.execute(f"DROP TRIGGER git_{family}_facts_bytes")
        insert(store, family, false)
        store.execute(guard)
    with pytest.raises(CatalogError) as error:
        validate_git_fact(store.connection, f"git_{family}_facts", false)
    assert error.value.code == "GIT_DECODER_FACT"
    actual = read(store, obj, family)
    assert not actual["decoder_conflict"] and len(actual["candidates"]) == 1
    explicit = read(store, obj, family, false["decoder_key"])
    assert explicit.get("fact", explicit.get("decoded_name")) is None
    assert any(
        issue.get("code") == "GIT_DECODER_FACT"
        and issue.get("table") == f"git_{family}_facts"
        for issue in check_catalog(store, full=True)
    )


@pytest.mark.parametrize("family", ["text", "commit", "name"])
def test_genuine_metadata_and_text_decoder_ambiguity_remains_explicit(store, family):
    obj, utf8 = subject(store, family)
    _, latin = subject(
        store, family, text_encoding="latin-1", metadata_encoding="latin-1"
    )
    insert(store, family, utf8)
    insert(store, family, latin)
    result = read(store, obj, family)
    assert result["decoder_conflict"] and len(result["candidates"]) == 2
    for candidate in (utf8, latin):
        selected = read(store, obj, family, candidate["decoder_key"])
        assert not selected["decoder_conflict"]
        if family == "name":
            assert selected["decoded_name"] == candidate["decoded_name"]
        else:
            output = "raw_text" if family == "text" else "message_text"
            assert selected["fact"][output] == candidate[output]
    assert check_catalog(store, full=True) == []


@pytest.mark.parametrize(
    "raw,limit,state",
    [
        (b"a\0b", 10, "nul"),
        (b"\xff", 10, "non_utf8"),
        (b"large", 2, "oversize"),
        (b"", 0, "eligible"),
    ],
)
def test_native_text_primitive_states_are_actual_supported_decodings(
    store, raw, limit, state
):
    parser = GitParsing(store, max_text_blob_bytes=limit)
    obj = parser.install_object("sha1", oid("sha1", "blob", raw), "blob", raw)
    result = decoded_fact(store, obj, "blob")["fact"]
    assert result["text_state"] == state
    assert result["raw_text"] == ("" if state == "eligible" else None)
    assert check_catalog(store, full=True) == []


@pytest.mark.parametrize("family", ["text", "commit", "name"])
def test_physical_damage_removes_existing_decoder_evidence_before_quarantine_scan(
    store, family
):
    obj, genuine = subject(store, family)
    insert(store, family, genuine)
    payload = store.one(
        "SELECT payload_sha256 FROM git_object_payloads WHERE git_object_id=?", (obj,)
    )[0]
    body = store.one("SELECT body FROM stored_bytes WHERE sha256=?", (payload,))[0]
    guard = store.one(
        "SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'"
    )[0]
    with store.transaction():
        store.execute("DROP TRIGGER stored_bytes_immutable")
        store.execute(
            "UPDATE stored_bytes SET body=? WHERE sha256=?", (b"x" + body[1:], payload)
        )
        store.execute(guard)
    assert not store.one("SELECT 1 FROM payload_quarantine")
    assert read(store, obj, family)["candidates"] == []
    assert check_catalog(store, full=True)


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
@pytest.mark.parametrize("family", ["commit", "name"])
def test_supported_metadata_settings_keep_real_producer_attribution(
    store, encoding, errors, family
):
    obj, genuine = subject(
        store, family, metadata_encoding=encoding, metadata_errors=errors
    )
    genuine.update(
        parser_module="independent.supported.producer", parser_version="unranked"
    )
    genuine["decoder_key"] = key({field: genuine[field] for field in DECODER_FIELDS})
    insert(store, family, genuine)
    candidate = read(store, obj, family)["candidates"][0]
    assert candidate["parser_module"] == "independent.supported.producer"
    assert candidate["parser_version"] == "unranked"
    assert validate_git_fact(store.connection, f"git_{family}_facts", genuine)
    assert check_catalog(store, full=True) == []


@pytest.mark.parametrize("family", ["text", "commit", "name"])
def test_native_candidate_key_cannot_misrepresent_supported_concrete_settings(
    store, family
):
    _, genuine = subject(store, family)
    genuine["decoder_key"] = "0" * 64
    with pytest.raises(sqlite3.IntegrityError, match="decoder value contradicts"):
        insert(store, family, genuine)
    assert store.one(f"SELECT count(*) FROM git_{family}_facts")[0] == 0


def test_normal_acquisition_search_and_index_do_not_use_damaged_retained_decoder_candidates(
    tmp_path,
):
    from repo_catalog.adapters.sqlite.index import rebuild
    from repo_catalog.application.query_service import QueryService
    from tests.integration.test_catalog3_git_runtime import collect, register
    from tests.support.git_fixture import FixtureRepo

    remote = FixtureRepo(tmp_path / "remote.git")
    remote.commit("A", {b"file.txt": b"genuine canonical content"})
    remote.ref("refs/heads/main", "A")
    with runtime(tmp_path) as store:
        repo = register(store, remote.url)
        collect(store, repo)
        genuine = dict(store.one("SELECT * FROM git_text_facts LIMIT 1"))
        false = forged(genuine, "text")
        with pytest.raises(sqlite3.IntegrityError, match="decoder value contradicts"):
            insert(store, "text", false)
        assert check_catalog(store, full=True) == []
        guard = store.one(
            "SELECT sql FROM sqlite_schema WHERE name='git_text_facts_bytes'"
        )[0]
        with store.transaction():
            store.execute("DROP TRIGGER git_text_facts_bytes")
            insert(store, "text", false)
            store.execute(guard)
        assert any(
            issue.get("code") == "GIT_DECODER_FACT"
            for issue in check_catalog(store, full=True)
        )
        rebuild(store, "code")
        docs = store.all("SELECT body FROM search_documents WHERE kind='code'")
        assert [row[0] for row in docs] == ["genuine canonical content"]
        # Equivalent decoded metadata may have a different valid JSON spelling.
        # This cannot manufacture a conflict or suppress a real commit index.
        agreed = dict(store.one("SELECT * FROM git_commit_facts LIMIT 1"))
        agreed.update(
            git_fact_uuidv4=str(uuid.uuid4()),
            parser_module="independent.equivalent.metadata",
            parser_version="unranked",
            metadata=json.dumps(json.loads(agreed["metadata"]), indent=2),
        )
        agreed["decoder_key"] = key({field: agreed[field] for field in DECODER_FIELDS})
        insert(store, "commit", agreed)
        rebuild(store, "commits")
        assert (
            len(store.all("SELECT body FROM search_documents WHERE kind='commits'"))
            == 1
        )
        query = QueryService(store.path)
        options = {
            "repo": repo["repository_uuidv4"],
            "literal": "fabricated byte interpretation",
            "decoder_key": false["decoder_key"],
        }
        assert query.query("search code", options).data["items"] == []
        genuine_result = query.query(
            "search code",
            {"repo": repo["repository_uuidv4"], "literal": "genuine canonical content"},
        )
        assert len(genuine_result.data["items"]) == 1


def test_large_tree_name_validation_and_fullcheck_do_not_rehash_the_tree_per_candidate(
    store,
):
    from repo_catalog.adapters.sqlite.cas_integrity import _git_object_identity_valid
    from repo_catalog.adapters.sqlite.git_intrinsic import _name_subject_valid
    from repo_catalog.application.git_query_context import decoded_names

    size = 2048
    child = oid("sha1", "blob", b"missing")
    raw = b"".join(
        b"100644 " + f"entry-{i:05}".encode() + b"\0" + child for i in range(size)
    )
    hashed, spans = [], []

    def identity(*args):
        if args[2] == "tree":
            hashed.append(len(args[4]))
        return _git_object_identity_valid(*args)

    def name_subject(*args):
        spans.append(len(args[1]))
        return _name_subject_valid(*args)

    store.connection.create_function(
        "repo_catalog_git_object_identity_valid", 6, identity, deterministic=True
    )
    store.connection.create_function(
        "repo_catalog_git_name_subject_valid", 7, name_subject, deterministic=True
    )
    obj = GitParsing(store).install_object(
        "sha1", oid("sha1", "tree", raw), "tree", raw
    )
    assert len(hashed) == 1
    assert len(spans) == size and sum(spans) == len(raw)
    hashed.clear()
    names = decoded_names(store, obj)
    assert len(names) == size and all(
        len(value["candidates"]) == 1 for value in names.values()
    )
    assert len(hashed) == 1
    hashed.clear()
    assert check_catalog(store, full=True) == []
    assert len(hashed) == 1
