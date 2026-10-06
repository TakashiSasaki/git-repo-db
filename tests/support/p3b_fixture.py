"""Disposable identity graphs and authentic reviewed P3A preparation.

The git export and fixture writes happen in the pytest parent, before entering
the dedicated guarded converter. No source evidence or old receipts are
relabelled to resemble a predecessor.
"""

import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

from scripts.conversion import archive, source
from scripts.conversion.common import DESIGN, ROOT
from tests.support.operational_source import (
    add_operational_indexes,
    make_operational_source,
)

REVIEWED_P3A = "e40430e3f38d3339d67017a04262445f9415a8ec"
REVIEWED_CONVERTER = "f7aa4b38bf91e95173a7c832b016c7add6c46334a9854e652fdea3a39b458362"
STAMP = "2025-01-02T03:04:05Z"
LATER = "2025-06-07T08:09:10+00:00"
IDS = {
    name: f"00000000-0000-4000-8000-{number:012d}"
    for number, name in enumerate(
        (
            "instance",
            "other_instance",
            "source",
            "other_source",
            "local_source",
            "repo",
            "mirror",
            "local_repo",
            "endpoint",
            "ssh_endpoint",
            "mirror_endpoint",
            "local_endpoint",
            "inventory",
            "job",
            "run",
            "mirror_run",
        ),
        101,
    )
}
SHARED_URL = "https://synthetic.invalid/same/repo.git"
SHARED_NAME = "same/repo 日本語"


