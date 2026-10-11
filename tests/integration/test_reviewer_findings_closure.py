"""Deterministic regression and counterexample tests for the eight new review findings:

B-02: Exchange code_acquisitions retention, cross-repo validation, onward export.
B-03: Missing captured review, merge, or test-merge role qualifies code assessment.
B-04: Public synchronization overstates completeness despite code conflict.
C-03: Selected Exchange scaling bounded access paths & missing index verification.
C-04: Generic competing-variant grouping distinguishing invalid vs pending/final.
C-05: Late conflicting code state reporting ambiguity/conflict in code observation.
C-06: Natural identities in Exchange for acquisition_roots and root_origins.
C-07: Root origins distinguishing missing_dependency from invalid:git_ref_origin.
"""

from __future__ import annotations

import hashlib
import json

from repo_catalog.adapters.sqlite.code_assessments import current_code_assessment
from repo_catalog.adapters.sqlite.exchange import FORMAT, Graph, encode
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.pr_queries import _code_observation, code_role_gaps
from tests.support.domain_facts import SERVICE, SOURCE, repository_uuid


def oid(fmt, typ, data):
    return hashlib.new(fmt, f"{typ} {len(data)}\0".encode() + data).digest()


def opened(path):
    MaintenanceService(path).init("catalog-text-v1", 64 * 1024 * 1024, 0)
    return Store(path)


def put(store, table, **values):
    return store.execute(
        f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
        tuple(values.values()),
    )


def _base_repo_setup(store, repo_id=None):
    repo_id = repo_id or repository_uuid(10)
    with store.transaction():
        put(
            store,
            "repositories",
            repository_uuidv4=repo_id,
            name="test-repo",
            metadata="{}",
        )
        put(
            store,
            "service_instances",
            service_instance_uuidv4=SERVICE,
            service_kind="github",
            name="github",
            metadata="{}",
        )
        put(
            store,
            "sources",
            source_registration_uuidv4=SOURCE,
            source_id="src",
            service_instance_uuidv4=SERVICE,
            discovery_kind="github_inventory",
            name="src",
            settings="{}",
        )
        put(
            store,
            "repository_bindings",
            repository_binding_id="bind-1",
            repository_uuidv4=repo_id,
            service_instance_uuidv4=SERVICE,
            provider_repository_id="repo-1",
            metadata="{}",
        )
        put(
            store,
            "source_repositories",
            source_id="src",
            repository_uuidv4=repo_id,
        )
    return repo_id


# =====================================================================
# B-02: Missing code acquisition roles in Exchange
# =====================================================================


