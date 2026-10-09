"""Deterministic SQL work bounds for large mutable GitHub comment collections."""

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.domain.models import CancellationToken
from repo_catalog.domain.time import parse_iso8601_us
from tests.support.github_runtime import github_runtime as github_runtime

TIME = parse_iso8601_us("2026-10-06T00:00:00Z")


def test_new_graphql_comments_have_bounded_sqlite_work(github_runtime):
    store, repo, _, _ = github_runtime
    collector = GitHubCollector(store, CancellationToken())
    pr = {"change_request_id": "pr"}
    try:
        with store.transaction():
            store.execute(
                "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES('pr',?,'binding','pull_request',1)",
                (repo["repository_uuidv4"],),
            )
            store.execute(
                "INSERT INTO review_threads(change_request_id,provider_resource_id) VALUES('pr','thread')"
            )
            collector.facts.current_context(
                repo, "pr", collector.http.graphql, "review-comment"
            )

            def insert_comments(start, end):
                connection = {
                    "nodes": [
                        {
                            "id": f"node-{position}",
                            "fullDatabaseId": str(position + 1),
                            "body": "shared comment body",
                        }
                        for position in range(start, end)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
                collector._thread_documents(
                    repo,
                    pr,
                    "thread",
                    connection,
                    {},
                    None,
                    start,
                    TIME,
                    base_revision=store.revision(),
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

            insert_comments(0, 64)
            early_steps = measured_comments(64, 96)
            early_replay_steps = measured_comments(64, 96)
            assert store.one("SELECT count(*) FROM review_resources")[0] == 96
            insert_comments(96, 512)
            late_steps = measured_comments(512, 544)
            late_replay_steps = measured_comments(512, 544)
            assert store.one("SELECT count(*) FROM review_resources")[0] == 544

        # Include all production SQL validation/FK triggers. Linear admission
        # work cannot depend on how many older comments already exist.
        assert early_steps > 0
        assert late_steps <= early_steps * 1.5, ("new", early_steps, late_steps)
        assert early_replay_steps > 0
        assert late_replay_steps <= early_replay_steps * 1.5, (
            "same",
            early_replay_steps,
            late_replay_steps,
        )
        assert store.one("SELECT count(*) FROM text_bodies")[0] == 1
        for table in (
            "documents",
            "document_observations",
            "fetch_occurrences",
            "collection_memberships",
            "exchange_staging",
        ):
            assert store.one(f"SELECT count(*) FROM {table}")[0] == 0
        assert not store.all("PRAGMA foreign_key_check")
    finally:
        collector.http.close()
