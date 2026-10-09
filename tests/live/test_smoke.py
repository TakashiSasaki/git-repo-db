import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.live
def test_selected_repository(tmp_path):
    target = os.environ.get("REPO_CATALOG_LIVE_REPOSITORY")
    if not target:
        pytest.fail(
            "Live smoke requires an explicitly selected REPO_CATALOG_LIVE_REPOSITORY"
        )
    owner, name = target.split("/", 1)
    state = Path(os.environ.get("REPO_CATALOG_LIVE_STATE_DIR", str(tmp_path / "state")))
    if state.exists():
        pytest.fail("Live smoke state must be new")

    def cli(*args):
        p = subprocess.run(
            [
                "repo-catalog",
                "--state-dir",
                str(state),
                "--format",
                "json",
                *map(str, args),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        data = json.loads(p.stdout)
        assert p.returncode == 0, (p.returncode, data)
        return data

    results = []
    results.append(
        cli(
            "init",
            "--profile",
            "catalog-text-v1",
            "--cache-max-bytes",
            33554432,
            "--min-free-bytes",
            0,
        )
    )
    source = cli("sources", "add", "github", "--owner", owner, "--include-repo", name)
    results.append(source)
    discovery = cli("discover", "--source", source["data"]["source_id"])
    results.append(discovery)
    assert len(discovery["data"]["repositories"]) == 1
    repo = discovery["data"]["repositories"][0]["repository_uuidv4"]
    results.append(cli("sync", "all", "--repo", repo))
    results.append(cli("refs", "list", "--repo", repo))
    results.append(cli("pr", "list", "--repo", repo))
    results.append(cli("db", "check", "--full"))
    (state.parent / "live-evidence.json").write_text(
        json.dumps(
            {"target": target, "scope": "single-repository-smoke", "results": results},
            ensure_ascii=True,
            indent=2,
        )
    )
