import json
from pathlib import Path
from unittest.mock import MagicMock

from scripts.ci_collector import CollectorPlugin, pytest_addoption, pytest_configure


class FakeMarker:
    def __init__(self, name):
        self.name = name


class FakeItem:
    def __init__(self, nodeid, path, markers=()):
        self.nodeid = nodeid
        self.path = Path(path)
        self._markers = [FakeMarker(m) for m in markers]

    def iter_markers(self):
        return iter(self._markers)


class FakeSession:
    def __init__(self, items):
        self.items = items


def test_collector_plugin_partitions_cohorts(tmp_path):
    items = [
        FakeItem("tests/unit/test_a.py::test_pass", "tests/unit/test_a.py", []),
        FakeItem("tests/unit/test_b.py::test_live", "tests/unit/test_b.py", ["live"]),
        FakeItem(
            "tests/unit/test_c.py::test_bench", "tests/unit/test_c.py", ["benchmark"]
        ),
        FakeItem(
            "tests/integration/access/test_acc.py::test_1",
            "tests/integration/access/test_acc.py",
            [],
        ),
    ]
    ci_targets = {"tests/unit/test_a.py", "tests/integration/access"}
    plugin = CollectorPlugin(tmp_path, ci_targets)
    session = FakeSession(items)

    plugin.pytest_collection_finish(session)

    result_file = tmp_path / "collected-cohorts.json"
    assert result_file.is_file()
    data = json.loads(result_file.read_text())

    assert len(data["all"]) == 4
    assert len(data["offline"]) == 3  # excludes test_live
    assert "tests/unit/test_b.py::test_live" not in data["offline"]
    assert len(data["ordinary"]) == 2  # excludes test_live and test_bench
    assert "tests/unit/test_c.py::test_bench" not in data["ordinary"]
    assert len(data["ci"]) == 2  # test_a and test_acc
    assert data["ci"] == [
        "tests/unit/test_a.py::test_pass",
        "tests/integration/access/test_acc.py::test_1",
    ]


def test_pytest_addoption_and_configure(tmp_path):
    parser = MagicMock()
    group = MagicMock()
    parser.getgroup.return_value = group
    pytest_addoption(parser)
    assert group.addoption.call_count == 2

    targets_file = tmp_path / "targets.txt"
    targets_file.write_text("tests/unit/test_a.py\n")

    config = MagicMock()
    config.getoption.side_effect = lambda opt: {
        "--collector-out": str(tmp_path),
        "--ci-targets-file": str(targets_file),
    }.get(opt)
    # Ensure config has no workerinput
    del config.workerinput

    pytest_configure(config)
    config.pluginmanager.register.assert_called_once()
