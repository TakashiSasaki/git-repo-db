"""Keep opt-in smoke orchestration compatible without acquiring a real source."""

import json
from types import SimpleNamespace

from tests.live import test_smoke as live_smoke


def test_live_smoke_uses_discovered_repository_identity(tmp_path, monkeypatch):
    repository = "00000000-0000-4000-8000-000000000901"
    state = tmp_path / "state"
    monkeypatch.setenv("REPO_CATALOG_LIVE_REPOSITORY", "fixture/alpha")
    monkeypatch.setenv("REPO_CATALOG_LIVE_STATE_DIR", str(state))
    commands = []

    def cli(command, **kwargs):
        assert command[:5] == [
            "repo-catalog",
            "--state-dir",
            str(state),
            "--format",
            "json",
        ]
        args = command[5:]
        commands.append(args)
        if args[:2] == ["sources", "add"]:
            data = {"source_id": "fixture-source"}
        elif args[:1] == ["discover"]:
            data = {"repositories": [{"repository_uuidv4": repository}]}
        else:
            data = {}
        return SimpleNamespace(returncode=0, stdout=json.dumps({"data": data}))

    monkeypatch.setattr(live_smoke.subprocess, "run", cli)
    live_smoke.test_selected_repository(tmp_path)

    assert commands[2:] == [
        ["discover", "--source", "fixture-source"],
        ["sync", "all", "--repo", repository],
        ["refs", "list", "--repo", repository],
        ["pr", "list", "--repo", repository],
        ["db", "check", "--full"],
    ]
    evidence = json.loads((tmp_path / "live-evidence.json").read_text())
    assert evidence["target"] == "fixture/alpha"
    assert len(evidence["results"]) == len(commands) == 7
