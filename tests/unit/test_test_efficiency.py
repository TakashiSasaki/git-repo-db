"""Shared preparation must stay isolated, complete and corruption-sensitive."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.support import git_fixture
from tests.support.distributions import build_once


def products(root):
    files = {
        "wheel": root / "direct.whl",
        "sdist_wheel": root / "rebuilt.whl",
        "requirements": root / "requirements.txt",
    }
    for name, path in files.items():
        path.write_bytes(name.encode())
    return files


def test_shared_build_recovers_failed_prefix_and_reuses_only_complete_products(
    tmp_path,
):
    def fail(root):
        (root / "partial.whl").write_text("unfinished")
        raise RuntimeError("build failed")

    with pytest.raises(RuntimeError, match="build failed"):
        build_once(tmp_path, fail)
    assert not (tmp_path / "ready.json").exists()

    def retry(root):
        assert not (root / "partial.whl").exists()
        return products(root)

    first = build_once(tmp_path, retry)

    def forbidden(root):
        raise AssertionError("already built in this invocation")

    assert build_once(tmp_path, forbidden) == first
    assert set(json.loads((tmp_path / "ready.json").read_text())) == set(first)


def test_competing_builders_publish_one_complete_set(tmp_path):
    entered, release, competing = (threading.Event() for _ in range(3))
    calls = []

    def build(root):
        calls.append(root)
        entered.set()
        assert release.wait(5)
        return products(root)

    def second():
        competing.set()
        return build_once(tmp_path, build)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(build_once, tmp_path, build)
        try:
            assert entered.wait(5)
            other = pool.submit(second)
            assert competing.wait(5)
            assert not other.done()
        finally:
            release.set()
        assert first.result(timeout=5) == other.result(timeout=5)
    assert len(calls) == 1


@pytest.mark.parametrize("fault", ["corrupt", "missing", "escape", "incomplete"])
def test_changed_or_invalid_shared_products_are_not_silently_rebuilt(tmp_path, fault):
    files = build_once(tmp_path, products)
    receipt = tmp_path / "ready.json"
    if fault == "corrupt":
        files["wheel"].write_text("changed")
    elif fault == "missing":
        files["wheel"].unlink()
    else:
        data = json.loads(receipt.read_text())
        if fault == "escape":
            data["wheel"]["path"] = "../outside.whl"
        else:
            del data["sdist_wheel"]
        receipt.write_text(json.dumps(data))
    with pytest.raises((ValueError, FileNotFoundError)):
        build_once(tmp_path, lambda _: pytest.fail("must not rebuild a sealed set"))


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_tree_setup_writes_duplicate_blobs_once_without_sharing_repositories(
    tmp_path, monkeypatch, fmt
):
    writes = []
    original = git_fixture.git

    def record(path, *args, **kwargs):
        if args[:1] == ("hash-object",):
            writes.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(git_fixture, "git", record)
    repo = git_fixture.FixtureRepo(tmp_path / "one.git", fmt)
    files = {
        b"a.txt": b"same",
        b"nested/b.txt": ("100755", b"same"),
        b"link": ("120000", b"same"),
    }
    tree = repo.tree(files)
    assert repo.tree(files) == tree
    repo.commit("A", files)
    repo.commit("B", files, ("A",))
    assert len(writes) == 1
    peer = git_fixture.FixtureRepo(tmp_path / "two.git", fmt)
    assert peer.tree(files) == tree
    assert len(writes) == 2
    for fixture in (repo, peer):
        assert original(fixture.path, "show", tree + ":a.txt") == b"same"
        assert original(fixture.path, "show", tree + ":nested/b.txt") == b"same"
        modes = original(fixture.path, "ls-tree", "-r", tree).decode()
        assert "100755 blob" in modes and "120000 blob" in modes


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_missing_fixture_object_is_rewritten_and_public_blob_still_uses_git(
    tmp_path, monkeypatch, fmt
):
    repo = git_fixture.FixtureRepo(tmp_path / "one.git", fmt)
    tree = repo.tree({b"a": b"same"})
    oid = next(iter(repo.raws))
    (repo.path / "objects" / oid[:2] / oid[2:]).unlink()
    assert repo.tree({b"a": b"same"}) == tree
    assert git_fixture.git(repo.path, "cat-file", "blob", oid) == b"same"
    calls, original = [], git_fixture.git

    def record(path, *args, **kwargs):
        calls.append(args)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(git_fixture, "git", record)
    assert repo.blob(b"same") == oid
    assert calls[0][:1] == ("hash-object",)


@pytest.mark.parametrize("wrap", [bytearray, memoryview])
def test_fixture_cache_keeps_byteslike_inputs_and_observes_mutated_content(
    tmp_path, wrap
):
    repo = git_fixture.FixtureRepo(tmp_path / "one.git")
    source = bytearray(b"first")
    raw = wrap(source)
    first = repo.blob(raw)
    assert repo.tree({b"a": raw})
    source[:] = b"later"
    later = repo._tree_blob(wrap(source))
    assert git_fixture.git(repo.path, "cat-file", "blob", first) == b"first"
    assert git_fixture.git(repo.path, "cat-file", "blob", later) == b"later"
    assert later != first