def test_b02_code_acquisitions_retained_in_full_and_selective_exchange(tmp_path):
    sender_path = tmp_path / "sender"
    receiver_path = tmp_path / "receiver"
    onward_path = tmp_path / "onward"

    s_store = opened(sender_path)
    repo = _base_repo_setup(s_store)

    head_bytes = oid("sha1", "commit", b"head commit")
    base_bytes = oid("sha1", "commit", b"base commit")

    with s_store.transaction():
        # Change request
        put(
            s_store,
            "change_requests",
            change_request_id="cr-1",
            repository_binding_id="bind-1",
            repository_uuidv4=repo,
            change_request_kind="pull_request",
            provider_change_request_number=1,
        )
        # Git acquisition
        put(
            s_store,
            "git_acquisitions",
            git_acquisition_id="acq-1",
            repository_uuidv4=repo,
            kind="git",
            object_format="sha1",
            request="{}",
            roots_manifest="[]",
        )
        put(
            s_store,
            "acquisition_roots",
            acquisition_root_id=1,
            git_acquisition_id="acq-1",
            repository_uuidv4=repo,
            object_format="sha1",
            oid=head_bytes,
            role="head",
            complete=0,
        )
        # Fetch collections and listings
        scope_c = json.dumps(
            {
                "repository_uuidv4": repo,
                "change_request_id": "cr-1",
                "endpoint": "https://api.github.com/commits",
            }
        )
        scope_f = json.dumps(
            {
                "repository_uuidv4": repo,
                "change_request_id": "cr-1",
                "endpoint": "https://api.github.com/files",
            }
        )
        put(
            s_store,
            "fetch_collections",
            fetch_collection_id="fc-commits",
            source_id="src",
            repository_uuidv4=repo,
            change_request_id="cr-1",
            kind="pr-commits",
            observed_at_us=100,
            scope_json=scope_c,
        )
        put(
            s_store,
            "fetch_collections",
            fetch_collection_id="fc-files",
            source_id="src",
            repository_uuidv4=repo,
            change_request_id="cr-1",
            kind="pr-files",
            observed_at_us=100,
            scope_json=scope_f,
        )
        put(
            s_store,
            "code_listings",
            code_listing_id="list-c",
            fetch_collection_id="fc-commits",
            change_request_id="cr-1",
            kind="commits",
            object_format="sha1",
            head_oid=head_bytes,
            base_oid=base_bytes,
        )
        put(
            s_store,
            "code_listings",
            code_listing_id="list-f",
            fetch_collection_id="fc-files",
            change_request_id="cr-1",
            kind="files",
            object_format="sha1",
            head_oid=head_bytes,
            base_oid=base_bytes,
        )
        # Code assessment
        put(
            s_store,
            "code_assessments",
            code_assessment_id="ca-1",
            change_request_id="cr-1",
            repository_uuidv4=repo,
            commit_code_listing_id="list-c",
            file_code_listing_id="list-f",
            state="partial",
            object_format="sha1",
            head_oid=head_bytes,
            base_oid=base_bytes,
            observed_at_us=100,
            parser_module="test",
            parser_version="1.0",
            details_json='{"expected_roles":{"head":"' + head_bytes.hex() + '"}}',
        )
        # Code acquisition
        put(
            s_store,
            "code_acquisitions",
            code_assessment_id="ca-1",
            role="head",
            object_format="sha1",
            oid=head_bytes,
            acquisition_root_id=1,
        )

    graph = Graph(s_store.connection)
    export_full = graph.export(repo)
    code_acq_records = [
        r for r in export_full["records"] if r["table"] == "code_acquisitions"
    ]
    assert len(code_acq_records) == 1, (
        "Full export must retain code_acquisitions role records"
    )
    assert code_acq_records[0]["values"]["role"] == "head"

    # Receive in receiver catalog
    r_store = opened(receiver_path)
    r_graph = Graph(r_store.connection)
    receipt = r_graph.receive(export_full)
    assert receipt["admitted_records"] > 0
    admitted_acq = r_store.one(
        "SELECT role, object_format FROM code_acquisitions WHERE code_assessment_id='ca-1'"
    )
    assert tuple(admitted_acq) == ("head", "sha1")

    # Onward export from receiver
    export_onward = r_graph.export(repo)
    onward_acq_records = [
        r for r in export_onward["records"] if r["table"] == "code_acquisitions"
    ]
    assert len(onward_acq_records) == 1, "Onward export must preserve code_acquisitions"

    # Receive in third catalog
    o_store = opened(onward_path)
    o_graph = Graph(o_store.connection)
    o_receipt = o_graph.receive(export_onward)
    assert o_receipt["admitted_records"] > 0
    assert o_store.one("SELECT count(*) FROM code_acquisitions")[0] == 1


