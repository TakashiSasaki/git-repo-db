import json
import time
import uuid

from repo_catalog.domain.models import CatalogError, now


class JobService:
    def __init__(self, store):
        self.store = store

    def create(self, kind, request):
        job = str(uuid.uuid4())
        with self.store.transaction():
            self.store.execute(
                "INSERT INTO jobs(id,kind,request,state,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (job, kind, json.dumps(request), "running", now(), now()),
            )
        return job

    def resume(self, job):
        row = self.store.one("SELECT * FROM jobs WHERE id=?", (job,))
        if not row:
            raise CatalogError("NOT_FOUND", "Job not found")
        if row["state"] in ("complete", "cancelled"):
            raise CatalogError("INVALID_ARGUMENT", "Job is not resumable")
        if row["not_before"] and row["not_before"] > time.time():
            from repo_catalog.domain.models import Waiting

            raise Waiting(
                "NOT_BEFORE",
                "Job is waiting for its scheduled retry",
                {"not_before": row["not_before"]},
                True,
            )
        with self.store.transaction():
            self.store.execute(
                "UPDATE jobs SET state='running',attempt=attempt+1,not_before=NULL,reason=NULL,updated_at=? WHERE id=?",
                (now(), job),
            )
        return row["kind"], json.loads(row["request"])

    def update(self, job, state, reason=None, not_before=None):
        with self.store.transaction():
            self.store.execute(
                "UPDATE jobs SET state=?,reason=?,not_before=?,updated_at=? WHERE id=?",
                (state, reason, not_before, now(), job),
            )

    def cancel(self, job):
        row = self.store.one("SELECT state FROM jobs WHERE id=?", (job,))
        if not row:
            raise CatalogError("NOT_FOUND", "Job not found")
        if row[0] == "running":
            raise CatalogError("JOB_RUNNING", "Use SIGINT on the foreground process")
        if row[0] not in ("queued", "waiting"):
            raise CatalogError(
                "INVALID_ARGUMENT", "Only queued/waiting jobs can be cancelled"
            )
        self.update(job, "cancelled")
