import json
import time
import uuid

from repo_catalog.domain.models import CatalogError, Waiting, now


class JobService:
    def __init__(self, store, *, clock=time.time):
        self.store, self.clock = store, clock

    def create(self, kind, request):
        job = str(uuid.uuid4())
        timestamp = now()
        with self.store.transaction():
            self.store.execute(
                "INSERT INTO jobs(job_id,kind,request,current_attempt,created_at) VALUES(?,?,?,1,?)",
                (job, kind, json.dumps(request), timestamp),
            )
            self.store.execute(
                "INSERT INTO job_attempts(job_id,attempt,state,created_at,updated_at,not_before,checkpoint,reason) VALUES(?,1,'running',?,?,NULL,'{}',NULL)",
                (job, timestamp, timestamp),
            )
        return job

    def resume(self, job):
        row = self.store.one(
            "SELECT j.*,a.state,a.not_before FROM jobs j JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt WHERE j.job_id=?",
            (job,),
        )
        if not row:
            raise CatalogError("NOT_FOUND", "Job not found")
        if row["kind"] == "legacy":
            raise CatalogError(
                "INVALID_ARGUMENT",
                "Imported historical jobs are evidence, not resumable processes; start a new sync",
            )
        if row["state"] in ("complete", "cancelled"):
            raise CatalogError("INVALID_ARGUMENT", "Job is not resumable")
        if row["not_before"] and row["not_before"] > self.clock():
            raise Waiting(
                "NOT_BEFORE",
                "Job is waiting for its scheduled retry",
                {"not_before": row["not_before"]},
                True,
            )
        timestamp, attempt = now(), row["current_attempt"] + 1
        with self.store.transaction():
            if row["state"] == "running":
                self.store.execute(
                    "UPDATE job_attempts SET state='interrupted',updated_at=?,reason='process_restart' WHERE job_id=? AND attempt=?",
                    (timestamp, job, row["current_attempt"]),
                )
            self.store.execute(
                "INSERT INTO job_attempts(job_id,attempt,state,created_at,updated_at,not_before,checkpoint,reason) VALUES(?,?,'running',?,?,NULL,'{}',NULL)",
                (job, attempt, timestamp, timestamp),
            )
            self.store.execute("DELETE FROM cache_leases WHERE job_id=?", (job,))
            self.store.execute("DELETE FROM space_reservations WHERE job_id=?", (job,))
            self.store.execute(
                "UPDATE jobs SET current_attempt=? WHERE job_id=?", (attempt, job)
            )
        return row["kind"], json.loads(row["request"])

    def update(self, job, state, reason=None, not_before=None):
        with self.store.transaction():
            self.store.execute(
                "UPDATE job_attempts SET state=?,reason=?,not_before=?,updated_at=? WHERE job_id=? AND attempt=(SELECT current_attempt FROM jobs WHERE job_id=?)",
                (state, reason, not_before, now(), job, job),
            )

    def cancel(self, job):
        row = self.store.one(
            "SELECT a.state FROM jobs j JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt WHERE j.job_id=?",
            (job,),
        )
        if not row:
            raise CatalogError("NOT_FOUND", "Job not found")
        if row[0] == "running":
            raise CatalogError("JOB_RUNNING", "Use SIGINT on the foreground process")
        if row[0] not in ("queued", "waiting", "failed", "interrupted"):
            raise CatalogError("INVALID_ARGUMENT", "Job cannot be cancelled")
        self.update(job, "cancelled")