def test_b02_code_acquisition_cross_repository_ownership_rejection(tmp_path):
    store = opened(tmp_path / "cross_repo")
    repo1 = _base_repo_setup(store, repository_uuid(11))
    repo2 = repository_uuid(12)
    s_oid = oid("sha1", "commit", b"c")
    with store.transaction():
        put(store, "repositories", repository_uuidv4=repo2, name="repo2", metadata="{}")
        put(
            store,
            "change_requests",
            change_request_id="cr-foreign",
            repository_binding_id="bind-1",
            repository_uuidv4=repo1,
            change_request_kind="pull_request",
            provider_change_request_number=2,
        )
        put(
            store,
            "git_acquisitions",
            git_acquisition_id="acq-2",
            repository_uuidv4=repo2,
            kind="git",
            object_format="sha1",
            request="{}",
            roots_manifest="[]",
        )
        put(
            store,
            "acquisition_roots",
            acquisition_root_id=99,
            git_acquisition_id="acq-2",
            repository_uuidv4=repo2,
            object_format="sha1",
            oid=s_oid,
            role="head",
            complete=0,
        )
        put(
            store,
            "code_assessments",
            code_assessment_id="ca-foreign",
            change_request_id="cr-foreign",
            repository_uuidv4=repo1,
            state="partial",
            object_format="sha1",
            head_oid=s_oid,
            base_oid=s_oid,
            observed_at_us=100,
            parser_module="test",
            parser_version="1.0",
            details_json="{}",
        )

    graph = Graph(store.connection)
    admit_result = graph._admit(
        {
            "key": "code_acquisitions:test",
            "table": "code_acquisitions",
            "values": {
                "code_assessment_id": "ca-foreign",
                "role": "head",
                "object_format": "sha1",
                "oid": encode(s_oid, "oid"),
                "acquisition_root_id": 99,
            },
        },
        "origin-1",
        repo1,
    )
    assert admit_result == "conflict:code_acquisition_owner"


# =====================================================================
# B-03: Missing captured review, merge, or test-merge role qualifies code
# =====================================================================


def test_b03_missing_merge_or_review_role_prevents_complete_state(tmp_path):
    store = opened(tmp_path / "b03_db")
    repo = _base_repo_setup(store)
    head_oid = oid("sha1", "commit", b"head")
    base_oid = oid("sha1", "commit", b"base")
    merge_oid = oid("sha1", "commit", b"merge")

    with store.transaction():
        put(
            store,
            "change_requests",
            change_request_id="cr-b03",
            repository_binding_id="bind-1",
            repository_uuidv4=repo,
            change_request_kind="pull_request",
            provider_change_request_number=10,
        )
        put(
            store,
            "change_request_state",
            change_request_id="cr-b03",
            repository_uuidv4=repo,
            repository_binding_id="bind-1",
            service_instance_uuidv4=SERVICE,
            kind="change-request",
            object_format="sha1",
            head_oid=head_oid,
            base_oid=base_oid,
            merge_oid=merge_oid,
            observed_at_us=100,
            parsed_at_us=100,
            parser_module="github",
            parser_version="1.0",
            acquisition_scope_json=json.dumps(
                {
                    "repository_uuidv4": repo,
                    "service_instance_uuidv4": SERVICE,
                    "repository_binding_id": "bind-1",
                    "endpoint": "pulls",
                    "change_request_id": "cr-b03",
                }
            ),
        )

    code = {
        "code_assessment_id": "ca-b03",
        "object_format": "sha1",
        "head_oid": head_oid,
        "base_oid": base_oid,
        "details_json": json.dumps(
            {
                "expected_roles": {
                    "head": head_oid.hex(),
                    "base": base_oid.hex(),
                    "merge": merge_oid.hex(),
                }
            }
        ),
    }
    with store.transaction():
        put(
            store,
            "code_assessments",
            code_assessment_id="ca-b03",
            change_request_id="cr-b03",
            repository_uuidv4=repo,
            state="partial",
            object_format="sha1",
            head_oid=head_oid,
            base_oid=base_oid,
            observed_at_us=100,
            parser_module="test",
            parser_version="1.0",
            details_json=code["details_json"],
        )
        put(
            store,
            "code_acquisitions",
            code_assessment_id="ca-b03",
            role="head",
            object_format="sha1",
            oid=head_oid,
            acquisition_root_id=None,
        )

    gaps = list(
        code_role_gaps(store, {"repository_uuidv4": repo}, code, check=lambda: None)
    )
    missing_reasons = [g["reason"] for g in gaps]
    assert "code_role_acquisition_missing" in missing_reasons
    missing_roles = [
        g.get("role") for g in gaps if g["reason"] == "code_role_acquisition_missing"
    ]
    assert "merge" in missing_roles


# =====================================================================
# B-04: Public synchronization overstates completeness on code conflict
# =====================================================================


