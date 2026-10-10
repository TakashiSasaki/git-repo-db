"""Direct Git domain units, decoder candidates and frozen ref captures."""

import copy
import hashlib
import shutil

import pytest

from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.git.parsing import GitParsing, reparse_git
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.git_query_context import decoded_fact
from repo_catalog.application.job_service import JobService
from repo_catalog.application.repository_identity import add_endpoint
from repo_catalog.config import DEFAULTS, serialize
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.git_fixture import FixtureRepo, git

OWNER = "10000000-0000-4000-8000-000000000001"


@pytest.fixture
def store(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    config = copy.deepcopy(DEFAULTS)
    config["cache"].update(max_bytes=64 * 1024 * 1024, min_free_bytes=0)
    config["collection"].update(write_batch_rows=1, write_batch_bytes=1)
    (state / "catalog.toml").write_text(serialize(config))
    for name in ("cache", "work", "quarantine", "locks", "logs"):
        (state / name).mkdir()
    with Store(state, initialize=True) as value:
        yield value


def oid(fmt, typ, data):
    return hashlib.new(fmt, f"{typ} {len(data)}\0".encode() + data).digest()


def register(store, remote):
    with store.transaction():
        store.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'fixture','{}')",
            (OWNER,),
        )
        add_endpoint(store, OWNER, remote.url)
    return {"repository_uuidv4": OWNER, "name": "fixture"}


def collect(store, repo, job=None):
    job = job or JobService(store).create("sync", {"kind": "git"})
    result = GitImporter(store, CancellationToken()).sync(repo, job)
    JobService(store).update(job, "complete")
    return result


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("typ", ["tree", "commit"])
def test_interrupted_intrinsic_object_rolls_back_whole_unit(
    store, fmt, typ, monkeypatch
):
    parser = GitParsing(store)
    unrelated = parser.install_object(fmt, oid(fmt, "blob", b"keep"), "blob", b"keep")
    target = oid(fmt, "blob", b"missing")
    if typ == "tree":
        raw = b"".join(
            b"100644 " + name + b"\0" + target for name in (b"a", b"b", b"c")
        )
        interrupted = "tree_entries"
    else:
        tree = oid(fmt, "tree", b"")
        parent = oid(fmt, "commit", b"missing")
        raw = (
            b"tree "
            + tree.hex().encode()
            + b"\nparent "
            + parent.hex().encode()
            + b"\nparent "
            + parent.hex().encode()
            + b"\nauthor X <x@example.invalid> 1 +0000\ncommitter X <x@example.invalid> 1 +0000\n\nmessage\n"
        )
        interrupted = "commit_parents"
    real_write, emitted = GitParsing.write, 0

    def fail(self, sql, values):
        nonlocal emitted
        if sql.startswith("INSERT INTO " + interrupted):
            emitted += 1
            if emitted == 2:
                raise CatalogError("CANCELLED", "Interrupted intrinsic row sequence")
        return real_write(self, sql, values)

    monkeypatch.setattr(GitParsing, "write", fail)
    revision = store.revision()
    with pytest.raises(CatalogError, match="Interrupted intrinsic"):
        parser.install_object(fmt, oid(fmt, typ, raw), typ, raw)
    assert not store.one("SELECT 1 FROM git_objects WHERE oid=?", (oid(fmt, typ, raw),))
    assert not store.one(
        "SELECT 1 FROM stored_bytes WHERE sha256=?", (hashlib.sha256(raw).digest(),)
    )
    assert store.one(
        "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (unrelated,)
    )
    assert store.one("SELECT count(*) FROM git_objects")[0] == 1
    assert store.revision() == revision
    assert not store.all("PRAGMA foreign_key_check")


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_canonical_bytes_required_and_missing_target_is_not_fabricated(store, fmt):
    parser = GitParsing(store)
    child = oid(fmt, "blob", b"absent")
    tree = b"100644 missing\0" + child
    obj_id = parser.install_object(fmt, oid(fmt, "tree", tree), "tree", tree)
    entry = store.one(
        "SELECT * FROM tree_entries WHERE tree_git_object_id=?", (obj_id,)
    )
    assert entry["child_oid"] == child
    assert entry["child_git_object_id"] is None
    assert store.one("SELECT count(*) FROM git_objects")[0] == 1
    assert store.one(
        "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj_id,)
    )
    with pytest.raises(CatalogError, match="missing descendants"):
        parser.manifest(obj_id)
    assert not store.one("SELECT 1 FROM root_manifests")
    with pytest.raises(CatalogError, match="declared Git object identity"):
        parser.install_object(fmt, child, "blob", b"fake")
    assert store.one("SELECT count(*) FROM git_objects")[0] == 1
    child_id = parser.install_object(fmt, child, "blob", b"absent")
    parser.parse_object(
        store.one("SELECT * FROM git_objects WHERE git_object_id=?", (obj_id,)), tree
    )
    parser.manifest(obj_id)
    assert (
        store.one(
            "SELECT child_git_object_id FROM tree_entries WHERE tree_git_object_id=?",
            (obj_id,),
        )[0]
        == child_id
    )
    assert (
        store.one(
            "SELECT complete FROM root_manifests WHERE tree_git_object_id=?", (obj_id,)
        )[0]
        == 1
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"100644 a\0bad",
        b"100644 a\0" + b"x" * 20 + b"invalid",
        b"+100644 a\0" + b"x" * 20,
    ],
)
def test_malformed_tree_never_leaks_verified_bytes_or_partial_structure(store, raw):
    with pytest.raises(CatalogError):
        GitParsing(store).install_object("sha1", oid("sha1", "tree", raw), "tree", raw)
    for table in (
        "git_objects",
        "git_object_payloads",
        "tree_objects",
        "tree_entries",
        "stored_bytes",
    ):
        assert store.one(f"SELECT count(*) FROM {table}")[0] == 0


