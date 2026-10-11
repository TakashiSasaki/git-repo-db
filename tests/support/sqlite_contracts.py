"""Assertions for the fresh catalog's explicitly retired tables."""


def assert_absent_tables(db, *tables):
    actual = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
    }
    assert not actual.intersection(tables)