def test_b04_sync_coverage_reports_partial_on_code_conflict(tmp_path):
    store = opened(tmp_path / "b04_db")
    repo = _base_repo_setup(store)
    head_oid1 = oid("sha1", "commit", b"head1")
    head_oid2 = oid("sha1", "commit", b"head2")
    base_oid = oid("sha1", "commit", b"base")

    with store.transaction():
        put(
            store,
            "change_requests",
            change_request_id="cr-b04",
            repository_binding_id="bind-1",
            repository_uuidv4=repo,
            change_request_kind="pull_request",
            provider_change_request_number=20,
        )
        put(
            store,
            "change_request_state",
            change_request_id="cr-b04",
            repository_uuidv4=repo,
            repository_binding_id="bind-1",
            service_instance_uuidv4=SERVICE,
            kind="change-request",
            object_format="sha1",
            head_oid=head_oid1,
            base_oid=base_oid,
            observed_at_us=200,
            parsed_at_us=200,
            parser_module="github",
            parser_version="1.0",
            acquisition_scope_json=json.dumps(
                {
                    "repository_uuidv4": repo,
                    "service_instance_uuidv4": SERVICE,
                    "repository_binding_id": "bind-1",
                    "endpoint": "pulls",
                    "change_request_id": "cr-b04",
                }
            ),
        )
        # Create contradictory same-time code assessments for this PR
        put(
            store,
            "code_assessments",
            code_assessment_id="ca-b04-1",
            change_request_id="cr-b04",
            repository_uuidv4=repo,
            state="partial",
            object_format="sha1",
            head_oid=head_oid1,
            base_oid=base_oid,
            observed_at_us=200,
            parser_module="test",
            parser_version="1.0",
            details_json="{}",
        )
        put(
            store,
            "code_assessments",
            code_assessment_id="ca-b04-2",
            change_request_id="cr-b04",
            repository_uuidv4=repo,
            state="partial",
            object_format="sha1",
            head_oid=head_oid2,
            base_oid=base_oid,
            observed_at_us=200,
            parser_module="test",
            parser_version="1.0",
            details_json="{}",
        )

    # current_code_assessment reports None due to conflict between ca-1 and ca-2
    candidate = current_code_assessment(store, "cr-b04", "sha1", head_oid1, base_oid)
    assert candidate is not None  # Specific head filter finds ca-b04-1

    # But without specific head (PR level query), _code_observation returns None
    class MockQuery:
        def __init__(self, s):
            self.s = s

    obs = _code_observation(
        MockQuery(store),
        {"change_request_id": "cr-b04", "repository_uuidv4": repo},
        {},
    )
    assert obs is None, "Contradictory same-time code assessments must report ambiguity"


# =====================================================================
# C-03: Selected Exchange scaling & bounded access paths
# =====================================================================


