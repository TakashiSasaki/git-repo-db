"""Disposable operational v2 evidence for catalog3 salvage acceptance.

Fixture creation performs SQLite/file writes only. All names, payloads and
objects are synthetic; no Git command, API call or user cache is involved.
Known blob bytes that are absent from the source exist only in this builder,
so converters must report their absence instead of reacquiring them.
"""

import base64
import hashlib
import json
import sqlite3
from pathlib import Path

from tests.support.identity_source import IDS as IDENTITY_IDS
from tests.support.identity_source import make_identity_source
from tests.support.operational_source import add_operational_indexes

IDS = {
    **IDENTITY_IDS,
    **{
        name: f"00000000-0000-4000-8000-{number:012d}"
        for number, name in (
            (301, "pr"),
            (302, "document_a"),
            (303, "document_same"),
            (304, "document_review"),
            (305, "document_line"),
            (306, "thread"),
            (307, "review"),
            (308, "api_job_a"),
            (309, "api_job_b"),
            (310, "api_job_c"),
            (311, "api_job_partial"),
            (321, "comments_a"),
            (322, "comments_b"),
            (323, "comments_return_a"),
            (324, "comments_partial"),
            (325, "commits_complete"),
            (326, "files_complete"),
            (327, "commits_partial"),
            (328, "files_partial"),
            (329, "reviews"),
            (330, "review_comments"),
            (331, "timeline"),
            (332, "threads"),
            (340, "pr_run"),
        )
    },
}
STAMPS = (
    "2026-02-01T03:04:05Z",
    "2026-02-02T03:04:05Z",
    "2026-02-03T03:04:05Z",
    "2026-02-04T03:04:05Z",
)
OBJECT_IDS = {
    "parent_a": 71,
    "parent_b": 72,
    "merge": 73,
    "root_tree": 74,
    "nested_tree": 75,
    "available_blob": 76,
    "missing_blob": 77,
    "binary_blob": 78,
    "tag": 79,
}
CONTENT_IDS = {"available": 201, "missing": 202, "binary": 203}
RAW_PATHS = (b"src/app.py", b"src/raw-\xff.txt", b"lost.txt", b"binary.dat")
REFS = (b"refs/heads/main", b"refs/heads/alias", b"refs/tags/v1")
AVAILABLE_TEXT = "def integrated_answer():\n    return 'searchable sentinel 日本語'\n"
SAVED_EARLY_BODY = "saved early-page 日本語"
SAVED_LATER_BODY = "saved later-page 日本語"
SAVED_PAGE_STAMPS = (
    STAMPS[3],
    "2026-02-04T03:04:06Z",
    "2026-02-04T03:04:07Z",
)
SAVED_BODY_SEQUENCE = (SAVED_EARLY_BODY, SAVED_LATER_BODY, SAVED_EARLY_BODY)
API_BASE = "https://synthetic.invalid/api/repos/same/repo"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _git_oid(kind, payload):
    return hashlib.sha1(f"{kind} {len(payload)}\0".encode() + payload).digest()


def _tree(entries):
    return b"".join(
        f"{mode:o} ".encode() + name + b"\0" + oid for name, mode, oid in entries
    )


