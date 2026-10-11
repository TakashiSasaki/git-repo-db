import json
import subprocess
from importlib.resources import files

import jsonschema


def cli(*args):
    p = subprocess.run(
        ["repo-catalog", "--format", "json", *map(str, args)],
        capture_output=True,
        text=True,
    )
    value = json.loads(p.stdout)
    jsonschema.validate(
        value,
        json.loads(
            files("repo_catalog")
            .joinpath("resources/schemas/cli-v1.schema.json")
            .read_text()
        ),
    )
    return p.returncode, value


def test_readonly_missing_database(tmp_path):
    state = tmp_path / "missing"
    for timeout in ("nan", "inf"):
        code, data = cli("--state-dir", state, "--timeout-seconds", timeout, "doctor")
        assert code == 2 and data["error"]["code"] == "INVALID_ARGUMENT"
        assert not state.exists()
    code, data = cli("--state-dir", state, "doctor")
    assert code == 0 and data["data"]["initialized"] is False
    assert not state.exists()
    code, data = cli(
        "init",
        "--profile",
        "not-implemented",
        "--cache-max-bytes",
        1024,
        "--min-free-bytes",
        0,
        "--all",
    )
    assert code == 2 and data["error"]["code"] == "INVALID_ARGUMENT"


def test_init_and_config(tmp_path):
    state = tmp_path / "state"
    code, data = cli(
        "--state-dir",
        state,
        "init",
        "--profile",
        "catalog-text-v1",
        "--cache-max-bytes",
        33554432,
        "--min-free-bytes",
        0,
    )
    assert code == 0 and data["catalog"]["local_revision"] == 0
    code, data = cli("--state-dir", state, "doctor")
    assert code == 0 and data["data"]["initialized"] is True
    code, data = cli(
        "--state-dir",
        state,
        "sources",
        "add",
        "local-git",
        "--name",
        "fixture",
        "--url",
        "file:///tmp/example.git",
    )
    assert code == 0 and data["data"]["source_id"]