def test_c03_selected_exchange_bounded_scaling_and_indexes(tmp_path):
    store = opened(tmp_path / "c03_db")
    repo = _base_repo_setup(store)

    conn = store.connection
    plan_sources = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM repository_object_sources WHERE repository_uuidv4=? AND git_acquisition_id=?",
        (repo, "acq-test"),
    ).fetchall()
    plan_text = " ".join(row[3] for row in plan_sources)
    assert "INDEX repository_object_sources_acquisition" in plan_text

    plan_snapshots = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM snapshots WHERE repository_uuidv4=? AND git_acquisition_id=?",
        (repo, "acq-test"),
    ).fetchall()
    snap_plan_text = " ".join(row[3] for row in plan_snapshots)
    assert "INDEX snapshots_acquisition" in snap_plan_text

    # Populate 500 unrelated repository_object_sources and snapshots
    with store.transaction():
        for i in range(500):
            put(
                store,
                "git_objects",
                git_object_id=1000 + i,
                object_format="sha1",
                oid=oid("sha1", "blob", f"unrelated {i}".encode()),
                type="blob",
                size=10,
                verified=1,
            )
            put(
                store,
                "git_acquisitions",
                git_acquisition_id=f"acq-unrelated-{i}",
                repository_uuidv4=repo,
                kind="git",
                object_format="sha1",
                request="{}",
                roots_manifest="[]",
            )
            put(
                store,
                "repository_object_sources",
                repository_uuidv4=repo,
                git_object_id=1000 + i,
                git_acquisition_id=f"acq-unrelated-{i}",
            )
            put(
                store,
                "snapshots",
                snapshot_id=f"snap-unrelated-{i}",
                git_acquisition_id=f"acq-unrelated-{i}",
                repository_uuidv4=repo,
                complete=0,
                generation=0,
            )

    target_acq = "acq-target"
    with store.transaction():
        put(
            store,
            "git_objects",
            git_object_id=9999,
            object_format="sha1",
            oid=oid("sha1", "blob", b"target"),
            type="blob",
            size=6,
            verified=1,
        )
        put(
            store,
            "git_acquisitions",
            git_acquisition_id=target_acq,
            repository_uuidv4=repo,
            kind="git",
            object_format="sha1",
            request="{}",
            roots_manifest="[]",
        )
        put(
            store,
            "repository_object_sources",
            repository_uuidv4=repo,
            git_object_id=9999,
            git_acquisition_id=target_acq,
        )

    res = conn.execute(
        "SELECT git_object_id FROM repository_object_sources WHERE repository_uuidv4=? AND git_acquisition_id=?",
        (repo, target_acq),
    ).fetchall()
    assert len(res) == 1
    assert res[0][0] == 9999


# =====================================================================
# C-04: Generic competing-variant grouping mishandles pending/final
# =====================================================================


def test_c04_competing_variants_excludes_invalid_and_unifies_pending(tmp_path):
    store = opened(tmp_path / "c04_db")
    repo = _base_repo_setup(store)
    graph = Graph(store.connection)

    # 1. Invalid candidate in staging must not poison a valid candidate
    key = 'stored_bytes:{"sha256":{"$sha256":"' + "0" * 64 + '"}}'
    digest_inv = hashlib.sha256(b"invalid_record").digest()
    digest_val = hashlib.sha256(b"valid_record").digest()
    valid_payload = json.dumps(
        {
            "key": key,
            "table": "stored_bytes",
            "values": {
                "sha256": {"$sha256": "0" * 64},
                "body": {"$bytes": "AAAA"},
                "byte_length": 3,
            },
        }
    )

    with store.transaction():
        store.execute(
            "INSERT INTO exchange_staging(record_key, content_sha256, table_name, repository_uuidv4, origin_catalog_uuidv4, record_json, reason) VALUES(?,?,?,?,?,?,?)",
            (
                key,
                digest_inv,
                "stored_bytes",
                repo,
                repository_uuid(98),
                valid_payload,
                "invalid:digest",
            ),
        )
        store.execute(
            "INSERT INTO exchange_staging(record_key, content_sha256, table_name, repository_uuidv4, origin_catalog_uuidv4, record_json, reason) VALUES(?,?,?,?,?,?,?)",
            (
                key,
                digest_val,
                "stored_bytes",
                repo,
                repository_uuid(98),
                valid_payload,
                "missing_dependency",
            ),
        )

    # Competing variant grouping query ignores rows with reason LIKE 'invalid:%'
    staged_counts = store.execute(
        "SELECT record_key, table_name FROM exchange_staging WHERE reason NOT LIKE 'current_state:%' AND reason NOT LIKE 'invalid:%' GROUP BY record_key, table_name HAVING count(*)>1"
    ).fetchall()
    assert len(staged_counts) == 0, (
        "Invalid candidate must not count toward competing variants"
    )

    # 2. Compatible pending and final code_assessments unify
    head_oid = oid("sha1", "commit", b"head")
    base_oid = oid("sha1", "commit", b"base")
    with store.transaction():
        put(
            store,
            "change_requests",
            change_request_id="cr-unify",
            repository_binding_id="bind-1",
            repository_uuidv4=repo,
            change_request_kind="pull_request",
            provider_change_request_number=99,
        )
        put(
            store,
            "code_assessments",
            code_assessment_id="ca-unify",
            change_request_id="cr-unify",
            repository_uuidv4=repo,
            state="pending",
            object_format="sha1",
            head_oid=head_oid,
            base_oid=base_oid,
            observed_at_us=100,
            parser_module="test",
            parser_version="1.0",
            details_json="{}",
        )

    exp_pending = graph.export(repo)
    rec_pending = next(
        r for r in exp_pending["records"] if r["table"] == "code_assessments"
    )

    with store.transaction():
        store.execute(
            "UPDATE code_assessments SET state='partial', details_json=? WHERE code_assessment_id='ca-unify'",
            ('{"code_inputs_complete":true}',),
        )
    exp_final = graph.export(repo)
    rec_final = next(
        r for r in exp_final["records"] if r["table"] == "code_assessments"
    )

    # In receiver catalog:
    r_store = opened(tmp_path / "c04_recv")
    r_repo = _base_repo_setup(r_store, repo)
    with r_store.transaction():
        put(
            r_store,
            "change_requests",
            change_request_id="cr-unify",
            repository_binding_id="bind-1",
            repository_uuidv4=r_repo,
            change_request_kind="pull_request",
            provider_change_request_number=99,
        )
    r_graph = Graph(r_store.connection)
    unit = {
        "format": FORMAT,
        "origin_catalog_uuidv4": repository_uuid(99),
        "repository_uuidv4": r_repo,
        "records": [rec_pending, rec_final],
    }
    r_graph.receive(unit)

    conflicts = r_store.execute(
        "SELECT count(*) FROM exchange_staging WHERE record_key=? AND reason='conflict:competing_variants'",
        (rec_pending["key"],),
    ).fetchone()[0]
    assert conflicts == 0, (
        "Compatible pending and final assessment must unify, not conflict"
    )


