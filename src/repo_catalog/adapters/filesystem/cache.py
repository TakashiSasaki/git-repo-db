from __future__ import annotations

import os
import shutil
from decimal import Decimal

from repo_catalog.adapters.filesystem.capacity import allocated_bytes
from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.git.runner import hook
from repo_catalog.domain.models import CatalogError, Waiting
from repo_catalog.domain.time import now_us


class CacheManager:
    def __init__(self, store):
        self.s = store

    def paths(self, row):
        expected = f"cache/{row['repository_id']}/{row['generation']}.git"
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
        quarantine = self.s.path / "quarantine" / row["active_cache_entry_id"]
        if quarantine.is_symlink() or not quarantine.resolve().is_relative_to(
            (self.s.path / "quarantine").resolve()
        ):
            raise CatalogError(
                "UNMANAGED_CACHE_PATH", "Refusing quarantine symlink or escaped path"
            )
        return path, quarantine

    def gate(self, row):
        s = self.s
        if s.config["preservation"]["profile"] != "catalog-text-v1":
            return ["unknown_profile"]
        obligations = s.all(
            "SELECT * FROM preservation_obligations WHERE cache_locator_id=?",
            (
                row["cache_locator_id"]
                if "cache_locator_id" in row.keys()
                else row["active_cache_entry_id"],
            ),
        )
        reasons = []
        for r in obligations:
            if r["roots_fixed"] and not all(
                r[k]
                for k in ("structure_done", "digest_done", "text_done", "published")
            ):
                reasons.append("pending_obligations:" + r["git_acquisition_id"])
        # No fixed roots means failed transfer work; OS lock must prove all users stopped.
        return reasons

    def collect(self, *, apply=False, pressure=False):
        s = self.s
        results = []
        rows = s.all(
            "SELECT a.*,l.repository_id,l.path,l.access FROM active_cache_entries a JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE l.access='target_active' AND a.state IN ('active','evicting') ORDER BY a.last_used_us,a.active_cache_entry_id"
        )
        from repo_catalog.adapters.filesystem.capacity import Capacity

        used = Capacity(s).used()
        cfg = s.config["cache"]
        # Configured TTL is an elapsed duration, independent of the epoch range.
        ttl_us = Decimal(str(cfg["ttl_seconds"])) * 1_000_000
        for row in rows:
            path, quarantine = self.paths(row)
            reasons = self.gate(row)
            bytes_used = allocated_bytes(path) + allocated_bytes(quarantine)
            ttl = now_us() - row["last_used_us"] >= ttl_us
            candidate = (
                row["state"] == "evicting"
                or ttl
                or pressure
                and used > cfg["max_bytes"] * cfg["low_water_ratio"]
            )
            try:
                with FileLock(
                    s.path / f"locks/cache-{row['active_cache_entry_id']}.lock"
                ):
                    latest = s.one(
                        "SELECT a.*,l.repository_id,l.path,l.access FROM active_cache_entries a JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE a.active_cache_entry_id=? AND l.access='target_active'",
                        (row["active_cache_entry_id"],),
                    )
                    if latest is None:
                        raise CatalogError(
                            "CACHE_INTEGRITY", "Active cache disappeared"
                        )
                    reasons = self.gate(latest)
                    if apply and candidate and not reasons:
                        # Leases of dead parents are safe to clear only after the inherited OS lock is acquired.
                        with s.transaction():
                            s.execute(
                                "DELETE FROM cache_leases WHERE active_cache_entry_id=?",
                                (row["active_cache_entry_id"],),
                            )
                            s.execute(
                                "UPDATE active_cache_entries SET state='evicting' WHERE active_cache_entry_id=?",
                                (row["active_cache_entry_id"],),
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
                                "UPDATE active_cache_entries SET state='evicted',bytes=0 WHERE active_cache_entry_id=?",
                                (row["active_cache_entry_id"],),
                            )
                            s.execute(
                                "UPDATE cache_locators SET state='missing' WHERE cache_locator_id=? AND access='target_active'",
                                (row["cache_locator_id"],),
                            )
                            s.execute(
                                "UPDATE content_locations SET state='unavailable' WHERE cache_locator_id=?",
                                (row["cache_locator_id"],),
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
                    "active_cache_entry_id": row["active_cache_entry_id"],
                    "bytes": bytes_used,
                    "ttl_expired": ttl,
                    "action": action,
                    "blocked_by": reasons,
                }
            )
        return results

    def recover(self):
        return self.collect(apply=True, pressure=False)
