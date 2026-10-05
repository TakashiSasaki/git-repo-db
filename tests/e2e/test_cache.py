from repo_catalog.config import load, serialize
from tests.support.cli import pages, run


def expire(state):
    cfg = load(state)
    cfg["cache"]["ttl_seconds"] = 0
    (state / "catalog.toml").write_text(serialize(cfg))


def test_gc_modes(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    expire(state)
    before = pages(state, "search", "code", "--literal", "認証")
    dry = run(state, "cache", "gc")
    assert dry["data"]["dry_run"]
    assert list((state / "cache").rglob("HEAD"))
    actual = run(state, "cache", "gc", "--apply")
    assert all(r["action"] == "evicted" for r in actual["data"]["entries"])
    assert not list((state / "cache").rglob("HEAD"))
    assert pages(state, "search", "code", "--literal", "認証") == before
