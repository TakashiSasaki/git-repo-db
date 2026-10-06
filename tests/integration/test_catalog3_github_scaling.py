"""Deterministic work bounds for large GitHub document collections."""

from repo_catalog.adapters.github.persistence import ApiFacts
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.maintenance_service import MaintenanceService

TIME = "2026-10-06T00:00:00Z"


def test_new_graphql_comments_have_bounded_sqlite_work(tmp_path):
    state = tmp_path / "state"
    MaintenanceService(state).init("catalog-text-v1", 64 * 1024 * 1024, 0)
    with Store(state) as store:
        assert store.one("PRAGMA foreign_keys")[0] == 1
        assert store.one("PRAGMA recursive_triggers")[0] == 1
        facts = ApiFacts(store, store.config["github"])
        collection = {"fetch_collection_id": "collection", "change_request_id": "pr"}
        with store.transaction():
            store.execute(
                "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES('00000000-0000-4000-8000-000000000101','github','synthetic','{}')"
            )
            store.execute(
                "INSERT INTO repositories(repository_id,name,metadata) VALUES('repo','synthetic','{}')"
            )
            store.execute(
                "INSERT INTO repository_bindings(repository_binding_id,repository_id,service_instance_uuidv4,provider_repository_id,metadata) VALUES('binding','repo','00000000-0000-4000-8000-000000000101','repo','{}')"
            )
            store.execute(
                "INSERT INTO change_requests(change_request_id,repository_id,repository_binding_id,request_kind,number) VALUES('pr','repo','binding','pull_request',1)"
            )
            store.execute(
                "INSERT INTO resume_scopes(resume_scope_id,repository_id,repository_binding_id,request_context,parser_version,profile_version,confidence) VALUES('scope','repo','binding','{}','catalog3-github/1','catalog-text-v1','proven')"
            )
            store.execute(
                "INSERT INTO fetch_collections(fetch_collection_id,repository_id,change_request_id,kind,resume_scope_id,observed_at) VALUES('collection','repo','pr','threads','scope',?)",
                (TIME,),
            )
            occurrence = store.execute(
                "INSERT INTO fetch_occurrences(fetch_collection_id,ordinal,payload_id,request,observed_at,parsed_at) VALUES('collection',0,?,'{}',?,?)",
                (facts.payload(b"{}"), TIME, TIME),
            ).lastrowid
            store.execute(
                "INSERT INTO review_threads(review_thread_id,change_request_id,payload,observed_at) VALUES('thread','pr','{}',?)",
                (TIME,),
            )

            def insert_comments(start, end):
                for position in range(start, end):
                    facts.document(
                        "pr",
                        "review-comment",
                        str(position),
                        "shared comment body",
                        {"id": f"node-{position}", "body": "shared comment body"},
                        collection,
                        occurrence,
                        position,
                        TIME,
                        thread="thread",
                    )

            def measured_comments(start, end):
                steps = 0

                def count_step():
                    nonlocal steps
                    steps += 1
                    return 0

                store.connection.set_progress_handler(count_step, 1)
                try:
                    insert_comments(start, end)
                finally:
                    store.connection.set_progress_handler(None, 0)
                return steps

            def fact_counts():
                return tuple(
                    store.one(f"SELECT count(*) FROM {table}")[0]
                    for table in (
                        "documents",
                        "document_observations",
                    )
                )

            insert_comments(0, 64)
            early_steps = measured_comments(64, 96)
            early_counts = fact_counts()
            early_replay_steps = measured_comments(64, 96)
            assert fact_counts() == early_counts == (96, 96)
            insert_comments(96, 512)
            late_steps = measured_comments(512, 544)
            late_counts = fact_counts()
            late_replay_steps = measured_comments(512, 544)
            assert fact_counts() == late_counts == (544, 544)

        # Count actual SQLite instructions, including all ownership/FK triggers,
        # rather than elapsed time. A missing replay or node lookup index makes
        # each new comment scan earlier comments; allow modest B-tree variation.
        assert early_steps > 0
        assert late_steps <= early_steps * 1.5, ("new", early_steps, late_steps)
        assert early_replay_steps > 0
        assert late_replay_steps <= early_replay_steps * 1.5, (
            "replay",
            early_replay_steps,
            late_replay_steps,
        )
        for table in (
            "documents",
            "document_observations",
            "review_comments",
            "collection_memberships",
        ):
            assert store.one(f"SELECT count(*) FROM {table}")[0] == 544
        assert store.one("SELECT count(*) FROM text_bodies")[0] == 1
        assert (
            store.one(
                "SELECT count(*) FROM document_observations WHERE fetch_occurrence_id=?",
                (occurrence,),
            )[0]
            == 544
        )
        assert not store.all("PRAGMA foreign_key_check")