def _objects():
    """Build real Git serialization without running Git."""
    payloads = {
        "available_blob": AVAILABLE_TEXT.encode(),
        "missing_blob": b"original unavailable blob evidence\n",
        "binary_blob": b"\x00\xff\x01synthetic binary\x00",
    }
    oids = {name: _git_oid("blob", payload) for name, payload in payloads.items()}
    nested = (
        (b"app.py", 0o100644, oids["available_blob"]),
        (b"raw-\xff.txt", 0o100644, oids["available_blob"]),
    )
    payloads["nested_tree"] = _tree(nested)
    oids["nested_tree"] = _git_oid("tree", payloads["nested_tree"])
    root = (
        (b"binary.dat", 0o100644, oids["binary_blob"]),
        (b"lost.txt", 0o100644, oids["missing_blob"]),
        (b"src", 0o40000, oids["nested_tree"]),
    )
    payloads["root_tree"] = _tree(root)
    oids["root_tree"] = _git_oid("tree", payloads["root_tree"])
    for name in ("parent_a", "parent_b", "merge"):
        headers = b"tree " + oids["root_tree"].hex().encode()
        if name == "merge":
            for parent in ("parent_a", "parent_b"):
                headers += b"\nparent " + oids[parent].hex().encode()
        headers += (
            b"\nauthor Synthetic Author <author@synthetic.invalid> 1769907845 +0000"
            b"\ncommitter Synthetic Committer <committer@synthetic.invalid> 1769907845 +0000"
        )
        message = f"synthetic {name} searchable commit 日本語\n".encode()
        payloads[name] = headers + b"\n\n" + message
        oids[name] = _git_oid("commit", payloads[name])
    payloads["tag"] = (
        b"object "
        + oids["merge"].hex().encode()
        + b"\ntype commit\ntag v1\n"
        + b"tagger Synthetic Tagger <tagger@synthetic.invalid> 1769907845 +0000\n\n"
        + b"synthetic annotated release\n"
    )
    oids["tag"] = _git_oid("tag", payloads["tag"])
    return payloads, oids, {"root_tree": root, "nested_tree": nested}


OBJECT_PAYLOADS, OIDS, TREE_ENTRIES = _objects()


