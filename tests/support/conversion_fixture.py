"""Deliberately inconsistent synthetic v2 evidence, never user data."""

import hashlib
import sqlite3
from pathlib import Path

from scripts.conversion.common import ROOT

STAMP = "2026-01-01T00:00:00Z"
REPO_ID = "00000000-0000-4000-8000-000000000001"


def make_source(path):
    db = sqlite3.connect(path)
    for version, sql_path in enumerate(
        sorted((ROOT / "src/repo_catalog/resources/migrations").glob("*.sql")), 1
    ):
        db.executescript(sql_path.read_text())
        db.execute(
            "INSERT INTO schema_migrations VALUES(?,?,?)",
            (version, hashlib.sha256(sql_path.read_bytes()).hexdigest(), STAMP),
        )
        db.commit()
    db.execute(
        "INSERT INTO catalog_meta VALUES(1,?,0,2)",
        ("00000000-0000-4000-8000-000000000002",),
    )
    # Exercise every source column, including values that normal code would not
    # accept. The converter must archive them, not repair or discard them.
    db.execute("PRAGMA ignore_check_constraints=ON")
    triggers = list(
        db.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger'")
    )
    for name, _ in triggers:
        db.execute(f'DROP TRIGGER "{name}"')
    tables = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    for table in tables:
        if table in {"catalog_meta", "schema_migrations"}:
            continue
        columns = list(db.execute(f'PRAGMA table_xinfo("{table}")'))
        values = [
            {
                "INTEGER": 1,
                "REAL": 1.25,
                "TEXT": f"synthetic-{table}-{c[1]}",
                "BLOB": b"\x00\xff",
            }[c[2]]
            for c in columns
        ]
        db.execute(
            f'INSERT INTO "{table}" VALUES({",".join("?" for _ in values)})', values
        )
    db.execute(
        "UPDATE repositories SET id=?,name='synthetic/repo',metadata='{}'", (REPO_ID,)
    )
    db.execute(
        "UPDATE contents SET raw_text=NULL,text_state='eligible',created_at=?", (STAMP,)
    )
    db.execute("UPDATE git_objects SET verified=9")
    db.execute(
        "UPDATE jobs SET state='unrecognized',created_at=?,updated_at=?", (STAMP, STAMP)
    )
    db.execute("UPDATE sources SET name=CAST(x'fffe00' AS TEXT)")
    db.execute(
        "UPDATE collections SET id='partial',state='partial',cursor='page-2',observed_at=?",
        (STAMP,),
    )
    db.execute(
        "INSERT INTO collections VALUES('complete',NULL,?,'comments','missing-job','complete','{}',NULL,?,NULL)",
        (REPO_ID, STAMP),
    )
    db.execute(
        "UPDATE api_responses SET body=?,payload_sha256=?",
        (
            b'{"synthetic_pending":true}',
            hashlib.sha256(b'{"synthetic_pending":true}').digest(),
        ),
    )
    db.execute("DELETE FROM document_versions")
    db.execute("DELETE FROM resource_observations")
    for version, body in ((1, "A"), (2, "B"), (3, "A")):
        # Two different documents/versions share bytes; A->B->A keeps distinct
        # historical observations even if the original version is reused.
        document = "doc-a" if version < 3 else "doc-b"
        db.execute(
            "INSERT INTO document_versions VALUES(?,?,?,?)",
            (version, document, body, hashlib.sha256(body.encode()).digest()),
        )
    for occurrence, version in enumerate((1, 2, 1), 1):
        db.execute(
            "INSERT INTO resource_observations VALUES(?,?,?, ?,?, '{}')",
            (
                occurrence,
                "doc-a",
                version,
                f"collection-{occurrence}",
                f"2026-01-0{occurrence}T00:00:00Z",
            ),
        )
    db.execute("DELETE FROM ref_observations")
    for ref in (b"refs/heads/a", b"refs/heads/b"):
        db.execute(
            "INSERT INTO ref_observations VALUES('snapshot',?,'branch','sha1',?,NULL,'commit')",
            (ref, b"1" * 20),
        )
    for _, sql in triggers:
        db.execute(sql)
    db.commit()
    db.close()
    cache = Path(path).parent / "source-cache"
    (cache / "objects").mkdir(parents=True)
    (cache / "objects/evidence").write_bytes(b"synthetic-local-git-evidence")
    (cache / "config").write_text(
        '[remote "origin"]\nurl = https://synthetic.invalid/repo.git\npromisor = true\n'
    )
    return cache
