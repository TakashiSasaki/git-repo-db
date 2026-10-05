from __future__ import annotations

import os
import shutil
import time

from repo_catalog.adapters.filesystem.capacity import allocated_bytes
from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.git.runner import hook
from repo_catalog.domain.models import CatalogError, Waiting


class CacheManager:
    def __init__(self, store):
        self.s = store

    def paths(self, row):
        expected = f"cache/{row['repo_id']}/{row['generation']}.git"
        if row["path"] != expected:
            raise CatalogError(
                "UNMANAGED_CACHE_PATH", "Cache path is not a managed generation"
            )
        path = self.s.path / expected
        if path.is_symlink() or not path.resolve().is_relative_to(
            (self.s.path / "cache").resolve()
        ):
            raise CatalogError(
                "UNMANAGED_CACHE_PATH", "Refusing cache symlink or escaped path"
            )
        quarantine = self.s.path / "quarantine" / row["id"]
        if quarantine.is_symlink():
            raise CatalogError("UNMANAGED_CACHE_PATH", "Quarantine cannot be a symlink")
        return path, quarantine

    def gate(self, row):
        s = self.s
        if s.config["preservation"]["profile"] != "catalog-text-v1":
            return ["unknown_profile"]
        obligations = s.all(
            "SELECT * FROM preservation_obligations WHERE cache_id=?", (row["id"],)
        )
        reasons = []
        for r in obligations:
            if r["roots_fixed"] and not all(
                r[k]
                for k in ("structure_done", "digest_done", "text_done", "published")
            ):
                reasons.append("pending_obligations:" + r["run_id"])
        # No fixed roots means failed transfer work; OS lock must prove all users stopped.
        return reasons

    def collect(self, *, apply=False, pressure=False):
        s = self.s
        results = []
        rows = s.all(
            "SELECT * FROM cache_entries WHERE state IN ('available','evicting') ORDER BY last_used,id"
        )
        from repo_catalog.adapters.filesystem.capacity import Capacity

        used = Capacity(s).used()
        cfg = s.config["cache"]
        for row in rows:
            path, quarantine = self.paths(row)
            reasons = self.gate(row)
            bytes_used = allocated_bytes(path) + allocated_bytes(quarantine)
            ttl = time.time() - row["last_used"] >= cfg["ttl_seconds"]
            candidate = (
                row["state"] == "evicting"
                or ttl
                or pressure
                and used > cfg["max_bytes"] * cfg["low_water_ratio"]
            )
            try:
                with FileLock(s.path / f"locks/cache-{row['id']}.lock"):
                    latest = s.one(
                        "SELECT * FROM cache_entries WHERE id=?", (row["id"],)
                    )
                    reasons = self.gate(latest)
                    if apply and candidate and not reasons:
                        # Leases of dead parents are safe to clear only after the inherited OS lock is acquired.
                        with s.transaction():
                            s.execute(
                                "DELETE FROM cache_leases WHERE cache_id=?",
                                (row["id"],),
                            )
                            s.execute(
                                "UPDATE cache_entries SET state='evicting' WHERE id=?",
                                (row["id"],),
                            )
                        if path.exists():
                            if quarantine.exists():
                                raise CatalogError(
                                    "CACHE_INTEGRITY",
                                    "Both generation and quarantine exist",
                                )
                            os.rename(path, quarantine)
                            fd = os.open(quarantine.parent, os.O_RDONLY)
                            try:
                                os.fsync(fd)
                            finally:
                                os.close(fd)
                        hook("after_gc_rename")
                        if quarantine.exists():
                            shutil.rmtree(quarantine)
                        if path.exists() or quarantine.exists():
                            raise CatalogError(
                                "CACHE_INTEGRITY", "Cache deletion not complete"
                            )
                        with s.transaction():
                            s.execute(
                                "UPDATE cache_entries SET state='evicted',bytes=0 WHERE id=?",
                                (row["id"],),
                            )
                            s.execute(
                                "UPDATE content_locations SET state='unavailable' WHERE cache_id=?",
                                (row["id"],),
                            )
                        used -= bytes_used
                        action = "evicted"
                    else:
                        action = (
                            "candidate" if candidate and not reasons else "retained"
                        )
            except Waiting:
                reasons.append("generation_in_use")
                action = "retained"
            results.append(
                {
                    "cache_id": row["id"],
                    "bytes": bytes_used,
                    "ttl_expired": ttl,
                    "action": action,
                    "blocked_by": reasons,
                }
            )
        return results

    def recover(self):
        return self.collect(apply=True, pressure=False)