def _git_records(db):
    for name, object_id in OBJECT_IDS.items():
        kind = (
            "blob"
            if name.endswith("blob")
            else "tree"
            if name.endswith("tree")
            else "tag"
            if name == "tag"
            else "commit"
        )
        values = (object_id, "sha1", OIDS[name], kind, len(OBJECT_PAYLOADS[name]), 0)
        if name == "parent_a":
            db.execute(
                "UPDATE git_objects SET object_format=?,oid=?,type=?,size=?,verified=? WHERE id=?",
                (*values[1:], object_id),
            )
        else:
            db.execute("INSERT INTO git_objects VALUES(?,?,?,?,?,?)", values)
        db.execute(
            "INSERT OR IGNORE INTO repository_object_sources VALUES(?,?,?)",
            (IDS["repo"], object_id, IDS["run"]),
        )
    for name in ("parent_a", "parent_b", "merge"):
        headers, message = OBJECT_PAYLOADS[name].split(b"\n\n", 1)
        db.execute(
            "INSERT INTO commits VALUES(?,?,?,?,?)",
            (
                OBJECT_IDS[name],
                OBJECT_IDS["root_tree"],
                headers,
                message,
                '{"synthetic":true}',
            ),
        )
    db.executemany(
        "INSERT INTO commit_parents VALUES(?,?,?)",
        [(73, 0, 71), (73, 1, 72)],
    )
    children = {oid: OBJECT_IDS[name] for name, oid in OIDS.items()}
    for name, entries in TREE_ENTRIES.items():
        tree_id = OBJECT_IDS[name]
        db.execute("INSERT INTO root_manifests VALUES(?,1)", (tree_id,))
        db.executemany(
            "INSERT INTO tree_entries VALUES(?,?,?,?,?,?)",
            [
                (tree_id, raw_name, mode, "sha1", oid, children[oid])
                for raw_name, mode, oid in entries
            ],
        )
    db.execute(
        "INSERT INTO tag_objects VALUES(?,?,?)", (79, 73, OBJECT_PAYLOADS["tag"])
    )
    for path, name in zip(
        RAW_PATHS,
        ("available_blob", "available_blob", "missing_blob", "binary_blob"),
        strict=True,
    ):
        db.execute(
            "INSERT INTO root_manifest_entries VALUES(?,?,?,?,?,?)",
            (74, path, 0o100644, OBJECT_IDS[name], "sha1", OIDS[name]),
        )
    for path in (b"app.py", b"raw-\xff.txt"):
        db.execute(
            "INSERT INTO root_manifest_entries VALUES(?,?,?,?,?,?)",
            (75, path, 0o100644, 76, "sha1", OIDS["available_blob"]),
        )
    for name, content_name, state in (
        ("available_blob", "available", "eligible"),
        ("missing_blob", "missing", "eligible"),
        ("binary_blob", "binary", "non_utf8"),
    ):
        content_id = CONTENT_IDS[content_name]
        payload = OBJECT_PAYLOADS[name]
        db.execute(
            "INSERT INTO contents VALUES(?,?,?,?,?)",
            (
                content_id,
                len(payload),
                AVAILABLE_TEXT if content_name == "available" else None,
                state,
                STAMPS[0],
            ),
        )
        db.execute(
            "INSERT INTO blob_content_map VALUES(?,?,?)",
            (OBJECT_IDS[name], content_id, IDS["run"]),
        )
        for algorithm in ("md5", "sha1", "sha256"):
            db.execute(
                "INSERT INTO content_digests VALUES(?,?,?,?,?,?)",
                (
                    content_id,
                    "raw-content-v1",
                    algorithm,
                    hashlib.new(algorithm, payload).digest(),
                    STAMPS[0],
                    "v1",
                ),
            )
    db.execute(
        "INSERT INTO content_locations VALUES(?,'durable-content',?,NULL,'available')",
        (201, "sqlite:contents/201"),
    )
    refs = []
    for ref in REFS:
        tag = ref == REFS[2]
        target = OIDS["tag"] if tag else OIDS["merge"]
        db.execute(
            "INSERT INTO ref_observations VALUES(?,?,?,?,?,?,?)",
            (
                IDS["run"],
                ref,
                "tag" if tag else "head",
                "sha1",
                target,
                OIDS["merge"] if tag else None,
                "tag" if tag else "commit",
            ),
        )
        refs.append(
            {
                "name": ref.decode(),
                "name_b64": base64.b64encode(ref).decode(),
                "oid": target.hex(),
                "type": "tag" if tag else "commit",
                "peeled": OIDS["merge"].hex() if tag else None,
            }
        )
    db.execute(
        "UPDATE collection_runs SET object_format='sha1',refs_at=?,ended_at=?,roots_manifest=?,endpoint_id=?,endpoint_url=? WHERE id=?",
        (
            STAMPS[0],
            STAMPS[0],
            _json(refs),
            IDS["endpoint"],
            "https://synthetic.invalid/same/repo.git",
            IDS["run"],
        ),
    )
    db.executemany(
        "INSERT INTO acquisition_roots VALUES(?,?,?,?,?,?,?,?,?,?)",
        [
            (
                401,
                IDS["run"],
                IDS["repo"],
                "sha1",
                OIDS["merge"],
                "head",
                None,
                None,
                None,
                1,
            ),
            (
                402,
                IDS["run"],
                IDS["repo"],
                "sha1",
                OIDS["tag"],
                "tag",
                None,
                None,
                None,
                1,
            ),
        ],
    )
    for component, state in (
        ("structure", "complete"),
        ("digests", "complete"),
        ("heads-text", "partial"),
        ("refs", "complete"),
    ):
        db.execute(
            "INSERT INTO coverage_components VALUES(?,?,?,?)",
            (IDS["run"], component, state, _json({"synthetic": True})),
        )


def _collection(db, name, kind, job_name, stamp, *, partial=False):
    cursor = f"{API_BASE}/{name}?page=2" if partial else None
    db.execute(
        "INSERT INTO collections VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            IDS[name],
            IDS["pr"],
            IDS["repo"],
            kind,
            IDS[job_name],
            "partial" if partial else "complete",
            _json(
                {
                    "repo_id": IDS["repo"],
                    "api_version": "2022-11-28",
                    "principal": "synthetic-user",
                    "parser_version": "v1",
                    "profile": "fixture-v1",
                }
            ),
            cursor,
            stamp,
            "synthetic interruption after saved page" if partial else None,
        ),
    )


