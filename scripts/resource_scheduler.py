"""Resource-aware worker selection and concurrency budgeting for pytest-xdist."""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import math
import os
import tempfile
from pathlib import Path

# Conservative memory estimate per worker process (in megabytes)
DEFAULT_MEMORY_PER_WORKER_MB = 350.0
PACKAGING_MEMORY_PER_WORKER_MB = 500.0


def get_cpu_affinity() -> int | None:
    """Return the number of CPUs in the current affinity mask, if available."""
    if hasattr(os, "sched_getaffinity"):
        try:
            return len(os.sched_getaffinity(0))
        except OSError:
            return None
    return None


def get_cgroup_cpu_quota() -> float | None:
    """Return the effective CPU quota from cgroups (v2 or v1), or None if unconstrained."""
    # Check cgroup v2
    cgroup2_max = Path("/sys/fs/cgroup/cpu.max")
    if cgroup2_max.is_file():
        try:
            parts = cgroup2_max.read_text(encoding="utf-8").strip().split()
            if len(parts) >= 2 and parts[0] != "max":
                quota = float(parts[0])
                period = float(parts[1])
                if period > 0 and quota > 0:
                    return quota / period
        except (OSError, ValueError):
            pass

    # Check cgroup v1
    v1_quota = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    v1_period = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if v1_quota.is_file() and v1_period.is_file():
        try:
            q = float(v1_quota.read_text(encoding="utf-8").strip())
            p = float(v1_period.read_text(encoding="utf-8").strip())
            if q > 0 and p > 0:
                return q / p
        except (OSError, ValueError):
            pass

    return None


def available_cpu_count() -> int:
    """Determine available logical CPUs considering affinity and cgroup quota."""
    logical = os.cpu_count() or 1
    affinity = get_cpu_affinity()
    base_cpus = affinity if affinity is not None and affinity > 0 else logical

    quota = get_cgroup_cpu_quota()
    if quota is not None and quota > 0:
        quota_cores = max(1, math.floor(quota))
        return min(base_cpus, quota_cores)

    return max(1, base_cpus)


def available_memory_mb() -> float:
    """Estimate available system memory in megabytes without requiring external packages."""
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            total_mb = None
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                key, separator, raw = line.partition(":")
                if not separator or key not in {"MemAvailable", "MemTotal"}:
                    continue
                fields = raw.split()
                if len(fields) != 2 or fields[1] != "kB":
                    continue
                try:
                    kb = float(fields[0])
                except ValueError:
                    continue
                if not math.isfinite(kb) or kb < 0:
                    continue
                if key == "MemAvailable":
                    # Zero is valid pressure: retain it so the worker floor is 1.
                    return kb / 1024.0
                if kb > 0:
                    total_mb = kb / 1024.0
            # /proc normally lists MemTotal first. Only use it after looking
            # through the entire file for a valid MemAvailable record.
            if total_mb is not None:
                return total_mb
        except OSError:
            pass

    # POSIX sysconf fallback
    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return (pages * page_size) / (1024.0 * 1024.0)
    except (AttributeError, ValueError, OSError):
        pass

    return 4096.0  # Safe default fallback


def calculate_worker_budget(
    workload_count: int | None = None,
    lane_name: str = "tests",
    memory_per_worker_mb: float = DEFAULT_MEMORY_PER_WORKER_MB,
    user_override: int | None = None,
) -> int:
    """Calculate safe, adaptive pytest-xdist worker count.

    Rules:
    - User override (explicit argument or CI_WORKERS env var) is honored up to workload count.
    - Packaging lane is capped at 2 (direct-wheel vs sdist-wheel).
    - Small workloads (< 20 nodes) run sequentially (1 worker).
    - Moderate workloads (< 50 nodes) capped at min(2, available CPUs).
    - Memory budget caps worker count to prevent swapping.
    """
    if user_override is None:
        env_workers = os.environ.get("CI_WORKERS")
        if env_workers is not None:
            try:
                parsed = int(env_workers)
                if parsed > 0:
                    user_override = parsed
            except ValueError:
                pass

    if user_override is not None:
        w = max(1, int(user_override))
        if workload_count is not None and workload_count > 0:
            w = min(w, workload_count)
        return w

    cpus = available_cpu_count()

    if lane_name == "packaging":
        cap = 2
        if workload_count is not None and workload_count > 0:
            cap = min(cap, workload_count)
        return max(1, min(cap, cpus))

    mem_avail = available_memory_mb()
    mem_workers = max(1, int(mem_avail // memory_per_worker_mb))

    if workload_count is not None:
        if workload_count < 20:
            workload_cap = 1
        elif workload_count < 50:
            workload_cap = min(2, cpus)
        else:
            workload_cap = min(workload_count, cpus)
    else:
        workload_cap = cpus

    return max(1, min(cpus, mem_workers, workload_cap))


@contextlib.contextmanager
def scoped_host_cpu_reservation(
    requested_workers: int,
    lock_path: Path | None = None,
):
    """Advisory host-wide worker reservation to coordinate concurrent test lanes.

    Stores active worker counts in a lock file. If aggregate demand exceeds
    available host CPUs, scales down the granted worker count.
    """
    if lock_path is None:
        env_lock = os.environ.get("CI_RESOURCE_LOCK")
        if env_lock:
            lock_path = Path(env_lock)
        else:
            lock_path = (
                Path(tempfile.gettempdir()) / f"git-repo-db-{os.getuid()}-resource.lock"
            )
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    max_cpus = available_cpu_count()
    granted = max(1, min(requested_workers, max_cpus))

    with lock_path.open("a+b") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            raw = f.read().decode("utf-8").strip()
            data = {}
            if raw:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {}

            # Clean stale PID entries
            active = {}
            for pid_str, count in data.items():
                try:
                    pid = int(pid_str)
                    os.kill(pid, 0)
                    active[pid_str] = count
                except OSError as err:
                    if err.errno == errno.EPERM:
                        active[pid_str] = count
                except ValueError:
                    pass

            total_used = sum(active.values())
            remaining = max(1, max_cpus - total_used)
            granted = max(1, min(granted, remaining))

            active[str(os.getpid())] = granted
            f.seek(0)
            f.truncate()
            f.write(json.dumps(active).encode("utf-8") + b"\n")
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    try:
        yield granted
    finally:
        with lock_path.open("a+b") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.seek(0)
                raw = f.read().decode("utf-8").strip()
                data = {}
                if raw:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = {}
                data.pop(str(os.getpid()), None)
                f.seek(0)
                f.truncate()
                f.write(json.dumps(data).encode("utf-8") + b"\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
