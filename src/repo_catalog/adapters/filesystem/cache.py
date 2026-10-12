from __future__ import annotations

import os
import shutil
import uuid
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
        expected = f"cache/{row['repository_uuidv4']}/{row['generation']}.git"
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
        entry_id = (
            row["active_cache_entry_id"]
            if "active_cache_entry_id" in row.keys()
            else None
        )
        repo_uuid = (
            row["repository_uuidv4"] if "repository_uuidv4" in row.keys() else None
        )
        acq_rows = (
            s.operational.all(
                "SELECT git_acquisition_id FROM acquisition_progress WHERE active_cache_entry_id=?",
                (entry_id,),
            )
            if entry_id
            else []
        )
        acq_ids = [r["git_acquisition_id"] for r in acq_rows]
        reasons = []
        if acq_ids:
            placeholders = ",".join("?" for _ in acq_ids)
            obligations = s.all(
                f"SELECT * FROM preservation_obligations WHERE git_acquisition_id IN ({placeholders})",
                acq_ids,
            )
            for r in obligations:
                if r["roots_fixed"] and not all(
                    r[k]
                    for k in (
                        "structure_done",
                        "digest_done",
                        "text_done",
                        "complete",
                    )
                ):
                    reasons.append("pending_obligations:" + r["git_acquisition_id"])

        # Fail-closed preservation protection against Operational DB loss / uncertain associations:
        if repo_uuid:
            pending_core = s.all(
                "SELECT p.git_acquisition_id FROM preservation_obligations p "
                "JOIN git_acquisitions a ON a.git_acquisition_id=p.git_acquisition_id "
                "WHERE a.repository_uuidv4=? AND p.roots_fixed=1 AND (p.complete=0 OR p.structure_done=0 OR p.digest_done=0 OR p.text_done=0)",
                (repo_uuid,),
            )
            for p in pending_core:
                p_acq_id = p["git_acquisition_id"]
                if f"pending_obligations:{p_acq_id}" in reasons:
                    continue
                mapped = s.operational.all(
                    "SELECT active_cache_entry_id FROM acquisition_progress WHERE git_acquisition_id=?",
                    (p_acq_id,),
                )
                mapped_ids = [m["active_cache_entry_id"] for m in mapped]
                if not mapped_ids:
                    # Missing operational association must not authorize deletion (fail-closed)
                    reasons.append("pending_obligations:" + p_acq_id)
                elif entry_id and entry_id in mapped_ids:
                    reasons.append("pending_obligations:" + p_acq_id)
                else:
                    ph = ",".join("?" for _ in mapped_ids)
                    active_count = s.operational.one(
                        f"SELECT count(*) FROM active_cache_entries WHERE active_cache_entry_id IN ({ph}) AND state='active'",
                        mapped_ids,
                    )[0]
                    if active_count == 0:
                        reasons.append("pending_obligations:" + p_acq_id)
        return reasons

    def _enroll_orphaned_generations(self):
        s = self.s
        cache_base = s.path / "cache"
        if not cache_base.exists() or not cache_base.is_dir():
            return
        for repo_dir in cache_base.iterdir():
            if not repo_dir.is_dir() or repo_dir.is_symlink():
                continue
            repo_uuid = repo_dir.name
            for gen_dir in repo_dir.iterdir():
                if not gen_dir.is_dir() or gen_dir.is_symlink():
                    continue
                if not gen_dir.name.endswith(".git"):
                    continue
                gen_str = gen_dir.name[:-4]
                if not gen_str.isdigit():
                    continue
                gen = int(gen_str)
                rel_path = f"cache/{repo_uuid}/{gen_dir.name}"
                loc = s.operational.one(
                    "SELECT cache_locator_id FROM cache_locators WHERE path=?",
                    (rel_path,),
                )
                if not loc:
                    cid = str(uuid.uuid4())
                    mtime_us = int(gen_dir.stat().st_mtime * 1_000_000)
                    with s.operational.transaction():
                        s.operational.execute(
                            "INSERT INTO cache_locators(cache_locator_id,repository_uuidv4,path,access,state) VALUES(?,?,?,'target_active','available')",
                            (cid, repo_uuid, rel_path),
                        )
                        s.operational.execute(
                            "INSERT INTO active_cache_entries(active_cache_entry_id,cache_locator_id,generation,state,last_used_us,bytes) VALUES(?,?,?,'active',?,?)",
                            (cid, cid, gen, mtime_us, allocated_bytes(gen_dir)),
                        )

    def collect(self, *, apply=False, pressure=False):
        s = self.s
        self._enroll_orphaned_generations()
        results = []
        rows = s.operational.all(
            "SELECT a.*,l.repository_uuidv4,l.path,l.access FROM active_cache_entries a JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE l.access='target_active' AND a.state IN ('active','evicting') ORDER BY a.last_used_us,a.active_cache_entry_id"
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
                    latest = s.operational.one(
                        "SELECT a.*,l.repository_uuidv4,l.path,l.access FROM active_cache_entries a JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE a.active_cache_entry_id=? AND l.access='target_active'",
                        (row["active_cache_entry_id"],),
                    )
                    if latest is None:
                        raise CatalogError(
                            "CACHE_INTEGRITY", "Active cache disappeared"
                        )
                    reasons = self.gate(latest)
                    if apply and candidate and not reasons:
                        # Leases of dead parents are safe to clear only after the inherited OS lock is acquired.
                        with s.operational.transaction():
                            s.operational.execute(
                                "DELETE FROM cache_leases WHERE active_cache_entry_id=?",
                                (row["active_cache_entry_id"],),
                            )
                            s.operational.execute(
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
                        with s.operational.transaction():
                            s.operational.execute(
                                "UPDATE active_cache_entries SET state='evicted',bytes=0 WHERE active_cache_entry_id=?",
                                (row["active_cache_entry_id"],),
                            )
                            s.operational.execute(
                                "UPDATE cache_locators SET state='missing' WHERE cache_locator_id=? AND access='target_active'",
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