def _page(db, collection, values, stamp, *, ordinal=0, partial=False):
    payload = _json(values).encode()
    sha = hashlib.sha256(payload).digest()
    db.execute(
        "INSERT OR IGNORE INTO api_responses(payload_sha256,body) VALUES(?,?)",
        (sha, payload),
    )
    response_id = db.execute(
        "SELECT id FROM api_responses WHERE payload_sha256=? AND body=?", (sha, payload)
    ).fetchone()[0]
    db.execute(
        "INSERT INTO collection_pages VALUES(?,?,?,?,?,?)",
        (
            IDS[collection],
            ordinal,
            response_id,
            _json(
                {
                    "url": f"{API_BASE}/{collection}?page={ordinal + 1}",
                    "api_version": "2022-11-28",
                    "parser_version": "v1",
                }
            ),
            f"{API_BASE}/{collection}?page={ordinal + 2}" if partial else None,
            stamp,
        ),
    )


def _comment(provider, body):
    return {
        "id": provider,
        "node_id": f"NODE_{provider}",
        "body": body,
        "user": {"login": "synthetic-author"},
        "html_url": f"https://synthetic.invalid/same/repo/issues/7#comment-{provider}",
    }


def _document(db, ident, kind, provider, version, body):
    db.execute(
        "INSERT INTO pr_documents VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            ident,
            IDS["pr"],
            kind,
            str(provider),
            f"NODE_{provider}",
            "synthetic-author",
            f"https://synthetic.invalid/same/repo/issues/7#comment-{provider}",
            version,
            0,
            _json({"synthetic": True}),
        ),
    )
    db.execute(
        "INSERT INTO document_versions VALUES(?,?,?,?)",
        (version, ident, body, hashlib.sha256(body.encode()).digest()),
    )