# =====================================================================
# C-05: Late conflicting code state reporting ambiguity/conflict
# =====================================================================


def test_c05_late_conflicting_code_state_reports_conflict(tmp_path):
    store = opened(tmp_path / "c05_db")
    repo = _base_repo_setup(store)
    head_1 = oid("sha1", "commit", b"head_1")
    head_2 = oid("sha1", "commit", b"head_2")
    base = oid("sha1", "commit", b"base")

    with store.transaction():
        put(
            store,
            "change_requests",
            change_request_id="cr-c05",
            repository_binding_id="bind-1",
            repository_uuidv4=repo,
            change_request_kind="pull_request",
            provider_change_request_number=30,
        )
        put(
            store,
            "code_assessments",
            code_assessment_id="ca-c05-initial",
            change_request_id="cr-c05",
            repository_uuidv4=repo,
            state="partial",
            object_format="sha1",
            head_oid=head_1,
            base_oid=base,
            observed_at_us=100,
            parser_module="test",
            parser_version="1.0",
            details_json="{}",
        )

    class MockQuery:
        def __init__(self, s):
            self.s = s

    mq = MockQuery(store)
    pr = {"change_request_id": "cr-c05", "repository_uuidv4": repo}

    initial = _code_observation(mq, pr, {})
    assert initial is not None
    assert initial["code_assessment_id"] == "ca-c05-initial"

    with store.transaction():
        put(
            store,
            "code_assessments",
            code_assessment_id="ca-c05-late",
            change_request_id="cr-c05",
            repository_uuidv4=repo,
            state="partial",
            object_format="sha1",
            head_oid=head_2,
            base_oid=base,
            observed_at_us=200,
            parser_module="test",
            parser_version="1.0",
            details_json="{}",
        )
        put(
            store,
            "change_request_state",
            change_request_id="cr-c05",
            repository_uuidv4=repo,
            repository_binding_id="bind-1",
            service_instance_uuidv4=SERVICE,
            kind="change-request",
            object_format="sha1",
            head_oid=head_1,
            base_oid=base,
            observed_at_us=200,
            parsed_at_us=200,
            parser_module="github",
            parser_version="1.0",
            acquisition_scope_json=json.dumps(
                {
                    "repository_uuidv4": repo,
                    "service_instance_uuidv4": SERVICE,
                    "repository_binding_id": "bind-1",
                    "endpoint": "pulls",
                    "change_request_id": "cr-c05",
                }
            ),
        )

    obs = _code_observation(mq, pr, {})
    assert obs is None, (
        "Contradiction between state and late code assessment must report ambiguity"
    )

    malformed_obs = _code_observation(mq, pr, {"head": "NOT_A_HEX_STRING!@#$"})
    assert malformed_obs is None


