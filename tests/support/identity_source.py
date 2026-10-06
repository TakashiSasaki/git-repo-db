"""Disposable normalized v2 identity graphs for catalog3 salvage acceptance."""

import sqlite3

from tests.support.operational_source import (
    add_operational_indexes,
    make_operational_source,
)

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