def export_reviewed(destination):
    """Export actual reviewed code/resources outside the guarded worker."""
    destination = Path(destination)
    destination.mkdir()
    exported = subprocess.run(
        [
            "git",
            "archive",
            REVIEWED_P3A,
            "scripts/conversion",
            "scripts/offline_convert.py",
            "scripts/schema_audit.py",
            "scripts/schema_contract.py",
            "docs/schema-hardening",
            "src/repo_catalog/resources/migrations",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=30,
    )
    with tarfile.open(fileobj=io.BytesIO(exported.stdout)) as bundle:
        bundle.extractall(destination, filter="data")
    return destination


def cli(action, workspace, *arguments, expected=0, root=None):
    """Execute the authentic old or current dedicated guarded CLI."""
    root = Path(root or ROOT)
    child_env = dict(os.environ)
    minimum = bool(child_env.get("TEST_SQLITE_MINIMUM")) or (
        sqlite3.sqlite_version_info < (3, 46, 1)
    )
    if minimum:
        child_env["TEST_SQLITE_MINIMUM"] = "3.46.1"
        # Load the separately audited binding before sqlite3 import. The
        # exported old converter stays byte-exact; no artifact is copied into
        # its source tree or included in its converter fingerprint.
        bootstrap = (
            "import runpy;"
            f"runpy.run_path({str(ROOT / 'scripts/sqlite_minimum.py')!r})['activate']();"
            "runpy.run_path('scripts/offline_convert.py',run_name='__main__')"
        )
        command = [sys.executable, "-c", bootstrap]
    else:
        command = [sys.executable, "scripts/offline_convert.py"]
    result = subprocess.run(
        [*command, action, "--work-dir", str(workspace), *map(str, arguments)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        env=child_env,
    )
    assert result.returncode == expected, (result.stdout, result.stderr)
    return json.loads(result.stdout if expected == 0 else result.stderr)


def make_identity_source(state_dir, *, derived=False):
    """Full v2 schema, separate identities despite equal URL/name/OID."""
    database, cache = make_operational_source(state_dir)
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executemany(
            "INSERT INTO service_instances VALUES(?,?,?,?,?,?,?)",
            [
                (
                    IDS["instance"],
                    "github",
                    "synthetic forge 日本語",
                    "https://synthetic.invalid",
                    "https://synthetic.invalid/api",
                    '{ "original": "service", "nullable": null }',
                    STAMP,
                ),
                (IDS["other_instance"], "git", "local forge", None, None, "{}", STAMP),
            ],
        )
        db.executemany(
            "INSERT INTO sources VALUES(?,?,?,?,?)",
            [
                (
                    IDS["source"],
                    "github",
                    "inventory 日本語",
                    '{ "owner": "same", "nullable": null }',
                    IDS["instance"],
                ),
                (
                    IDS["other_source"],
                    "github",
                    "second inventory",
                    '{"owner":"second"}',
                    IDS["instance"],
                ),
                (
                    IDS["local_source"],
                    "local-git",
                    "original mount spelling",
                    '{"url":"file:///synthetic/../mount/repo.git"}',
                    None,
                ),
            ],
        )
        db.executemany(
            "INSERT INTO repositories VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    IDS[name],
                    IDS["source"],
                    "synthetic.invalid",
                    native,
                    SHARED_NAME,
                    SHARED_URL,
                    '{ "preserved": "repository", "nullable": null }',
                    IDS["run" if name == "repo" else "mirror_run"],
                )
                for name, native in (("repo", "401"), ("mirror", "402"))
            ]
            + [
                (
                    IDS["local_repo"],
                    IDS["local_source"],
                    "local",
                    IDS["local_source"],
                    "mount/repo",
                    "file:///synthetic/../mount/repo.git",
                    "{}",
                    None,
                )
            ],
        )
        db.executemany(
            "INSERT INTO repository_bindings VALUES(?,?,?,?,?)",
            [
                (IDS[name], IDS["instance"], native, '{ "native": true }', STAMP)
                for name, native in (("repo", "401"), ("mirror", "402"))
            ]
            + [(IDS["local_repo"], IDS["other_instance"], None, "{}", STAMP)],
        )
        db.executemany(
            "INSERT INTO repository_endpoints VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    IDS["endpoint"],
                    IDS["repo"],
                    SHARED_URL,
                    "https",
                    None,
                    1,
                    "{}",
                    STAMP,
                ),
                (
                    IDS["ssh_endpoint"],
                    IDS["repo"],
                    "ssh://git@synthetic.invalid/same/repo",
                    "ssh",
                    "alternate 日本語",
                    0,
                    '{ "nullable": null }',
                    LATER,
                ),
                (
                    IDS["mirror_endpoint"],
                    IDS["mirror"],
                    SHARED_URL,
                    "https",
                    "mirror",
                    1,
                    "{}",
                    STAMP,
                ),
                (
                    IDS["local_endpoint"],
                    IDS["local_repo"],
                    "file:///synthetic/../mount/repo.git",
                    "file",
                    None,
                    0,
                    "{}",
                    STAMP,
                ),
            ],
        )
        db.executemany(
            "INSERT INTO source_repositories VALUES(?,?,?,?)",
            [
                (IDS["source"], IDS["repo"], STAMP, LATER),
                (IDS["other_source"], IDS["repo"], LATER, LATER),
                (IDS["source"], IDS["mirror"], STAMP, STAMP),
                (IDS["local_source"], IDS["local_repo"], STAMP, LATER),
            ],
        )
        db.executemany(
            "INSERT INTO repository_names VALUES(?,?,?)",
            [
                (IDS["repo"], SHARED_NAME, STAMP),
                (IDS["mirror"], SHARED_NAME, LATER),
                (IDS["repo"], "older/original 日本語", STAMP),
            ],
        )
        db.execute(
            "INSERT INTO inventory_runs VALUES(?,?,?,?,?,?)",
            (IDS["inventory"], IDS["source"], "partial", '{ "page": 2 }', LATER, None),
        )
        db.execute(
            "INSERT INTO jobs VALUES(?,'sync','{}','complete',1,NULL,'{}',NULL,?,?)",
            (IDS["job"], STAMP, LATER),
        )
        db.execute(
            "INSERT INTO git_objects VALUES(71,'sha1',?,'commit',4,0)", (b"c" * 20,)
        )
        for name, run_name in (("repo", "run"), ("mirror", "mirror_run")):
            db.execute(
                "INSERT INTO collection_runs(id,job_id,repo_id,generation,attempt,state,"
                "started_at,kind) VALUES(?,?,?,1,1,'published',?,'git')",
                (IDS[run_name], IDS["job"], IDS[name], STAMP),
            )
            db.execute(
                "INSERT INTO snapshots VALUES(?,?,?,1,1,?)",
                (IDS[run_name], IDS[run_name], IDS[name], STAMP),
            )
            db.execute(
                "INSERT INTO repository_object_sources VALUES(?,71,?)",
                (IDS[name], IDS[run_name]),
            )
    if derived:
        add_operational_indexes(database, kinds=("code", "pr", "commits"), analyze=True)
    return database, cache


