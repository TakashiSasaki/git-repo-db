"""Bounded SQL work for actual current Provider comment units and exact replays."""

from contextlib import closing

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.provider_acquisition import (
    ProviderIntakeBatch,
    ProviderReviewCommentIntake,
)
from tests.integration.p3.test_production_context import SERVICE, directory

__all__ = ["directory"]


def test_actual_comment_units_and_replay_sql_work_do_not_scan_older_comment_roster(
    directory,
):
    parent = ResourceKey.from_native(SERVICE, "pull_request", "20")
    keys = {
        ResourceKey.document(parent, "comment", "review_comment", str(position + 1))
        for position in range(544)
    }
    grants = DependencySet(resources=keys | {parent}, provider_registrations={SERVICE})
    authorization, admission, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    app = ProviderAcquisition(
        directory, authorization=authorization, admission=admission
    )
    origin = canonical(
        {
            "source": "actual bounded comment batch",
            "evidence": "single real source traversal",
        }
    )
    with closing(connect(directory / "context.sqlite3", "context")) as db:
        with Context.owned_transaction(
            db, directory, authorization=authorization, admission=admission
        ) as context:
            context.provider(SERVICE, "github")

            def insert(start, end):
                batch = ProviderIntakeBatch(
                    SERVICE,
                    review_comments=tuple(
                        ProviderReviewCommentIntake(
                            "20",
                            {
                                "id": "node-" + str(position),
                                "fullDatabaseId": str(position + 1),
                                "body": "one exact shared body",
                            },
                            100,
                            origin,
                            graphql=True,
                        )
                        for position in range(start, end)
                    ),
                )
                return app.admit_batch(batch, context=context)

            def measured(start, end):
                steps = [0]

                def step():
                    steps[0] += 1
                    return 0

                db.set_progress_handler(step, 1)
                try:
                    insert(start, end)
                finally:
                    db.set_progress_handler(None, 0)
                return steps[0]

            insert(0, 64)
            early, replay_early = measured(64, 96), measured(64, 96)
            insert(96, 512)
            late, replay_late = measured(512, 544), measured(512, 544)
            assert early > 0 and late <= early * 1.5, (early, late)
            assert replay_early > 0 and replay_late <= replay_early * 1.5, (
                replay_early,
                replay_late,
            )
            assert (
                db.execute(
                    "SELECT count(*) FROM resources WHERE resource_kind='comment'"
                ).fetchone()[0]
                == 544
            )
            assert db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 1
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                )
            }
            assert not tables & {
                "exchange_staging",
                "document_observations",
                "fetch_occurrences",
                "parsed_results",
            }
    assert not (directory / "core.sqlite3").exists()