@pytest.mark.parametrize("raw,conflicting", [(b"\xfftext", True), (b"ascii", False)])
def test_decoder_candidates_remain_explicit_without_profile_or_version_winner(
    store, raw, conflicting
):
    original = GitParsing(store)
    obj_id = original.install_object("sha1", oid("sha1", "blob", raw), "blob", raw)
    alternative = GitParsing(store, text_encoding="latin-1")
    alternative.parse_object(
        store.one("SELECT * FROM git_objects WHERE git_object_id=?", (obj_id,)), raw
    )
    result = decoded_fact(store, obj_id, "blob")
    assert result["decoder_conflict"] is conflicting
    assert len(result["candidates"]) == 2
    if conflicting:
        assert result["fact"] is None
    else:
        assert result["fact"]["raw_text"] == "ascii"
        assert len(result["fact"]["decoder_evidence"]) == 2
    explicit = decoded_fact(store, obj_id, "blob", decoder_key=alternative.decoder_key)
    assert not explicit["decoder_conflict"]
    assert explicit["fact"]["raw_text"] == raw.decode("latin-1")
    assert store.one("SELECT count(*) FROM git_objects")[0] == 1
    assert not store.one("SELECT 1 FROM sqlite_schema WHERE name='parser_profiles'")


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_reanalysis_keeps_real_capture_and_intrinsic_identity(store, tmp_path, fmt):
    remote = FixtureRepo(tmp_path / "remote.git", fmt)
    remote.commit("A", {b"a.txt": b"\xfftext", b"odd-\xff.txt": b"abc"})
    remote.ref("refs/heads/main", "A")
    repo = register(store, remote)
    result = collect(store, repo)
    tables = (
        "git_objects",
        "git_acquisitions",
        "git_object_payloads",
        "snapshots",
        "ref_observations",
        "commits",
        "commit_parents",
        "tree_entries",
        "root_manifest_entries",
    )
    before = {
        table: [tuple(row) for row in store.all(f"SELECT * FROM {table}")]
        for table in tables
    }
    shutil.rmtree(store.path / "cache")
    reparsed = reparse_git(
        store,
        result["git_acquisition_id"],
        text_encoding="latin-1",
        metadata_encoding="latin-1",
    )
    assert reparsed["decoded_objects"] > 0
    assert "parsed_result_uuidv4" not in reparsed
    assert "snapshot_id" not in reparsed
    for table in tables:
        assert [tuple(row) for row in store.all(f"SELECT * FROM {table}")] == before[
            table
        ]
    commit = store.one("SELECT git_object_id FROM commits")[0]
    assert decoded_fact(store, commit, "commit")["decoder_conflict"]
    assert (
        store.one("SELECT snapshot_id FROM current_snapshots")[0]
        == result["snapshot_id"]
    )
    assert not store.all("PRAGMA foreign_key_check")
    assert store.one("PRAGMA integrity_check")[0] == "ok"


