from unittest.mock import patch

import pytest

from scripts import resource_scheduler


def test_available_cpu_count_defaults():
    cpus = resource_scheduler.available_cpu_count()
    assert cpus >= 1
    assert isinstance(cpus, int)


def test_calculate_worker_budget_override():
    assert (
        resource_scheduler.calculate_worker_budget(workload_count=100, user_override=2)
        == 2
    )
    assert (
        resource_scheduler.calculate_worker_budget(workload_count=10, user_override=8)
        == 8
    )


def test_calculate_worker_budget_packaging_cap():
    with patch.object(resource_scheduler, "available_cpu_count", return_value=8):
        assert (
            resource_scheduler.calculate_worker_budget(
                workload_count=10, lane_name="packaging"
            )
            == 2
        )
        assert (
            resource_scheduler.calculate_worker_budget(
                workload_count=1, lane_name="packaging"
            )
            == 1
        )


def test_calculate_worker_budget_small_workloads():
    with (
        patch.object(resource_scheduler, "available_cpu_count", return_value=8),
        patch.object(resource_scheduler, "available_memory_mb", return_value=16384.0),
    ):
        # Workloads under 20 run sequentially (1 worker)
        assert resource_scheduler.calculate_worker_budget(workload_count=5) == 1
        assert resource_scheduler.calculate_worker_budget(workload_count=19) == 1
        # Workloads 20-49 capped at min(2, cpus)
        assert resource_scheduler.calculate_worker_budget(workload_count=20) == 2
        assert resource_scheduler.calculate_worker_budget(workload_count=45) == 2
        # Workloads >= 50 scale to available CPUs
        assert resource_scheduler.calculate_worker_budget(workload_count=100) == 8


def test_calculate_worker_budget_memory_constraint():
    with (
        patch.object(resource_scheduler, "available_cpu_count", return_value=16),
        patch.object(resource_scheduler, "available_memory_mb", return_value=1000.0),
    ):
        # With 1000MB and 350MB per worker, max 2 workers
        assert (
            resource_scheduler.calculate_worker_budget(
                workload_count=200, memory_per_worker_mb=350.0
            )
            == 2
        )


def test_cgroup_quota_parsing_v2(tmp_path):
    cgroup_file = tmp_path / "cpu.max"
    cgroup_file.write_text("200000 100000\n")
    with patch(
        "scripts.resource_scheduler.Path",
        side_effect=lambda p: (
            cgroup_file if str(p) == "/sys/fs/cgroup/cpu.max" else tmp_path / "absent"
        ),
    ):
        quota = resource_scheduler.get_cgroup_cpu_quota()
        assert quota == 2.0


def test_cgroup_quota_parsing_v2_unconstrained(tmp_path):
    cgroup_file = tmp_path / "cpu.max"
    cgroup_file.write_text("max 100000\n")
    with patch(
        "scripts.resource_scheduler.Path",
        side_effect=lambda p: (
            cgroup_file if str(p) == "/sys/fs/cgroup/cpu.max" else tmp_path / "absent"
        ),
    ):
        quota = resource_scheduler.get_cgroup_cpu_quota()
        assert quota is None


def test_scoped_host_cpu_reservation(tmp_path):
    lock_path = tmp_path / "resource.lock"
    with patch.object(resource_scheduler, "available_cpu_count", return_value=4):
        with resource_scheduler.scoped_host_cpu_reservation(
            requested_workers=4, lock_path=lock_path
        ) as granted1:
            assert granted1 == 4
            # A concurrent reservation cannot exceed remaining capacity
            with resource_scheduler.scoped_host_cpu_reservation(
                requested_workers=2, lock_path=lock_path
            ) as granted2:
                # Remaining was 0, so scales to safe floor of 1
                assert granted2 == 1
        # After outer exit, lock entry is cleared
        with resource_scheduler.scoped_host_cpu_reservation(
            requested_workers=3, lock_path=lock_path
        ) as granted3:
            assert granted3 == 3


# Exercise the real /proc parser, not a mocked available_memory_mb result.


@pytest.mark.parametrize("available_first", [False, True])
def test_memavailable_precedes_total_independently_of_proc_order(
    tmp_path, available_first
):
    total = "MemTotal:       16777216 kB\n"
    available = "MemAvailable:    1048576 kB\n"
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(available + total if available_first else total + available)
    with (
        patch("scripts.resource_scheduler.Path", return_value=meminfo),
        patch.object(resource_scheduler, "available_cpu_count", return_value=8),
        patch.dict(resource_scheduler.os.environ, {}, clear=True),
    ):
        assert resource_scheduler.available_memory_mb() == 1024.0
        assert resource_scheduler.calculate_worker_budget(workload_count=200) == 2