def _pr_records(db, scale):
    for name, stamp in zip(
        ("api_job_a", "api_job_b", "api_job_c", "api_job_partial"), STAMPS, strict=True
    ):
        db.execute(
            "INSERT INTO jobs VALUES(?,'pr','{}','complete',1,NULL,'{}',NULL,?,?)",
            (IDS[name], stamp, stamp),
        )
    db.execute(
        "INSERT INTO pull_requests VALUES(?,?,7,'PR_synthetic7',303)",
        (IDS["pr"], IDS["repo"]),
    )
    for observation, job_name, stamp, state in zip(
        (301, 302, 303),
        ("api_job_a", "api_job_b", "api_job_c"),
        STAMPS[:3],
        ("open", "closed", "open"),
        strict=True,
    ):
        payload = {
            "id": 701,
            "number": 7,
            "node_id": "PR_synthetic7",
            "title": "Synthetic integrated PR 日本語",
            "body": "PR description original",
            "state": state,
            "head": {"sha": OIDS["merge"].hex()},
            "base": {"sha": OIDS["parent_a"].hex()},
            "commits": 1,
            "changed_files": 1,
        }
        db.execute(
            "INSERT INTO pr_observations VALUES(?,?,?,?,?,1)",
            (observation, IDS["pr"], IDS[job_name], stamp, _json(payload)),
        )
    for collection, kind, job, stamp, partial in (
        ("comments_a", "issue-comment", "api_job_a", STAMPS[0], False),
        ("comments_b", "issue-comment", "api_job_b", STAMPS[1], False),
        ("comments_return_a", "issue-comment", "api_job_c", STAMPS[2], False),
        ("comments_partial", "issue-comment", "api_job_partial", STAMPS[3], True),
        ("commits_complete", "pr-commits", "api_job_a", STAMPS[0], False),
        ("files_complete", "pr-files", "api_job_a", STAMPS[0], False),
        ("commits_partial", "pr-commits", "api_job_b", STAMPS[1], True),
        ("files_partial", "pr-files", "api_job_b", STAMPS[1], True),
        ("reviews", "review", "api_job_a", STAMPS[0], False),
        ("review_comments", "review-comment", "api_job_a", STAMPS[0], False),
        ("timeline", "timeline", "api_job_a", STAMPS[0], False),
        ("threads", "threads", "api_job_a", STAMPS[0], False),
    ):
        _collection(db, collection, kind, job, stamp, partial=partial)
    _document(db, IDS["document_a"], "issue-comment", 901, 301, "A")
    db.execute(
        "INSERT INTO document_versions VALUES(302,?,'B',?)",
        (IDS["document_a"], hashlib.sha256(b"B").digest()),
    )
    _document(db, IDS["document_same"], "issue-comment", 903, 303, "A")
    _document(db, IDS["document_review"], "review", 1001, 304, "Review original 日本語")
    _document(
        db, IDS["document_line"], "review-comment", 1002, 305, "Inline original 日本語"
    )
    for observation, doc_name, version, collection, stamp in (
        (301, "document_a", 301, "comments_a", STAMPS[0]),
        (302, "document_a", 302, "comments_b", STAMPS[1]),
        (303, "document_a", 301, "comments_return_a", STAMPS[2]),
        (304, "document_same", 303, "comments_a", STAMPS[0]),
        (305, "document_review", 304, "reviews", STAMPS[0]),
        (306, "document_line", 305, "review_comments", STAMPS[0]),
    ):
        db.execute(
            "INSERT INTO resource_observations VALUES(?,?,?,?,?,?)",
            (
                observation,
                IDS[doc_name],
                version,
                IDS[collection],
                stamp,
                _json({"source_observation": observation}),
            ),
        )
        db.execute(
            "INSERT INTO collection_memberships VALUES(?,?,?)",
            (IDS[collection], IDS[doc_name], 1 if observation == 304 else 0),
        )
    first_comments = [_comment(901, "A"), _comment(903, "A")]
    for index in range(1, scale):
        ident = f"00000000-0000-4000-8000-{10000 + index:012d}"
        version = 5000 + index
        provider = 20000 + index
        body = f"scaled searchable synthetic document {index} 日本語"
        _document(db, ident, "issue-comment", provider, version, body)
        db.execute(
            "INSERT INTO resource_observations VALUES(?,?,?,?,?,?)",
            (5000 + index, ident, version, IDS["comments_a"], STAMPS[0], "{}"),
        )
        db.execute(
            "INSERT INTO collection_memberships VALUES(?,?,?)",
            (IDS["comments_a"], ident, index + 1),
        )
        first_comments.append(_comment(provider, body))
    _page(db, "comments_a", first_comments, STAMPS[0])
    _page(db, "comments_b", [_comment(901, "B")], STAMPS[1])
    _page(db, "comments_return_a", [_comment(901, "A")], STAMPS[2])
    # Saved provider902 A->B->A pages have no normalized rows. Replay must
    # preserve separate page observations and leave the collection partial.
    _page(
        db,
        "comments_partial",
        [_comment(901, "A"), _comment(902, SAVED_EARLY_BODY)],
        STAMPS[3],
        partial=True,
    )
    for ordinal in (1, 2):
        _page(
            db,
            "comments_partial",
            [_comment(902, SAVED_BODY_SEQUENCE[ordinal])],
            SAVED_PAGE_STAMPS[ordinal],
            ordinal=ordinal,
            partial=True,
        )
    db.execute(
        "UPDATE collections SET cursor=? WHERE id=?",
        (f"{API_BASE}/comments_partial?page=4", IDS["comments_partial"]),
    )
    db.execute(
        "INSERT INTO collection_runs(id,job_id,repo_id,generation,attempt,state,started_at,refs_at,ended_at,object_format,kind,roots_manifest,request,endpoint_id,endpoint_url) VALUES(?,?,?,1,1,'published',?,?,?,'sha1','pr',?,'{}',?,?)",
        (
            IDS["pr_run"],
            IDS["api_job_a"],
            IDS["repo"],
            STAMPS[0],
            STAMPS[0],
            STAMPS[0],
            _json(
                [
                    {"role": "head", "number": 7, "oid": OIDS["merge"].hex()},
                    {"role": "base", "number": 7, "oid": OIDS["parent_a"].hex()},
                ]
            ),
            IDS["endpoint"],
            "https://synthetic.invalid/same/repo.git",
        ),
    )
    for acquisition, role, name in ((403, "head", "merge"), (404, "base", "parent_a")):
        db.execute(
            "INSERT INTO acquisition_roots VALUES(?,?,?,?,?,?,?,?,?,1)",
            (
                acquisition,
                IDS["pr_run"],
                IDS["repo"],
                "sha1",
                OIDS[name],
                role,
                7,
                301,
                OIDS[name].hex(),
            ),
        )
        db.execute(
            "INSERT INTO repository_object_sources VALUES(?,?,?)",
            (IDS["repo"], OBJECT_IDS[name], IDS["pr_run"]),
        )
    commit = {
        "sha": OIDS["merge"].hex(),
        "commit": {"message": "synthetic merge searchable commit 日本語"},
    }
    file = {
        "filename": "src/app.py",
        "status": "modified",
        "sha": OIDS["available_blob"].hex(),
        "patch": "+searchable sentinel 日本語",
    }
    for code, observation, state in ((301, 301, "complete"), (302, 302, "partial")):
        db.execute(
            "INSERT INTO pr_code_observations VALUES(?,?,?,?,?,?,?)",
            (
                code,
                IDS["pr"],
                observation,
                OIDS["merge"].hex(),
                OIDS["parent_a"].hex(),
                state,
                _json(
                    {
                        "api_head_base_stable": True,
                        "provider_limits": {"commits": 250, "files": 3000},
                    }
                ),
            ),
        )
        db.execute(
            "INSERT INTO pr_commits VALUES(?,?,?,?)",
            (code, 0, OIDS["merge"].hex(), _json(commit)),
        )
        db.execute(
            "INSERT INTO pr_file_changes VALUES(?,?,?,?)",
            (code, 0, "src/app.py", _json(file)),
        )
        for role, name, acquisition in (
            ("head", "merge", 403),
            ("base", "parent_a", 404),
        ):
            db.execute(
                "INSERT INTO pr_git_links VALUES(?,?,?,?,?)",
                (code, role, "sha1", OIDS[name], acquisition if code == 301 else None),
            )
    for collection, values, stamp, partial in (
        ("commits_complete", [commit], STAMPS[0], False),
        ("files_complete", [file], STAMPS[0], False),
        ("commits_partial", [commit], STAMPS[1], True),
        ("files_partial", [file], STAMPS[1], True),
    ):
        _page(db, collection, values, stamp, partial=partial)
        resource = commit["sha"] if "commits" in collection else file["filename"]
        db.execute(
            "INSERT INTO collection_memberships VALUES(?,?,0)",
            (IDS[collection], resource),
        )
    review = {
        "id": 1001,
        "body": "Review original 日本語",
        "state": "APPROVED",
        "commit_id": OIDS["merge"].hex(),
        "submitted_at": STAMPS[0],
        "user": {"login": "synthetic-reviewer"},
    }
    thread = {
        "id": "THREAD_synthetic",
        "isResolved": False,
        "path": "src/app.py",
        "line": 2,
    }
    line = {
        "id": 1002,
        "body": "Inline original 日本語",
        "path": "src/app.py",
        "line": 2,
        "pull_request_review_id": 1001,
        "commit_id": OIDS["merge"].hex(),
        "user": {"login": "synthetic-reviewer"},
    }
    event = {
        "id": 1101,
        "event": "reopened",
        "created_at": STAMPS[2],
        "actor": {"login": "synthetic-author"},
    }
    db.execute(
        "INSERT INTO pr_reviews VALUES(?,?,?,?)",
        (IDS["review"], IDS["pr"], IDS["document_review"], _json(review)),
    )
    db.execute(
        "INSERT INTO review_threads VALUES(?,?,?,?)",
        (IDS["thread"], IDS["pr"], _json(thread), STAMPS[0]),
    )
    db.execute(
        "INSERT INTO review_comments VALUES(?,?,?)",
        (IDS["document_line"], IDS["thread"], _json(line)),
    )
    db.execute(
        "INSERT INTO pr_events VALUES(301,?,?,0,'1101',?)",
        (IDS["pr"], IDS["timeline"], _json(event)),
    )
    for collection, values in (
        ("reviews", [review]),
        ("review_comments", [line]),
        ("timeline", [event]),
        (
            "threads",
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [thread],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        }
                    }
                }
            },
        ),
    ):
        _page(db, collection, values, STAMPS[0])
    db.execute(
        "INSERT INTO collection_memberships VALUES(?,?,0)",
        (IDS["timeline"], f"{IDS['timeline']}:0"),
    )
    db.execute(
        "INSERT INTO collection_memberships VALUES(?,?,0)",
        (IDS["threads"], IDS["thread"]),
    )
    db.execute(
        "INSERT INTO coverage_components VALUES(?,'pr-documents','partial',?)",
        (IDS["repo"], _json({"reason": "saved_page_pending_normalization"})),
    )
    db.execute(
        "INSERT INTO sync_checkpoints VALUES(?,?,?)",
        (
            f"watermark:{IDS['repo']}:synthetic-user:issue-comment:2022-11-28",
            _json(
                {
                    "since": STAMPS[0],
                    "pending_cursor": "page-2",
                    "validator": 'W/"synthetic"',
                }
            ),
            STAMPS[0],
        ),
    )