def test_ref_predecessors_keep_sequential_capture_and_divergent_resume_honest(
    store, tmp_path, monkeypatch
):
    remote = FixtureRepo(tmp_path / "remote.git")
    remote.commit("A", {b"a.txt": b"abc"})
    remote.ref("refs/heads/main", "A")
    repo = register(store, remote)
    first = collect(store, repo)["snapshot_id"]
    second = collect(store, repo)["snapshot_id"]
    assert (
        store.one(
            "SELECT predecessor_snapshot_id FROM snapshots WHERE snapshot_id=?",
            (second,),
        )[0]
        == first
    )
    assert store.one("SELECT snapshot_id FROM current_snapshots")[0] == second
    job = JobService(store).create("sync", {"kind": "git"})
    real_import = GitImporter.import_objects

    def fail(*args, **kwargs):
        raise CatalogError("CANCELLED", "Interrupted fixed refs")

    monkeypatch.setattr(GitImporter, "import_objects", fail)
    with pytest.raises(CatalogError, match="Interrupted fixed"):
        collect(store, repo, job=job)
    interrupted = store.one(
        "SELECT a.git_acquisition_id,a.refs_observed_at_us FROM git_acquisitions a JOIN acquisition_progress p USING(git_acquisition_id) WHERE p.job_id=?",
        (job,),
    )
    JobService(store).update(job, "interrupted")
    monkeypatch.setattr(GitImporter, "import_objects", real_import)
    remote.commit("B", {b"a.txt": b"new"}, parents=("A",))
    remote.ref("refs/heads/main", "B")
    newest = collect(store, repo)["snapshot_id"]
    assert store.one("SELECT snapshot_id FROM current_snapshots")[0] == newest
    JobService(store).resume(job)
    resumed = collect(store, repo, job=job)
    assert resumed["git_acquisition_id"] == interrupted[0]
    assert (
        store.one(
            "SELECT refs_observed_at_us FROM git_acquisitions WHERE git_acquisition_id=?",
            (interrupted[0],),
        )[0]
        == interrupted[1]
    )
    assert not store.one("SELECT 1 FROM current_snapshots")
    assert (
        store.one(
            "SELECT target_oid FROM ref_observations WHERE snapshot_id=?",
            (interrupted[0],),
        )[0].hex()
        == remote.commits["A"]
    )
    assert store.one("SELECT count(*) FROM snapshots WHERE complete=1")[0] == 4


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_annotated_tag_and_root_capture_require_actual_complete_object_closure(
    store, tmp_path, fmt
):
    remote = FixtureRepo(tmp_path / "remote.git", fmt)
    remote.commit("A", {b"sub/a.txt": b"abc"})
    remote.ref("refs/heads/main", "A")
    raw_tag = (
        b"object "
        + remote.commits["A"].encode()
        + b"\ntype commit\ntag version\ntagger X <x@example.invalid> 1 +0000\n\ntag body\n"
    )
    tag = (
        git(remote.path, "hash-object", "-w", "-t", "tag", "--stdin", input=raw_tag)
        .strip()
        .decode()
    )
    remote.ref("refs/tags/version", tag)
    repo = register(store, remote)
    result = collect(store, repo)
    parser = GitParsing(store, OWNER)
    assert (
        parser.validate_acquisition(result["git_acquisition_id"])
        == store.one("SELECT count(*) FROM git_objects")[0]
    )
    assert store.one("SELECT raw_payload FROM tag_objects")[0] == raw_tag
    assert store.one("SELECT complete FROM snapshots")[0] == 1
    assert store.one("SELECT raw_path FROM root_manifest_entries")[0] == b"sub/a.txt"
    assert not store.one(
        "SELECT 1 FROM sqlite_schema WHERE name='git_acquisition_publications'"
    )