def authentic_p3a(reviewed_root, database, cache, workspace, *, representative=True):
    cli(
        "seal",
        workspace,
        "--source",
        database,
        "--source-cache",
        cache,
        root=reviewed_root,
    )
    options = ["--batch-size", "2"]
    if representative:
        options.append("--representative-repositories")
    result = cli("archive", workspace, *options, root=reviewed_root)
    assert result["archive_complete"]
    receipt = cli("handoff", workspace, root=reviewed_root)
    assert cli("verify-phase", workspace, root=reviewed_root) == {
        **receipt,
        "new_phase": False,
    }
    with source.readonly(workspace / "target.sqlite3") as db:
        runs = db.execute("SELECT manifest FROM conversion_runs").fetchall()
        assert len(runs) == 2
        for row in runs:
            manifest = json.loads(row[0])
            assert (
                manifest.get("signatures", manifest)["converter_sha256"]
                == REVIEWED_CONVERTER
            )
    return receipt


def parent_snapshot(workspace):
    """All immutable predecessor rows, including diagnostic event times."""
    with source.readonly(workspace / "target.sqlite3") as db:
        runs = list(
            db.execute(
                "SELECT * FROM conversion_runs WHERE parser_version IN ('p2-archive/1','p3a-handoff/1')"
            )
        )
        run_ids = [row["id"] for row in runs]
        return {
            "conversion_runs": [tuple(row) for row in runs],
            **{
                name: [
                    tuple(row)
                    for row in db.execute(f"SELECT * FROM {name} ORDER BY 1,2")
                ]
                for name in ("conversion_sources", "legacy_records", "legacy_values")
            },
            **{
                name: [
                    tuple(row)
                    for row in db.execute(
                        f"SELECT * FROM {name} WHERE run_id IN (?,?) ORDER BY id",
                        run_ids,
                    )
                ]
                for name in ("conversion_batches", "validation_results")
            },
            "id_mappings": [
                tuple(row)
                for row in db.execute(
                    "SELECT * FROM id_mappings WHERE reason='P2 representative repository; preserve local ID' ORDER BY id"
                )
            ],
        }


def assert_exact_archive(database, workspace):
    tables = {
        row["table"]
        for row in json.loads((DESIGN / "conversion-contract.json").read_bytes())[
            "source_columns"
        ]
    }
    with (
        source.readonly(database) as src,
        source.readonly(workspace / "target.sqlite3") as db,
    ):
        count = 0
        for table in tables:
            for record in archive.rows(src, table):
                saved = db.execute(
                    "SELECT id,row_sha256 FROM legacy_records WHERE source_table=? AND source_key=?",
                    (table, record.key),
                ).fetchone()
                assert saved is not None and saved[1] == record.row_sha256
                assert sorted(
                    tuple(row)
                    for row in db.execute(
                        "SELECT column_name,storage_type,value_bytes FROM legacy_values WHERE record_id=?",
                        (saved[0],),
                    )
                ) == sorted(record.values)
                count += 1
        assert db.execute("SELECT count(*) FROM legacy_records").fetchone()[0] == count
