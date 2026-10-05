"""Measure two candidate FK lookup indexes on synthetic, throwaway v2 data.

Not a target-DDL benchmark or production migration. Never accepts a real DB.
"""

import json
import tempfile
from pathlib import Path

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.collection_service import CollectionService
from repo_catalog.application.maintenance_service import MaintenanceService


def probe(rows=1000):
    with tempfile.TemporaryDirectory(prefix="repo-catalog-index-probe-") as directory:
        state = Path(directory) / "state"
        maintenance = MaintenanceService(state)
        maintenance.init("catalog-text-v1", 67108864, 0)
        source = maintenance.source_add(
            "git-url", name="synthetic", url="file:///synthetic/app.git"
        ).data["source_id"]
        repo = (
            CollectionService(state).discover(source).data["repositories"][0]["repo_id"]
        )
        with Store(state) as db:
            job = db.one("SELECT id FROM jobs")[0]
            pr = repo + ":41"
            with db.transaction():
                db.execute(
                    "INSERT INTO pull_requests VALUES(?,?,41,NULL,NULL)", (pr, repo)
                )
                for ordinal in range(rows):
                    db.execute(
                        "INSERT INTO pr_observations(pr_id,job_id,observed_at,payload) VALUES(?,?,?,'{}')",
                        (pr, job, "2026-01-01T00:00:00+00:00"),
                    )
                    db.execute(
                        "INSERT INTO collections VALUES(?,?,?,'synthetic',?,'complete','{}',NULL,?,NULL)",
                        (
                            "synthetic-" + str(ordinal),
                            pr,
                            repo,
                            job,
                            "2026-01-01T00:00:00+00:00",
                        ),
                    )
            result = []
            for table, columns, parameter in (
                ("pr_observations", "pr_id,id", pr),
                ("collections", "repo_id,pr_id,kind", repo),
            ):
                first_column = columns.split(",")[0]
                sql = f"SELECT 1 FROM {table} WHERE {first_column}=?"
                before = [
                    r[3] for r in db.all("EXPLAIN QUERY PLAN " + sql, (parameter,))
                ]
                page_before = db.one("PRAGMA page_count")[0]
                index = "probe_" + table
                with db.transaction():
                    db.execute(f"CREATE INDEX {index} ON {table}({columns})")
                after = [
                    r[3] for r in db.all("EXPLAIN QUERY PLAN " + sql, (parameter,))
                ]
                page_size = db.one("PRAGMA page_size")[0]
                result.append(
                    {
                        "table": table,
                        "rows": rows,
                        "columns": columns,
                        "plan_before": before,
                        "plan_after": after,
                        "added_database_pages": db.one("PRAGMA page_count")[0]
                        - page_before,
                        "page_size": page_size,
                    }
                )
            return {
                "fixture_only": True,
                "purpose": "FK child lookup plan and incremental space, not runtime throughput",
                "results": result,
                "limitations": [
                    "All rows share one synthetic parent",
                    "No estimate of target DB growth or trigger/write throughput",
                    "Full target indexes require representative measurement",
                ],
            }


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2, sort_keys=True))
