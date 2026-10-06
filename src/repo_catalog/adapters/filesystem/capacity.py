import os
import shutil
from pathlib import Path

from repo_catalog.domain.models import CatalogError, Waiting


def allocated_bytes(path):
    seen = set()
    total = 0
    if not Path(path).exists():
        return 0
    for root, dirs, names in os.walk(path, followlinks=False):
        for name in names + dirs:
            try:
                st = os.lstat(Path(root) / name)
            except FileNotFoundError:
                # Git can rename/delete temporary pack files during monitoring.
                # The next scan and physical-free-space check cover the new path.
                continue
            key = (st.st_dev, st.st_ino)
            if key not in seen:
                total += st.st_blocks * 512
                seen.add(key)
    return total


class Capacity:
    def __init__(self, store):
        self.store = store

    def used(self):
        return sum(
            allocated_bytes(self.store.path / name)
            for name in ("cache", "work", "quarantine")
        )

    def attempt(self, job_id):
        row = self.store.one("SELECT current_attempt FROM jobs WHERE id=?", (job_id,))
        if row is None or row[0] is None:
            raise CatalogError("CAPACITY_ERROR", "Job has no current attempt")
        return row[0]

    def reserved_elsewhere(self, job_id, attempt):
        return self.store.one(
            "SELECT coalesce(sum(max(reserved-consumed,0)),0) FROM space_reservations "
            "WHERE NOT(job_id=? AND attempt=?)",
            (job_id, attempt),
        )[0]

    def reserve(self, job_id, peak):
        cfg = self.store.config["cache"]
        used = self.used()
        free = shutil.disk_usage(self.store.path).free
        with self.store.transaction():
            attempt = self.attempt(job_id)
            other = self.reserved_elsewhere(job_id, attempt)
            if (
                used + other + peak > cfg["max_bytes"]
                or free - other < peak + cfg["min_free_bytes"]
            ):
                raise Waiting(
                    "CAPACITY_WAIT",
                    "Insufficient cache budget or physical headroom",
                    {
                        "used": used,
                        "reserved_elsewhere": other,
                        "peak": peak,
                        "free": free,
                    },
                    retryable=True,
                )
            if self.store.one(
                "SELECT 1 FROM space_reservations WHERE job_id=? AND attempt=?",
                (job_id, attempt),
            ):
                self.store.execute(
                    "UPDATE space_reservations SET reserved=?,consumed=0 WHERE job_id=? AND attempt=?",
                    (peak, job_id, attempt),
                )
            else:
                self.store.execute(
                    "INSERT INTO space_reservations(job_id,attempt,reserved,consumed) VALUES(?,?,?,0)",
                    (job_id, attempt, peak),
                )

    def monitor(self, job_id, baseline):
        used = self.used()
        consumed = max(0, used - baseline)
        attempt = self.attempt(job_id)
        row = self.store.one(
            "SELECT reserved FROM space_reservations WHERE job_id=? AND attempt=?",
            (job_id, attempt),
        )
        if row is None:
            raise CatalogError("CAPACITY_ERROR", "Missing admission reservation")
        peak = max(row[0], consumed + 1048576)
        other = self.reserved_elsewhere(job_id, attempt)
        remaining = max(peak - consumed, 0)
        cfg = self.store.config["cache"]
        if (
            used + other + remaining > cfg["max_bytes"]
            or shutil.disk_usage(self.store.path).free - other
            < remaining + cfg["min_free_bytes"]
        ):
            raise Waiting(
                "CAPACITY_WAIT",
                "Transfer exceeded available peak capacity",
                retryable=True,
            )
        with self.store.transaction():
            self.store.execute(
                "UPDATE space_reservations SET reserved=?,consumed=? WHERE job_id=? AND attempt=?",
                (peak, consumed, job_id, attempt),
            )

    def release(self, job):
        self.store.execute(
            "DELETE FROM space_reservations WHERE job_id=? AND attempt=?",
            (job, self.attempt(job)),
        )
