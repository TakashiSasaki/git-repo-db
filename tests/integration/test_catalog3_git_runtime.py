"""Direct catalog3 acquisition uses disposable local Git and no legacy runtime."""

import copy

import pytest

from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.application.repository_identity import add_endpoint
from repo_catalog.config import DEFAULTS, serialize
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.git_fixture import FixtureRepo, git


def runtime(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    config = copy.deepcopy(DEFAULTS)
    config["cache"].update(max_bytes=64 * 1024 * 1024, min_free_bytes=0)
    (state / "catalog.toml").write_text(serialize(config))
    for name in ("cache", "work", "quarantine", "locks", "logs"):
        (state / name).mkdir()
    return Store(state, initialize=True)


def register(store, url):
    with store.transaction():
        store.execute(
            "INSERT INTO repositories(repository_uuidv4,name,preferred_repository_endpoint_id,metadata) VALUES('10000000-0000-4000-8000-000000000001','fixture',NULL,'{}')"
        )
        add_endpoint(store, "10000000-0000-4000-8000-000000000001", url)
    return {
        "repository_uuidv4": "10000000-0000-4000-8000-000000000001",
        "name": "fixture",
    }


def collect(store, repo, token=None, job=None):
    job = job or JobService(store).create("sync", {"kind": "git"})
    result = GitImporter(store, token or CancellationToken()).sync(repo, job)
    JobService(store).update(job, "complete")
    return result


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_catalog3_git_preserves_roots_bytes_parents_and_new_observations(tmp_path, fmt):
    fixture = FixtureRepo(tmp_path / "remote.git", fmt)
    fixture.commit("A", {b"raw-\xff.txt": b"abc", b"empty.txt": b""})
    fixture.commit("B", {b"raw-\xff.txt": b"def"}, parents=("A",))
    fixture.commit("C", {b"copy.txt": b"abc"}, parents=("A",))
    fixture.commit("M", {b"raw-\xff.txt": b"abc"}, parents=("B", "C"))
    fixture.ref("refs/heads/main", "M")
    fixture.ref("refs/heads/alias", "M")
    fixture.ref("refs/tags/plain", "M")
    # An annotated tag origin must match its peeled traversal target.
    tagged = (
        b"object "
        + fixture.commits["M"].encode()
        + b"\ntype commit\ntag annotation\ntagger Fixture <fixture@example.invalid> 1700000000 +0000\n\nraw tag\n"
    )
    tag = (
        git(fixture.path, "hash-object", "-w", "-t", "tag", "--stdin", input=tagged)
        .strip()
        .decode()
    )
    fixture.ref("refs/tags/annotation", tag)
    with runtime(tmp_path) as store:
        repo = register(store, fixture.url)
        first = collect(store, repo)
        sid = first["snapshot_id"]
        assert (
            store.one(
                "SELECT (SELECT snapshot_id FROM current_snapshots WHERE repository_uuidv4='10000000-0000-4000-8000-000000000001')"
            )[0]
            == sid
        )
        assert (
            store.one(
                "SELECT count(*) FROM acquisition_roots WHERE git_acquisition_id=?",
                (sid,),
            )[0]
            == 1
        )
        assert (
            store.one("SELECT count(*) FROM root_origins WHERE snapshot_id=?", (sid,))[
                0
            ]
            == 4
        )
        assert (
            store.one("SELECT published FROM snapshots WHERE snapshot_id=?", (sid,))[0]
            == 1
        )
        oid = bytes.fromhex(fixture.commits["M"])
        commit = store.one(
            "SELECT c.* FROM commits c JOIN git_objects g ON g.git_object_id=c.git_object_id WHERE g.object_format=? AND g.oid=?",
            (fmt, oid),
        )
        assert commit["raw_message"] == "commit M 認証\n".encode()
        parents = store.all(
            "SELECT g.oid FROM commit_parents p JOIN git_objects g ON g.git_object_id=p.parent_git_object_id WHERE p.commit_git_object_id=? ORDER BY p.parent_ordinal",
            (commit["git_object_id"],),
        )
        assert [r[0].hex() for r in parents] == [
            fixture.commits["B"],
            fixture.commits["C"],
        ]
        assert (
            store.one(
                "SELECT raw_path FROM root_manifest_entries WHERE tree_git_object_id=?",
                (commit["tree_git_object_id"],),
            )[0]
            == b"raw-\xff.txt"
        )
        counts = [
            store.one(f"SELECT count(*) FROM {t}")[0]
            for t in ("git_objects", "contents", "content_digests")
        ]
        second = collect(store, repo)
        assert second["snapshot_id"] != sid
        assert counts == [
            store.one(f"SELECT count(*) FROM {t}")[0]
            for t in ("git_objects", "contents", "content_digests")
        ]
        assert (
            store.one(
                "SELECT (SELECT snapshot_id FROM current_snapshots WHERE repository_uuidv4='10000000-0000-4000-8000-000000000001')"
            )[0]
            == second["snapshot_id"]
        )
        assert not store.all("PRAGMA foreign_key_check")
        assert not store.one("SELECT 1 FROM sqlite_schema WHERE name='collection_runs'")


def test_interrupted_fixed_refs_resume_without_new_remote_observation(
    tmp_path, monkeypatch
):
    fixture = FixtureRepo(tmp_path / "remote.git")
    fixture.commit("A", {b"a.txt": b"abc"})
    fixture.ref("refs/heads/main", "A")
    with runtime(tmp_path) as store:
        repo = register(store, fixture.url)
        job = JobService(store).create("sync", {"kind": "git"})
        original = GitImporter.import_objects

        def interrupt(self, *args):
            raise CatalogError("CANCELLED", "Synthetic interruption after ref commit")

        monkeypatch.setattr(GitImporter, "import_objects", interrupt)
        with pytest.raises(CatalogError, match="Synthetic interruption"):
            collect(store, repo, job=job)
        run = store.one("SELECT * FROM git_acquisitions")
        observed = run["refs_observed_at_us"]
        assert (
            store.one(
                "SELECT (SELECT snapshot_id FROM current_snapshots WHERE repository_uuidv4='10000000-0000-4000-8000-000000000001')"
            )[0]
            is None
        )
        JobService(store).update(job, "interrupted")
        JobService(store).resume(job)
        monkeypatch.setattr(GitImporter, "import_objects", original)
        # Fixed roots are local durable restart evidence even if source moves.
        fixture.commit("B", {b"a.txt": b"changed"}, parents=("A",))
        fixture.ref("refs/heads/main", "B")
        resumed = collect(store, repo, job=job)
        assert resumed["git_acquisition_id"] == run["git_acquisition_id"]
        assert (
            store.one(
                "SELECT refs_observed_at_us FROM git_acquisitions WHERE git_acquisition_id=?",
                (run["git_acquisition_id"],),
            )[0]
            == observed
        )
        ref = store.one(
            "SELECT target_oid FROM ref_observations WHERE snapshot_id=?",
            (run["git_acquisition_id"],),
        )
        assert ref[0].hex() == fixture.commits["A"]
        assert store.one("SELECT count(*) FROM root_origins")[0] == 1
        assert store.one("SELECT count(*) FROM cache_leases")[0] == 0
        assert store.one("SELECT count(*) FROM space_reservations")[0] == 0


def test_older_interrupted_snapshot_cannot_replace_a_new_completed_observation(
    tmp_path, monkeypatch
):
    first_us = 1_791_360_000_123_456
    monkeypatch.setattr("repo_catalog.adapters.git.importer.now_us", lambda: first_us)
    fixture = FixtureRepo(tmp_path / "remote.git")
    fixture.commit("A", {b"a.txt": b"abc"})
    fixture.ref("refs/heads/main", "A")
    with runtime(tmp_path) as store:
        repo = register(store, fixture.url)
        job = JobService(store).create("sync", {"kind": "git"})
        original = GitImporter.import_objects

        def interrupt(self, *args):
            raise CatalogError("CANCELLED", "Synthetic interruption")

        monkeypatch.setattr(GitImporter, "import_objects", interrupt)
        with pytest.raises(CatalogError):
            collect(store, repo, job=job)
        old = store.one("SELECT git_acquisition_id FROM git_acquisitions")[0]
        JobService(store).update(job, "interrupted")
        monkeypatch.setattr(GitImporter, "import_objects", original)
        # Distinct observations within one millisecond must keep their ordering.
        monkeypatch.setattr(
            "repo_catalog.adapters.git.importer.now_us", lambda: first_us + 1
        )
        fixture.commit("B", {b"a.txt": b"changed"}, parents=("A",))
        fixture.ref("refs/heads/main", "B")
        newest = collect(store, repo)["snapshot_id"]
        assert [
            row[0]
            for row in store.all(
                "SELECT refs_observed_at_us FROM git_acquisitions ORDER BY refs_observed_at_us"
            )
        ] == [first_us, first_us + 1]
        assert store.one("SELECT count(*) FROM coverage_claims")[0] == 4
        JobService(store).resume(job)
        collect(store, repo, job=job)
        assert old != newest
        assert (
            store.one("SELECT published FROM snapshots WHERE snapshot_id=?", (old,))[0]
            == 1
        )
        # Independent acquisitions froze their predecessors before either
        # completed. Late publication creates two heads, never a time winner.
        assert (
            store.one(
                "SELECT (SELECT snapshot_id FROM current_snapshots WHERE repository_uuidv4='10000000-0000-4000-8000-000000000001')"
            )[0]
            is None
        )
        assert store.one("SELECT count(*) FROM fact_selection_decisions")[0] == 2
        assert store.one("SELECT count(*) FROM coverage_claims")[0] == 4
        assert {
            (row["coverage_state"], row["observed_at_us"])
            for row in store.all("SELECT * FROM current_coverage")
        } == {("complete", first_us + 1)}


def test_unverified_imported_oid_needs_actual_bytes_before_admission(tmp_path):
    fixture = FixtureRepo(tmp_path / "remote.git")
    fixture.commit("A", {b"a.txt": b"abc"})
    fixture.ref("refs/heads/main", "A")
    oid = fixture.blob(b"abc")
    with runtime(tmp_path) as store:
        repo = register(store, fixture.url)
        store.execute(
            "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',3,0)",
            (bytes.fromhex(oid),),
        )
        collect(store, repo)
        assert (
            store.one(
                "SELECT verified FROM git_objects WHERE oid=?", (bytes.fromhex(oid),)
            )[0]
            == 1
        )
        assert store.one("SELECT raw_text FROM contents")[0] == "abc"


def test_unknown_provider_binding_admits_one_proven_identity(tmp_path):
    from repo_catalog.application.repository_identity import add_instance, bind

    with runtime(tmp_path) as store:
        with store.transaction():
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,preferred_repository_endpoint_id,metadata) VALUES('10000000-0000-4000-8000-000000000001','fixture',NULL,'{}')"
            )
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,preferred_repository_endpoint_id,metadata) VALUES('10000000-0000-4000-8000-000000000002','10000000-0000-4000-8000-000000000002',NULL,'{}')"
            )
            service = add_instance(store, "github", "fixture-github")
            bind(store, "10000000-0000-4000-8000-000000000001", service)
            binding = store.one(
                "SELECT repository_binding_id FROM repository_bindings WHERE repository_uuidv4='10000000-0000-4000-8000-000000000001'"
            )[0]
            bind(store, "10000000-0000-4000-8000-000000000001", service, "42")
            assert tuple(
                store.one(
                    "SELECT repository_binding_id,provider_repository_id FROM repository_bindings WHERE repository_uuidv4='10000000-0000-4000-8000-000000000001'"
                )
            ) == (binding, "42")
            with pytest.raises(CatalogError, match="different identity"):
                bind(store, "10000000-0000-4000-8000-000000000001", service, "43")
            with pytest.raises(CatalogError, match="another repository"):
                bind(store, "10000000-0000-4000-8000-000000000002", service, "42")
        assert not store.all("PRAGMA foreign_key_check")
