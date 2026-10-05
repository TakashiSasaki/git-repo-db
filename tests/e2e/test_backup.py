from tests.support.cli import pages, run


def test_restore_new_state(catalog, tmp_path):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    run(state, "index", "rebuild")
    before = pages(state, "search", "code", "--literal", "認証")
    cursor = run(state, "search", "code", "--literal", "認証", "--limit", 1)["data"][
        "page"
    ]["next_cursor"]
    backup = tmp_path / "backup.sqlite3"
    original = run(state, "db", "backup", "--output", backup)
    restored = tmp_path / "restored"
    result = run(restored, "db", "restore", "--input", backup)
    assert result["catalog"]["db_instance_id"] != original["catalog"]["db_instance_id"]
    assert pages(restored, "search", "code", "--literal", "認証") == before
    assert pages(state, "search", "code", "--literal", "認証") == before
    assert (
        run(
            restored,
            "search",
            "code",
            "--literal",
            "認証",
            "--cursor",
            cursor,
            expected=4,
        )["error"]["code"]
        == "STALE_CURSOR"
    )
    assert not list((restored / "cache").rglob("HEAD"))
    run(restored, "db", "restore", "--input", backup, expected=2)
