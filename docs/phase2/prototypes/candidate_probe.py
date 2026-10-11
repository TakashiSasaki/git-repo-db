"""Adversarial disposable model; not production schema, policy, or Exchange format.

Runs entirely on synthetic data. A seal passing only SQLite FKs is insufficient:
this validator checks typed family, exact observation digests, required child set,
contiguous members/fragments, terminal boundary and original observation times.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import uuid
from pathlib import Path

SQL = Path(__file__).with_name("candidate.sql")


def ident(number):
    return str(uuid.UUID(int=number, version=4))


def sha(body):
    return hashlib.sha256(body).digest()


def manifest(values):
    return sha(
        json.dumps(
            values, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    )


def valid_git(fmt, oid, kind, size, body):
    if fmt not in {"sha1", "sha256"} or body is None or size != len(body):
        return 0
    return int(
        hashlib.new(fmt, f"{kind} {len(body)}\0".encode() + body).digest() == oid
    )


def valid_utf8(body):
    try:
        body.decode("utf-8")
        return 1
    except (UnicodeError, AttributeError):
        return 0


def connect(path=":memory:"):
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.create_function("sha256", 1, sha, deterministic=True)
    db.create_function("valid_utf8", 1, valid_utf8, deterministic=True)
    db.create_function("valid_git", 5, valid_git, deterministic=True)
    db.executescript(SQL.read_text())
    return db


def put(db, table, **row):
    names = ",".join(row)
    placeholders = ",".join("?" for _ in row)
    db.execute(
        f"INSERT INTO {table}({names}) VALUES({placeholders})", tuple(row.values())
    )


def base(db):
    for n in (1, 2):
        put(db, "service_instances", service_uuid=ident(n), kind="github")
        put(db, "repositories", repository_uuid=ident(n + 10))
        put(db, "sources", source_uuid=ident(n + 20), service_uuid=ident(n))
        put(
            db,
            "source_repositories",
            source_uuid=ident(n + 20),
            repository_uuid=ident(n + 10),
        )
        put(
            db,
            "repository_bindings",
            binding_uuid=ident(n + 30),
            repository_uuid=ident(n + 10),
            service_uuid=ident(n),
            provider_repository_id=str(n),
        )
        put(
            db,
            "change_requests",
            change_request_id=f"pr-{n}",
            repository_uuid=ident(n + 10),
            binding_uuid=ident(n + 30),
            service_uuid=ident(n),
            provider_number=n,
            kind="pull_request",
        )
        put(
            db,
            "repository_publications",
            publication_uuid=ident(n + 40),
            repository_uuid=ident(n + 10),
            source_uuid=ident(n + 20),
            observed_at_us=100,
            module="fixture.domain",
            version="1",
        )


def pr(db, number, owner=1, clock=100, scope="provider-pr-clock"):
    state = {"title": f"title-{number}", "head_oid": bytes([number % 256]).hex() * 20}
    put(
        db,
        "change_request_observations",
        observation_uuid=ident(number + 100),
        change_request_id=f"pr-{owner}",
        repository_uuid=ident(owner + 10),
        publication_uuid=ident(owner + 40),
        observed_at_us=number,
        clock_scope=scope,
        provider_clock_us=clock,
        module="fixture.domain",
        version="1",
        state_digest=manifest(state),
        title=state["title"],
        head_oid=bytes.fromhex(state["head_oid"]),
    )
    uid = ident(number + 100)
    for path, value in state.items():
        put(
            db,
            "pr_observation_fields",
            observation_uuid=uid,
            path=path,
            state="value",
            value_json=json.dumps(value),
            origin_observation_uuid=uid,
            module="fixture.domain",
            version="1",
        )
    value = observation_digest(db, "change_request_observations", uid)
    db.execute(
        "UPDATE change_request_observations SET state_digest=? WHERE observation_uuid=?",
        (value, uid),
    )
    return uid, value


FAMILIES = {
    "pr-list": ("pr_collection_members", "change_request_observations"),
    "threads": ("thread_collection_members", "review_thread_observations"),
    "thread-comments": ("review_receipt_members", "review_resources"),
    "documents": ("document_collection_members", "document_observations"),
}


class InvalidProof(ValueError):
    pass


def observation_digest(db, table, identity):
    row = db.execute(
        f"SELECT * FROM {table} WHERE observation_uuid=?", (identity,)
    ).fetchone()
    if table == "change_request_observations":
        fields = db.execute(
            "SELECT * FROM pr_observation_fields WHERE observation_uuid=? ORDER BY path",
            (identity,),
        ).fetchall()
        scalar = {
            "title": row["title"],
            "head_oid": row["head_oid"].hex() if row["head_oid"] is not None else None,
        }
        values = []
        for cell in fields:
            origin = db.execute(
                "SELECT * FROM change_request_observations WHERE observation_uuid=?",
                (cell["origin_observation_uuid"],),
            ).fetchone()
            if (origin["change_request_id"], origin["repository_uuid"]) != (
                row["change_request_id"],
                row["repository_uuid"],
            ):
                raise InvalidProof("cross-resource field origin")
            value = None if cell["state"] == "null" else json.loads(cell["value_json"])
            if cell["path"] not in {"title", "head_oid", "body"} or (
                value is not None and not isinstance(value, str)
            ):
                raise InvalidProof("unknown or untyped domain field")
            if value is not None:
                value.encode("utf-8")
            if (
                cell["path"] == "head_oid"
                and value is not None
                and (
                    len(value) not in {40, 64}
                    or any(character not in "0123456789abcdef" for character in value)
                )
            ):
                raise InvalidProof("malformed observed OID field")
            if origin["observation_uuid"] == row["observation_uuid"]:
                if (cell["module"], cell["version"]) != (
                    origin["module"],
                    origin["version"],
                ):
                    raise InvalidProof(
                        "field parser differs from modeled actual producer"
                    )
            else:
                original_cell = db.execute(
                    "SELECT * FROM pr_observation_fields WHERE observation_uuid=? AND path=?",
                    (origin["observation_uuid"], cell["path"]),
                ).fetchone()
                if not original_cell or any(
                    original_cell[key] != cell[key]
                    for key in ("state", "value_json", "module", "version")
                ):
                    raise InvalidProof(
                        "inherited value/parser differs from originating field"
                    )
            if cell["path"] in scalar and scalar[cell["path"]] != value:
                raise InvalidProof("scalar index disagrees with canonical field cell")
            if cell["path"] in scalar:
                original_value = origin[cell["path"]]
                if isinstance(original_value, bytes):
                    original_value = original_value.hex()
                if original_value != value:
                    raise InvalidProof("field value differs from origin")
            values.append([cell["path"], cell["state"], value])
        return manifest({"scalar_index": scalar, "field_values": values})
    if table == "review_thread_observations":
        return manifest({"thread_id": row["thread_id"], "resolved": row["resolved"]})
    if table == "document_observations":
        return manifest(
            {
                "body_state": row["body_state"],
                "body_sha256": row["body_sha256"].hex()
                if row["body_sha256"] is not None
                else None,
                "author_provider_id": row["author_provider_id"],
            }
        )
    raise InvalidProof("unmodeled observation digest contract")


def validate_collection(db, collection_uuid, active=None):
    active = set() if active is None else active
    if collection_uuid in active:
        raise InvalidProof("child cycle")
    active.add(collection_uuid)
    collection = db.execute(
        "SELECT c.*,s.kind,s.change_request_id,s.thread_id FROM repository_collection_observations c JOIN repository_collection_scopes s USING(scope_uuid) WHERE collection_uuid=?",
        (collection_uuid,),
    ).fetchone()
    terminal = db.execute(
        "SELECT * FROM repository_collection_terminals WHERE collection_uuid=?",
        (collection_uuid,),
    ).fetchone()
    seal = db.execute(
        "SELECT * FROM repository_collection_seals WHERE collection_uuid=?",
        (collection_uuid,),
    ).fetchone()
    fragments = db.execute(
        "SELECT * FROM repository_collection_fragments WHERE collection_uuid=? ORDER BY ordinal",
        (collection_uuid,),
    ).fetchall()
    if not collection or not terminal or not seal or not fragments:
        raise InvalidProof("missing collection, terminal, fragment or seal")
    if collection["kind"] not in FAMILIES:
        raise InvalidProof("unmodeled collection family")
    if [p["ordinal"] for p in fragments] != list(range(terminal["last_ordinal"] + 1)):
        raise InvalidProof("skipped or extra fragment ordinal")
    member_table, observations = FAMILIES[collection["kind"]]
    for table, _ in FAMILIES.values():
        if (
            table != member_table
            and db.execute(
                f"SELECT 1 FROM {table} WHERE collection_uuid=?", (collection_uuid,)
            ).fetchone()
        ):
            raise InvalidProof("wrong member family")
    all_members, root_members = [], []
    for fragment in fragments:
        if member_table == "review_receipt_members":
            members = db.execute(
                "SELECT m.*,m.observed_state_digest state_digest FROM review_receipt_members m JOIN review_resources r ON r.change_request_id=m.change_request_id AND r.kind=m.kind AND r.provider_document_id=m.provider_document_id WHERE collection_uuid=? AND ordinal=? ORDER BY position",
                (collection_uuid, fragment["ordinal"]),
            ).fetchall()
        else:
            members = db.execute(
                f"SELECT m.*,o.state_digest actual_digest,o.change_request_id resource_pr FROM {member_table} m JOIN {observations} o USING(observation_uuid) WHERE collection_uuid=? AND ordinal=? ORDER BY position"
                if observations != "review_thread_observations"
                else "SELECT m.*,o.state_digest actual_digest,t.change_request_id resource_pr FROM thread_collection_members m JOIN review_thread_observations o USING(observation_uuid) JOIN review_threads t USING(thread_id) WHERE collection_uuid=? AND ordinal=? ORDER BY position",
                (collection_uuid, fragment["ordinal"]),
            ).fetchall()
        if [m["position"] for m in members] != list(range(len(members))):
            raise InvalidProof("skipped member position")
        rows = []
        for member in members:
            if member_table == "review_receipt_members":
                resource_pr = member["change_request_id"]
                natural = [resource_pr, member["kind"], member["provider_document_id"]]
                if member["kind"] != "review-comment":
                    raise InvalidProof("wrong current review member kind")
                if member["captured_thread_id"] != collection["thread_id"]:
                    raise InvalidProof("current receipt has wrong captured thread")
                # Immutable receipt attestation: current mutable state is not old history.
            else:
                resource_pr = member["resource_pr"]
                natural = member["observation_uuid"]
                actual_digest = observation_digest(
                    db, observations, member["observation_uuid"]
                )
                if (
                    actual_digest != member["actual_digest"]
                    or actual_digest != member["state_digest"]
                ):
                    raise InvalidProof(
                        "member digest differs from normalized observed values"
                    )
            if (
                collection["change_request_id"] is not None
                and resource_pr != collection["change_request_id"]
            ):
                raise InvalidProof("member belongs to another PR in same repository")
            rows.append(
                [
                    member["position"],
                    member_table,
                    natural,
                    member["state_digest"].hex(),
                ]
            )
            root_members.append(member)
        if fragment["member_count"] != len(rows) or fragment[
            "member_digest"
        ] != manifest(rows):
            raise InvalidProof("fragment count or digest")
        all_members.extend([[fragment["ordinal"], *row] for row in rows])
    children = db.execute(
        "SELECT * FROM collection_child_obligations WHERE parent_collection_uuid=? ORDER BY parent_ordinal,parent_position,required_role",
        (collection_uuid,),
    ).fetchall()
    expected = (
        {(member["ordinal"], member["position"], "comments") for member in root_members}
        if collection["kind"] == "threads"
        else set()
    )
    actual = {
        (child["parent_ordinal"], child["parent_position"], child["required_role"])
        for child in children
    }
    if actual != expected:
        raise InvalidProof("required child obligation set")
    child_manifest, times = [], [fragment["observed_at_us"] for fragment in fragments]
    if terminal["observed_at_us"] != max(times):
        raise InvalidProof("terminal clock differs from admitted fragment boundary")
    for child in children:
        parent = db.execute(
            "SELECT t.thread_id,t.change_request_id FROM thread_collection_members m JOIN review_thread_observations o USING(observation_uuid) JOIN review_threads t USING(thread_id) WHERE m.collection_uuid=? AND m.ordinal=? AND m.position=?",
            (collection_uuid, child["parent_ordinal"], child["parent_position"]),
        ).fetchone()
        child_scope = db.execute(
            "SELECT s.* FROM repository_collection_observations c JOIN repository_collection_scopes s USING(scope_uuid) WHERE collection_uuid=?",
            (child["child_collection_uuid"],),
        ).fetchone()
        if (
            not parent
            or child_scope["kind"] != "thread-comments"
            or child_scope["thread_id"] != parent["thread_id"]
            or child_scope["change_request_id"] != parent["change_request_id"]
        ):
            raise InvalidProof("wrong natural child scope")
        times.append(validate_collection(db, child["child_collection_uuid"], active))
        child_manifest.append(
            [
                child["parent_ordinal"],
                child["parent_position"],
                child["required_role"],
                child["child_collection_uuid"],
            ]
        )
    if seal["member_count"] != len(all_members) or seal["member_digest"] != manifest(
        all_members
    ):
        raise InvalidProof("collection member count or digest")
    if seal["required_child_count"] != len(children) or seal[
        "required_child_digest"
    ] != manifest(child_manifest):
        raise InvalidProof("child manifest digest")
    if seal["observed_at_us"] != max(times):
        raise InvalidProof("assessment observation clock differs from exact evidence")
    active.remove(collection_uuid)
    return seal["observed_at_us"]


def collection(
    db, number, members=(), ordinals=(0,), terminal=True, kind="pr-list", thread=None
):
    scope, cid = ident(number + 1000), ident(number + 2000)
    put(
        db,
        "repository_collection_scopes",
        scope_uuid=scope,
        repository_uuid=ident(11),
        kind=kind,
        change_request_id="pr-1" if kind != "pr-list" else None,
        thread_id=thread,
    )
    put(
        db,
        "repository_collection_observations",
        collection_uuid=cid,
        scope_uuid=scope,
        repository_uuid=ident(11),
        publication_uuid=ident(41),
        observed_at_us=100,
    )
    member_table, _ = FAMILIES[kind]
    flattened = []
    for ordinal in ordinals:
        rows = (
            [
                [position, member_table, uid, value.hex()]
                for position, (uid, value) in enumerate(members)
            ]
            if ordinal == ordinals[0]
            else []
        )
        put(
            db,
            "repository_collection_fragments",
            collection_uuid=cid,
            repository_uuid=ident(11),
            ordinal=ordinal,
            observed_at_us=100,
            module="fixture.domain",
            version="1",
            member_count=len(rows),
            member_digest=manifest(rows),
        )
        for position, uid, value in (
            [(pos, uid, value) for pos, (uid, value) in enumerate(members)]
            if ordinal == ordinals[0]
            else []
        ):
            put(
                db,
                member_table,
                collection_uuid=cid,
                ordinal=ordinal,
                position=position,
                repository_uuid=ident(11),
                observation_uuid=uid,
                state_digest=value,
            )
        flattened.extend([[ordinal, *row] for row in rows])
    if terminal:
        put(
            db,
            "repository_collection_terminals",
            collection_uuid=cid,
            repository_uuid=ident(11),
            last_ordinal=max(ordinals),
            observed_at_us=100,
        )
        put(
            db,
            "repository_collection_seals",
            collection_uuid=cid,
            repository_uuid=ident(11),
            member_count=len(flattened),
            member_digest=manifest(flattened),
            required_child_count=0,
            required_child_digest=manifest([]),
            observed_at_us=100,
        )
    return cid


def rejected(call):
    try:
        call()
    except (sqlite3.IntegrityError, InvalidProof, OverflowError):
        return True
    raise AssertionError("adversarial input was accepted")


def run():
    results = []

    def case(name, function):
        function()
        results.append({"case": name, "outcome": "passed"})

    def proof_case(kind):
        with connect() as db:
            base(db)
            if kind == "empty":
                assert validate_collection(db, collection(db, 1)) == 100
            elif kind == "terminal":
                rejected(
                    lambda: validate_collection(db, collection(db, 2, terminal=False))
                )
            elif kind == "ordinal":
                rejected(
                    lambda: validate_collection(db, collection(db, 3, ordinals=(0, 2)))
                )
            elif kind == "duplicate":
                rejected(lambda: collection(db, 4, ordinals=(0, 0)))
            elif kind == "digest":
                cid = collection(db, 5, members=[pr(db, 1)])
                db.execute(
                    "UPDATE repository_collection_fragments SET member_digest=? WHERE collection_uuid=?",
                    (manifest(["incorrect"]), cid),
                )
                rejected(lambda: validate_collection(db, cid))
            elif kind == "selective":
                member = pr(db, 2)
                cid = collection(db, 6, members=[member])
                db.execute(
                    "DELETE FROM pr_collection_members WHERE collection_uuid=?", (cid,)
                )
                rejected(lambda: validate_collection(db, cid))
                put(
                    db,
                    "pr_collection_members",
                    collection_uuid=cid,
                    ordinal=0,
                    position=0,
                    repository_uuid=ident(11),
                    observation_uuid=member[0],
                    state_digest=member[1],
                )
                assert validate_collection(db, cid) == 100
            elif kind == "owner":
                rejected(lambda: collection(db, 7, members=[pr(db, 3, owner=2)]))
                rejected(
                    lambda: put(
                        db,
                        "source_publications",
                        publication_uuid=ident(999),
                        source_uuid=ident(998),
                        observed_at_us=0,
                        module="fixture",
                        version="1",
                    )
                )
                rejected(
                    lambda: put(
                        db,
                        "repository_publications",
                        publication_uuid=ident(997),
                        repository_uuid=ident(996),
                        observed_at_us=0,
                        module="fixture",
                        version="1",
                    )
                )
            elif kind == "wrong_family":
                cid = collection(db, 8)
                db.execute(
                    "UPDATE repository_collection_scopes SET kind='documents' WHERE scope_uuid=(SELECT scope_uuid FROM repository_collection_observations WHERE collection_uuid=?)",
                    (cid,),
                )
                member = pr(db, 4)
                put(
                    db,
                    "pr_collection_members",
                    collection_uuid=cid,
                    ordinal=0,
                    position=0,
                    repository_uuid=ident(11),
                    observation_uuid=member[0],
                    state_digest=member[1],
                )
                rejected(lambda: validate_collection(db, cid))
            elif kind == "tampered_value":
                member = pr(db, 5)
                cid = collection(db, 9, members=[member])
                db.execute(
                    "UPDATE change_request_observations SET title='changed without evidence' WHERE observation_uuid=?",
                    (member[0],),
                )
                rejected(lambda: validate_collection(db, cid))
            elif kind == "cross_field_origin":
                member = pr(db, 6)
                other = pr(db, 7, owner=2)
                cid = collection(db, 10, members=[member])
                db.execute(
                    "UPDATE pr_observation_fields SET origin_observation_uuid=? WHERE observation_uuid=?",
                    (other[0], member[0]),
                )
                rejected(lambda: validate_collection(db, cid))

    for name in (
        "empty",
        "terminal",
        "ordinal",
        "duplicate",
        "digest",
        "selective",
        "owner",
        "wrong_family",
        "tampered_value",
        "cross_field_origin",
    ):
        case(name, lambda name=name: proof_case(name))

    def coverage():
        with connect() as db:
            base(db)
            assert [
                row[1] for row in db.execute("PRAGMA table_info(coverage_claims)")
            ] == [
                "coverage_claim_id",
                "coverage_scope_id",
                "coverage_state",
                "observed_at_us",
                "details_json",
            ]
            put(
                db,
                "coverage_scopes",
                coverage_scope_id="coverage",
                repository_uuid=ident(11),
                kind="pr-list",
                scope_identity="all",
            )
            assert tuple(
                db.execute(
                    "SELECT observed_at_us,coverage_state FROM current_coverage"
                ).fetchone()
            ) == (None, "unknown")
            for clock, state in (
                (100, "complete"),
                (200, "partial"),
                (200, "complete"),
            ):
                put(
                    db,
                    "coverage_claims",
                    coverage_scope_id="coverage",
                    observed_at_us=clock,
                    coverage_state=state,
                )
            assert tuple(
                db.execute(
                    "SELECT observed_at_us,coverage_state FROM current_coverage"
                ).fetchone()
            ) == (200, "conflict")
            put(
                db,
                "coverage_claims",
                coverage_scope_id="coverage",
                observed_at_us=300,
                coverage_state="unknown",
            )
            assert tuple(
                db.execute(
                    "SELECT observed_at_us,coverage_state FROM current_coverage"
                ).fetchone()
            ) == (300, "unknown")
            put(
                db,
                "coverage_claims",
                coverage_scope_id="coverage",
                observed_at_us=300,
                coverage_state="complete",
            )
            assert tuple(
                db.execute(
                    "SELECT observed_at_us,coverage_state FROM current_coverage"
                ).fetchone()
            ) == (300, "complete")

    case("coverage_exact_contract_newer_partial_equal_time_unknown", coverage)

    def fields():
        with connect() as db:
            base(db)
            uid, _ = pr(db, 9)
            put(
                db,
                "pr_observation_fields",
                observation_uuid=uid,
                path="body",
                state="null",
                origin_observation_uuid=uid,
                module="fixture.domain",
                version="1",
            )
            db.execute(
                "UPDATE change_request_observations SET title='' WHERE observation_uuid=?",
                (uid,),
            )
            db.execute(
                "UPDATE pr_observation_fields SET value_json='\"\"' WHERE observation_uuid=? AND path='title'",
                (uid,),
            )
            observation_digest(db, "change_request_observations", uid)
            assert not db.execute(
                "SELECT 1 FROM pr_observation_fields WHERE path='omitted'"
            ).fetchone()
            assert (
                len(
                    {
                        manifest({"identity": uid}),
                        manifest({"identity": uid, "body": None}),
                        manifest({"identity": uid, "body": ""}),
                    }
                )
                == 3
            )
            rejected(
                lambda: put(
                    db,
                    "pr_observation_fields",
                    observation_uuid=uid,
                    path="bad",
                    state="value",
                    value_json="null",
                    origin_observation_uuid=uid,
                    module="fixture",
                    version="1",
                )
            )
            rejected(
                lambda: put(
                    db,
                    "pr_observation_fields",
                    observation_uuid=uid,
                    path="_original_response",
                    state="value",
                    value_json=json.dumps(
                        {
                            "http_status": 200,
                            "headers": {"etag": "opaque"},
                            "provider_body": {"wire_marker": "unmodeled"},
                        }
                    ),
                    origin_observation_uuid=uid,
                    module="fixture.domain",
                    version="1",
                )
            )

    case("identical_identity_missing_null_empty", fields)

    def unordered():
        with connect() as db:
            base(db)
            pr(db, 10, clock=100, scope="endpoint-a")
            pr(db, 11, clock=200, scope="endpoint-b")
            members = [
                list(row)
                for row in db.execute(
                    "SELECT observation_uuid,hex(state_digest) FROM change_request_observations ORDER BY observation_uuid"
                )
            ]
            put(
                db,
                "repository_publication_seals",
                publication_uuid=ident(41),
                repository_uuid=ident(11),
                member_count=2,
                member_digest=manifest(members),
                sealed_at_us=101,
            )
            assert (
                db.execute("SELECT count(*) FROM pr_maximal_candidates").fetchone()[0]
                == 2
            )

    case("incomparable_observations_keep_both_candidates", unordered)

    def unknown_identity_attributes():
        with connect() as db:
            base(db)
            put(db, "sources", source_uuid=ident(880), service_uuid=None)
            put(db, "repositories", repository_uuid=ident(881))
            put(
                db,
                "repository_bindings",
                binding_uuid=ident(882),
                repository_uuid=ident(881),
                service_uuid=ident(1),
                provider_repository_id=None,
            )
            assert (
                db.execute(
                    "SELECT service_uuid FROM sources WHERE source_uuid=?",
                    (ident(880),),
                ).fetchone()[0]
                is None
            )

    case(
        "manual_source_and_unknown_provider_identity_without_fabrication",
        unknown_identity_attributes,
    )

    def nested():
        with connect() as db:
            base(db)
            put(
                db,
                "review_threads",
                thread_id="thread-1",
                change_request_id="pr-1",
                repository_uuid=ident(11),
                provider_thread_id="provider-thread-1",
            )
            rejected(
                lambda: put(
                    db,
                    "review_threads",
                    thread_id="duplicate-local-thread",
                    change_request_id="pr-1",
                    repository_uuid=ident(11),
                    provider_thread_id="provider-thread-1",
                )
            )
            state = manifest({"thread_id": "thread-1", "resolved": 0})
            put(
                db,
                "review_thread_observations",
                observation_uuid=ident(801),
                thread_id="thread-1",
                repository_uuid=ident(11),
                publication_uuid=ident(41),
                observed_at_us=100,
                resolved=0,
                module="fixture.domain",
                version="1",
                state_digest=state,
            )
            root = collection(db, 40, members=[(ident(801), state)], kind="threads")
            rejected(lambda: validate_collection(db, root))
            child = collection(db, 41, kind="thread-comments", thread="thread-1")
            put(
                db,
                "collection_child_obligations",
                parent_collection_uuid=root,
                parent_ordinal=0,
                parent_position=0,
                repository_uuid=ident(11),
                child_collection_uuid=child,
                required_role="comments",
            )
            digest = manifest([[0, 0, "comments", child]])
            db.execute(
                "UPDATE repository_collection_seals SET required_child_count=1,required_child_digest=? WHERE collection_uuid=?",
                (digest, root),
            )
            assert validate_collection(db, root) == 100
            put(
                db,
                "change_requests",
                change_request_id="pr-3",
                repository_uuid=ident(11),
                binding_uuid=ident(31),
                service_uuid=ident(1),
                provider_number=3,
                kind="pull_request",
            )
            db.execute(
                "UPDATE repository_collection_scopes SET change_request_id='pr-3' WHERE scope_uuid=(SELECT scope_uuid FROM repository_collection_observations WHERE collection_uuid=?)",
                (child,),
            )
            rejected(lambda: validate_collection(db, root))

    case("nested_missing_child_then_exact_empty_child_wrong_pr_scope", nested)

    def git():
        with connect() as db:
            body = "exact Git bytes\n".encode()
            put(db, "domain_bytes", sha256=sha(body), body=body, byte_length=len(body))
            for fmt in ("sha1", "sha256"):
                oid = hashlib.new(fmt, f"blob {len(body)}\0".encode() + body).digest()
                put(
                    db,
                    "git_objects",
                    object_format=fmt,
                    oid=oid,
                    type="blob",
                    size=len(body),
                    sha256=sha(body),
                )
                rejected(
                    lambda fmt=fmt, oid=oid: put(
                        db,
                        "git_objects",
                        object_format=fmt,
                        oid=bytes(len(oid)),
                        type="blob",
                        size=len(body),
                        sha256=sha(body),
                    )
                )
            rejected(
                lambda: put(
                    db,
                    "domain_bytes",
                    sha256=bytes(32),
                    body=body,
                    byte_length=len(body),
                )
            )

    case("verified_git_sha1_sha256_exact_shared_content", git)

    def restart():
        with tempfile.TemporaryDirectory(prefix="p2-candidate-") as temporary:
            path = Path(temporary) / "candidate.sqlite"
            db = connect(path)
            base(db)
            cid = collection(db, 30, terminal=False)
            db.close()
            db = sqlite3.connect(path, isolation_level=None)
            db.row_factory = sqlite3.Row
            rejected(lambda: validate_collection(db, cid))
            put(
                db,
                "repository_collection_terminals",
                collection_uuid=cid,
                repository_uuid=ident(11),
                last_ordinal=0,
                observed_at_us=100,
            )
            put(
                db,
                "repository_collection_seals",
                collection_uuid=cid,
                repository_uuid=ident(11),
                member_count=0,
                member_digest=manifest([]),
                required_child_count=0,
                required_child_digest=manifest([]),
                observed_at_us=100,
            )
            assert validate_collection(db, cid) == 100
            db.close()

    case("file_close_reopen_committed_prefix", restart)
    with connect() as db:
        counts = {
            kind: db.execute(
                "SELECT count(*) FROM sqlite_schema WHERE type=?", (kind,)
            ).fetchone()[0]
            for kind in ("table", "view", "trigger", "index")
        }
        checks = {
            "foreign_keys": db.execute("PRAGMA foreign_key_check").fetchall(),
            "integrity": [row[0] for row in db.execute("PRAGMA integrity_check")],
            "strict_tables": sum(row[5] for row in db.execute("PRAGMA table_list")),
        }
    return {
        "status": "Proposed/Pending Owner Decision",
        "sql_sha256": sha(SQL.read_bytes()).hex(),
        "cases": results,
        "counts": counts,
        "checks": checks,
        "limitations": [
            "This is a domain skeleton, not production writer/reader or wire format.",
            "Publication member sealing, complete retained-field contracts, current-resource admission and immutable guards reuse responsibilities traced in workstreams but are not fully implemented in this prototype.",
            "Source/code/Git interpretation validators and production CAS-41 backup/restore are characterized separately; no prototype pass certifies those runtime paths.",
            "No retention duration, GC, lifecycle or owner decision is implemented.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