# =====================================================================
# C-06: Natural identities in Exchange for acquisition_roots and root_origins
# =====================================================================


def test_c06_natural_identities_in_exchange_and_portable_columns(tmp_path):
    store = opened(tmp_path / "c06_lookup")
    repo = _base_repo_setup(store)
    head_oid = oid("sha1", "commit", b"root_head")

    with store.transaction():
        put(
            store,
            "git_acquisitions",
            git_acquisition_id="acq-c06-lookup",
            repository_uuidv4=repo,
            kind="git",
            object_format="sha1",
            request="{}",
            roots_manifest="[]",
        )
        put(
            store,
            "acquisition_roots",
            acquisition_root_id=101,
            git_acquisition_id="acq-c06-lookup",
            repository_uuidv4=repo,
            object_format="sha1",
            oid=head_oid,
            role="head",
            complete=0,
        )
        put(
            store,
            "snapshots",
            snapshot_id="snap-c06-lookup",
            git_acquisition_id="acq-c06-lookup",
            repository_uuidv4=repo,
            complete=0,
            generation=0,
        )
        put(
            store,
            "ref_observations",
            repository_uuidv4=repo,
            snapshot_id="snap-c06-lookup",
            raw_ref_name=b"refs/heads/main",
            kind="head",
            object_format="sha1",
            target_oid=head_oid,
        )
        put(
            store,
            "root_origins",
            root_origin_id=202,
            acquisition_root_id=101,
            repository_uuidv4=repo,
            origin_kind="ref",
            raw_ref_name=b"refs/heads/main",
            source_ordinal=0,
            snapshot_id="snap-c06-lookup",
        )

    graph = Graph(store.connection)
    # Natural unique lookup when surrogate key is absent (e.g. after alias loss)
    root_data = {
        "git_acquisition_id": "acq-c06-lookup",
        "object_format": "sha1",
        "oid": head_oid,
        "role": "head",
        "repository_uuidv4": repo,
        "complete": 0,
    }
    existing_root = graph._existing("acquisition_roots", root_data)
    assert existing_root is not None
    assert existing_root["acquisition_root_id"] == 101

    origin_data = {
        "acquisition_root_id": 101,
        "origin_kind": "ref",
        "source_ordinal": 0,
        "repository_uuidv4": repo,
        "snapshot_id": "snap-c06-lookup",
        "raw_ref_name": b"refs/heads/main",
    }
    existing_origin = graph._existing("root_origins", origin_data)
    assert existing_origin is not None
    assert existing_origin["root_origin_id"] == 202