def make_integrated_source(state_dir, *, derived=False, malformed=False, scale=1):
    """Return ``(database, cache)`` with operational Git and PR saved evidence.

    ``scale`` adds independently identified document/version/observation rows
    to the first saved page. ``malformed`` adds semantic defects while keeping
    the exact operational schema and saved source bytes intact. ``derived``
    includes recognized app-built FTS and SQLite ANALYZE data.
    """
    if type(scale) is not int or scale < 1:
        raise ValueError("Synthetic fixture scale must be a positive integer")
    database, cache = make_identity_source(Path(state_dir))
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA foreign_keys=ON")
        _git_records(db)
        _pr_records(db, scale)
        db.execute(
            "UPDATE inventory_runs SET scope=?,observed_at=? WHERE id=?",
            (
                _json(
                    {
                        "owner": "same",
                        "api_version": "2022-11-28",
                        "principal": "synthetic-user",
                        "cursor": "inventory-page-2",
                        "reported_total": 3,
                        "observed_repository_ids": [IDS["repo"], IDS["mirror"]],
                    }
                ),
                STAMPS[3],
                IDS["inventory"],
            ),
        )
        if malformed:
            db.execute(
                "UPDATE pr_observations SET payload='{broken saved PR payload' WHERE id=303"
            )
            db.execute(
                "UPDATE pr_code_observations SET head_oid='malformed-oid' WHERE id=302"
            )
            db.execute(
                "UPDATE content_digests SET digest=? WHERE content_id=201 AND algorithm='sha256'",
                (b"\x00" * 32,),
            )
        violations = list(db.execute("PRAGMA foreign_key_check"))
        if violations:
            raise AssertionError(f"Synthetic fixture foreign keys: {violations}")
    if derived:
        add_operational_indexes(database, kinds=("code", "pr", "commits"), analyze=True)
    return database, cache