@pytest.mark.parametrize(
    "bad", ["", "not-a-number kB", "nan kB", "inf kB", "-1 kB", "1024 MB"]
)
def test_malformed_memory_record_does_not_hide_later_available_value(tmp_path, bad):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(f"MemTotal: {bad}\nMemAvailable: 1048576 kB\n")
    with patch("scripts.resource_scheduler.Path", return_value=meminfo):
        assert resource_scheduler.available_memory_mb() == 1024.0


@pytest.mark.parametrize(
    "bad", [None, "", "garbage kB", "nan kB", "inf kB", "-1 kB", "1024 MB"]
)
def test_total_fallback_only_when_no_valid_available_record(tmp_path, bad):
    meminfo = tmp_path / "meminfo"
    text = "MemTotal: 16777216 kB\n"
    if bad is not None:
        text += f"MemAvailable: {bad}\n"
    meminfo.write_text(text)
    with patch("scripts.resource_scheduler.Path", return_value=meminfo):
        assert resource_scheduler.available_memory_mb() == 16384.0


@pytest.mark.parametrize(
    "available_kb,workers", [(0, 1), (32768, 1), (357376, 1), (716800, 2), (1048576, 2)]
)
def test_low_available_memory_keeps_worker_cap_despite_large_total(
    tmp_path, available_kb, workers
):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(f"MemTotal: 16777216 kB\nMemAvailable: {available_kb} kB\n")
    with (
        patch("scripts.resource_scheduler.Path", return_value=meminfo),
        patch.object(resource_scheduler, "available_cpu_count", return_value=8),
        patch.dict(resource_scheduler.os.environ, {}, clear=True),
    ):
        assert resource_scheduler.calculate_worker_budget(workload_count=200) == workers


def test_invalid_proc_values_fall_back_to_available_sysconf_pages(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: nan kB\nMemAvailable: invalid kB\n")
    with (
        patch("scripts.resource_scheduler.Path", return_value=meminfo),
        patch.object(
            resource_scheduler.os,
            "sysconf",
            side_effect=lambda key: {"SC_AVPHYS_PAGES": 262144, "SC_PAGE_SIZE": 4096}[
                key
            ],
        ),
    ):
        assert resource_scheduler.available_memory_mb() == 1024.0


@pytest.mark.parametrize(
    "prefix", ["", "MemTotal: 16777216 kB\nMemAvailable: malformed kB\n"]
)
def test_valid_available_record_survives_missing_total_or_prior_malformed_record(
    tmp_path, prefix
):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(prefix + "MemAvailable: 1048576 kB\n")
    with patch("scripts.resource_scheduler.Path", return_value=meminfo):
        assert resource_scheduler.available_memory_mb() == 1024.0


def test_memory_fix_preserves_cpu_cgroup_and_low_memory_minimum_caps(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 16777216 kB\nMemAvailable: 4194304 kB\n")
    with (
        patch("scripts.resource_scheduler.Path", return_value=meminfo),
        patch.object(resource_scheduler, "get_cpu_affinity", return_value=8),
        patch.object(resource_scheduler, "get_cgroup_cpu_quota", return_value=2.0),
        patch.object(resource_scheduler.os, "cpu_count", return_value=8),
        patch.dict(resource_scheduler.os.environ, {}, clear=True),
    ):
        assert resource_scheduler.calculate_worker_budget(workload_count=200) == 2
        meminfo.write_text("MemTotal: 16777216 kB\nMemAvailable: 262144 kB\n")
        assert resource_scheduler.calculate_worker_budget(workload_count=200) == 1


def test_absent_meminfo_uses_available_sysconf_pages(tmp_path):
    with (
        patch("scripts.resource_scheduler.Path", return_value=tmp_path / "absent"),
        patch.object(
            resource_scheduler.os,
            "sysconf",
            side_effect=lambda key: {"SC_AVPHYS_PAGES": 262144, "SC_PAGE_SIZE": 4096}[
                key
            ],
        ),
    ):
        assert resource_scheduler.available_memory_mb() == 1024.0