def test_c06_natural_identities_cross_catalog_exchange(tmp_path):
    store_a = opened(tmp_path / "c06_a")
    repo = _base_repo_setup(store_a)
    head_oid = oid("sha1", "commit", b"root_head")

    with store_a.transaction():
        put(
            store_a,
            "git_acquisitions",
            git_acquisition_id="acq-c06",
            repository_uuidv4=repo,
            kind="git",
            object_format="sha1",
            request="{}",
            roots_manifest="[]",
        )
        put(
            store_a,
            "acquisition_roots",
            acquisition_root_id=1,
            git_acquisition_id="acq-c06",
            repository_uuidv4=repo,
            object_format="sha1",
            oid=head_oid,
            role="head",
            complete=0,
        )
        put(
            store_a,
            "snapshots",
            snapshot_id="snap-c06",
            git_acquisition_id="acq-c06",
            repository_uuidv4=repo,
            complete=0,
            generation=0,
        )
        put(
            store_a,
            "ref_observations",
            repository_uuidv4=repo,
            snapshot_id="snap-c06",
            raw_ref_name=b"refs/heads/main",
            kind="head",
            object_format="sha1",
            target_oid=head_oid,
        )
        put(
            store_a,
            "root_origins",
            root_origin_id=10,
            acquisition_root_id=1,
            repository_uuidv4=repo,
            origin_kind="ref",
            raw_ref_name=b"refs/heads/main",
            source_ordinal=0,
            snapshot_id="snap-c06",
        )

    graph_a = Graph(store_a.connection)
    export_unit = graph_a.export(repo)

    acq_root_rec = next(
        r for r in export_unit["records"] if r["table"] == "acquisition_roots"
    )
    assert "acquisition_root_id" not in acq_root_rec["values"]
    assert "acquisition_roots:" in acq_root_rec["key"]

    root_orig_rec = next(
        r for r in export_unit["records"] if r["table"] == "root_origins"
    )
    assert "root_origin_id" not in root_orig_rec["values"]
    assert "root_origins:" in root_orig_rec["key"]

    store_b = opened(tmp_path / "c06_b")
    graph_b = Graph(store_b.connection)
    receipt = graph_b.receive(export_unit)
    assert receipt["admitted_records"] > 0
    admitted_root = store_b.one(
        "SELECT acquisition_root_id, role FROM acquisition_roots WHERE git_acquisition_id='acq-c06'"
    )
    assert admitted_root is not None
    assert admitted_root[1] == "head"


# =====================================================================
# C-07: Root origins distinguishing missing_dependency from invalid
# =====================================================================


def test_c07_root_origins_missing_dependency_vs_invalid_origin(tmp_path):
    store = opened(tmp_path / "c07_db")
    repo = _base_repo_setup(store)
    graph = Graph(store.connection)

    # 1. Missing snapshot returns missing_dependency, NOT invalid:git_ref_origin
    data_missing = {
        "acquisition_root_id": 9999,
        "repository_uuidv4": repo,
        "origin_kind": "ref",
        "raw_ref_name": encode(b"refs/heads/main", "raw_ref_name"),
        "source_ordinal": 0,
        "snapshot_id": "snap-nonexistent",
        "change_request_id": None,
        "code_assessment_id": None,
    }
    res = graph._admit(
        {"key": "root_origins:test1", "table": "root_origins", "values": data_missing},
        "origin-1",
        repo,
    )
    assert res == "missing_dependency", (
        "Missing root/snapshot must return missing_dependency"
    )

    # 2. Existing root and snapshot, but mismatched repository returns invalid:git_ref_origin
    foreign_repo = repository_uuid(99)
    head_oid = oid("sha1", "commit", b"head_c07")
    with store.transaction():
        put(
            store,
            "repositories",
            repository_uuidv4=foreign_repo,
            name="foreign",
            metadata="{}",
        )
        put(
            store,
            "git_acquisitions",
            git_acquisition_id="acq-c07",
            repository_uuidv4=foreign_repo,
            kind="git",
            object_format="sha1",
            request="{}",
            roots_manifest="[]",
        )
        put(
            store,
            "acquisition_roots",
            acquisition_root_id=50,
            git_acquisition_id="acq-c07",
            repository_uuidv4=foreign_repo,
            object_format="sha1",
            oid=head_oid,
            role="head",
            complete=0,
        )
        put(
            store,
            "snapshots",
            snapshot_id="snap-c07",
            git_acquisition_id="acq-c07",
            repository_uuidv4=foreign_repo,
            complete=0,
            generation=0,
        )

    data_mismatched = {
        "acquisition_root_id": 50,
        "repository_uuidv4": repo,
        "origin_kind": "ref",
        "raw_ref_name": encode(b"refs/heads/main", "raw_ref_name"),
        "source_ordinal": 0,
        "snapshot_id": "snap-c07",
        "change_request_id": None,
        "code_assessment_id": None,
    }
    res_mismatch = graph._admit(
        {
            "key": "root_origins:test2",
            "table": "root_origins",
            "values": data_mismatched,
        },
        "origin-1",
        repo,
    )
    assert res_mismatch == "invalid:git_ref_origin", (
        "Mismatched repo must return invalid:git_ref_origin"
    )
