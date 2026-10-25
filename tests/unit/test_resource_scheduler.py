from unittest.mock import patch

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
