"""Pytest plugin for single-pass multi-cohort test collection."""

from __future__ import annotations

import json
import os
from pathlib import Path


class CollectorPlugin:
    def __init__(self, out_dir: Path, ci_targets: set[str]):
        self.out_dir = out_dir
        self.ci_targets = ci_targets

    def pytest_collection_finish(self, session):
        all_nodes = []
        offline_nodes = []
        ordinary_nodes = []
        ci_nodes = []

        root = Path.cwd()
        for item in session.items:
            nodeid = item.nodeid
            all_nodes.append(nodeid)

            markers = {m.name for m in item.iter_markers()}
            is_live = "live" in markers
            is_benchmark = "benchmark" in markers

            if not is_live:
                offline_nodes.append(nodeid)
                if not is_benchmark:
                    ordinary_nodes.append(nodeid)
                    rel = str(Path(item.path).resolve().relative_to(root))
                    if any(
                        rel == t or rel.startswith(t.rstrip("/") + "/")
                        for t in self.ci_targets
                    ):
                        ci_nodes.append(nodeid)

        if self.out_dir:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            result = {
                "all": all_nodes,
                "offline": offline_nodes,
                "ordinary": ordinary_nodes,
                "ci": ci_nodes,
            }
            (self.out_dir / "collected-cohorts.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )


def pytest_addoption(parser):
    group = parser.getgroup("ci_collector", "CI Multi-cohort test collector")
    group.addoption(
        "--collector-out",
        action="store",
        default=os.environ.get("CI_COLLECTOR_OUT"),
        help="Directory to output collected cohorts JSON",
    )
    group.addoption(
        "--ci-targets-file",
        action="store",
        default=os.environ.get("CI_TARGETS_FILE"),
        help="File containing newline-delimited CI targets",
    )


def pytest_configure(config):
    out_dir_str = config.getoption("--collector-out")
    if out_dir_str and not hasattr(config, "workerinput"):
        ci_targets_file = config.getoption("--ci-targets-file")
        ci_targets = set()
        if ci_targets_file and Path(ci_targets_file).is_file():
            ci_targets = {
                line.strip()
                for line in Path(ci_targets_file).read_text().splitlines()
                if line.strip()
            }
        plugin = CollectorPlugin(Path(out_dir_str), ci_targets)
        config.pluginmanager.register(plugin, name="ci_collector_plugin")