@pytest.mark.parametrize("attack", ["name", "child", "inflated-prefix"])
def test_canonical_raw_tree_rejects_forged_relations_even_with_matching_counts(
    store, attack
):
    parser = GitParsing(store)
    target = oid("sha1", "blob", b"missing")
    raw = b"100644 a\0" + target + b"100644 b\0" + target
    obj_id = parser.install_object(
        "sha1", oid("sha1", "tree", raw), "tree", raw, decode=False
    )
    store.execute("DROP TRIGGER tree_entries_immutable")
    if attack == "name":
        store.execute("UPDATE tree_entries SET raw_name=X'78' WHERE raw_name=X'61'")
    elif attack == "child":
        store.execute(
            "UPDATE tree_entries SET child_oid=? WHERE raw_name=X'61'", (b"y" * 20,)
        )
    else:
        store.execute("DROP TRIGGER tree_entries_retain")
        store.execute("DROP TRIGGER tree_objects_immutable")
        store.execute("DELETE FROM tree_entries WHERE raw_name=X'62'")
        store.execute("UPDATE tree_entries SET entry_length=?", (len(raw),))
        store.execute("UPDATE tree_objects SET entry_count=1")
    assert not store.one(
        "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj_id,)
    )
    assert any(
        row.get("code") == "GIT_OBJECT_STRUCTURE"
        for row in check_catalog(store, full=True)
    )


def test_full_validation_rejects_intrinsic_rows_of_a_foreign_object_type(store):
    parser = GitParsing(store)
    obj_id = parser.install_object(
        "sha1", oid("sha1", "blob", b"text"), "blob", b"text"
    )
    store.execute("DROP TRIGGER tree_objects_object_type")
    store.execute("INSERT INTO tree_objects VALUES(?,0)", (obj_id,))
    assert any(
        row.get("code") == "GIT_OBJECT_STRUCTURE"
        for row in check_catalog(store, full=True)
    )


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_raw_octal_mode_spelling_remains_exact_and_available(store, fmt):
    target = oid(fmt, "blob", b"missing")
    raw = b"00100644 a\0" + target
    obj_id = GitParsing(store).install_object(fmt, oid(fmt, "tree", raw), "tree", raw)
    assert store.one("SELECT mode FROM tree_entries")[0] == 0o100644
    assert store.one(
        "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj_id,)
    )
    before = store.revision()
    store.execute("PRAGMA query_only=ON")
    assert check_catalog(store, full=True) == []
    assert store.revision() == before


def test_independent_git_value_unit_advances_revision_only_for_real_changes(store):
    parser = GitParsing(store)
    before = store.revision()
    raw = b"\xfftext"
    obj_id = parser.install_object("sha1", oid("sha1", "blob", raw), "blob", raw)
    assert store.revision() != before
    before = store.revision()
    parser.install_object("sha1", oid("sha1", "blob", raw), "blob", raw)
    assert store.revision() == before
    alternative = GitParsing(store, text_encoding="latin-1")
    alternative.parse_object(
        store.one("SELECT * FROM git_objects WHERE git_object_id=?", (obj_id,)), raw
    )
    assert store.revision() != before
