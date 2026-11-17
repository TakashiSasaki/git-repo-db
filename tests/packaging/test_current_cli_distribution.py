"""Ordinary separated CLI from root wheels, outside the source checkout."""

import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.packaging.test_p1_distribution import p1_distributions, run

__all__ = ["p1_distributions"]


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
def test_installed_current_cli_metadata_reparse_backup_without_file_archive(
    p1_distributions, tmp_path, variant
):
    env, wheels = p1_distributions
    for archive in wheels[variant]:
        with ZipFile(archive) as wheel:
            names = set(wheel.namelist())
        assert not names.intersection(
            {
                "repo_catalog/adapters/sqlite/store.py",
                "repo_catalog/adapters/sqlite/schema.py",
                "repo_catalog/config.py",
            }
        )
        assert not any(
            name.startswith("repo_catalog/resources/")
            and name.endswith((".sql", ".graphql", "cli-v1.schema.json"))
            for name in names
        )
    outside = tmp_path / "outside"
    outside.mkdir()
    venv = tmp_path / "venv"
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    wheelhouse = env.get("REPO_CATALOG_WHEELHOUSE")
    assert wheelhouse and (Path(wheelhouse) / "manifest.json").is_file(), (
        "Prepare locked wheels with scripts/prepare_wheelhouse.py"
    )
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--no-index",
            "--find-links",
            wheelhouse,
            *wheels[variant],
        ],
        outside,
        env,
    )
    script = r"""
import base64
import dataclasses
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
import repo_catalog
from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.domain.git_acquisition import GitMetadataInput
from repo_catalog.domain.p1_core import OID, NativeObject, native_object_oid

assert all("site-packages" in part for part in repo_catalog.__path__)
assert "site-packages" in p1_schema.__file__
cli_path = Path(sys.executable).parent / "repo-catalog"

def cli(*args, code=0):
    result = subprocess.run([str(cli_path), *map(str, args)], capture_output=True, text=True)
    assert result.returncode == code, (args, result.stdout, result.stderr)
    return json.loads(result.stdout if code == 0 else result.stderr)

def wire(value):
    if dataclasses.is_dataclass(value):
        return {"$type": type(value).__name__, "fields": {
            field.name: wire(getattr(value, field.name)) for field in dataclasses.fields(value)
            if field.init and not field.name.startswith("_")}}
    if isinstance(value, bytes):
        return {"$bytes": base64.b64encode(value).decode()}
    if isinstance(value, (tuple, list, frozenset)):
        return [wire(item) for item in value]
    if isinstance(value, dict):
        return {key: wire(item) for key, item in value.items()}
    return value

def document(name, value):
    path = Path(name)
    path.write_text(json.dumps(wire(value)))
    return path

catalog = Path("catalog")
identity = cli("init", "--scope", "core", "--catalog", catalog)
cli("init", "--scope", "operational", "--catalog", catalog)
assert sorted(path.name for path in catalog.glob("*.sqlite3")) == ["core.sqlite3", "operational.sqlite3"]
assert "parser" not in subprocess.check_output([str(cli_path), "--help"], text=True)
fmt = "sha1"
body = b"100644 raw\xff\0" + bytes.fromhex("1" * 40)
tree = OID(fmt, native_object_oid(fmt, "tree", body))
unit = GitMetadataInput(
    identity["repository_uuidv4"], str(uuid4()), str(uuid4()),
    "installed metadata input", 100,
    native_objects=(NativeObject(tree, "tree", body, len(body), hashlib.sha256(body).hexdigest()),),
)
source = document("metadata.json", unit)
assert cli("acquire", "git-metadata", "--catalog", catalog, "--input", source, "--new-request")["retained_objects"]
before = cli("query", "tree", "--catalog", catalog, "--object-oid", tree.object_oid)
assert before["items"][0]["path"] == {"$bytes": base64.b64encode(b"raw\xff").decode()}
reparse = document("reparse.json", {"unit": dataclasses.replace(unit, native_objects=()), "objects": [tree]})
cli("reparse", "--catalog", catalog, "--input", reparse,
    "--request-origin", str(uuid4()), "--request", str(uuid4()), "--new-request")
after = cli("query", "tree", "--catalog", catalog, "--object-oid", tree.object_oid)
structural = lambda item: {key: item[key] for key in ("path", "mode", "object_format", "object_oid", "qualification")}
assert [structural(item) for item in after["items"]] == [structural(item) for item in before["items"]]
assert after["items"][0]["decoded_name_candidates"]
cli("doctor", "--scope", "git_only", "--verify-retained", "--catalog", catalog)
backup = Path("backup")
cli("recovery", "backup", "--scope", "git_only", "--catalog", catalog, "--output", backup)
restored = Path("restored")
cli("recovery", "restore", "--scope", "git_only", "--catalog", restored,
    "--input", backup, "--repository", identity["repository_uuidv4"])
assert cli("query", "tree", "--catalog", restored, "--object-oid", tree.object_oid)["items"] == after["items"]
assert sorted(path.name for path in restored.glob("*.sqlite3")) == ["core.sqlite3"]
assert not (catalog / "context.sqlite3").exists()
assert not (catalog / "search.sqlite3").exists()
assert not (catalog / "transport-archive").exists()
p1_schema.verify_declared()
"""
    run([python, "-c", script], outside, env)
