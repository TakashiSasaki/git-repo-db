"""Fail-closed Windows bootstrap checks without running a Windows executable."""

import copy
import io
import json
import os
import tarfile
from unittest.mock import patch

import pytest

from scripts import local_catalog_runtime as runtime


def manifest():
    return {
        "distribution": "astral-sh/python-build-standalone",
        "release": "20261021",
        "python": "3.12.15",
        "additional_platforms": {
            runtime.WINDOWS_TRIPLE: {
                "url": "https://example.invalid/python.tar.gz",
                "sha256": "1" * 64,
            }
        },
    }


def windows_host():
    return (
        patch.object(runtime.platform, "system", return_value="Windows"),
        patch.object(runtime.platform, "machine", return_value="AMD64"),
    )


def test_windows_selection_uses_reviewed_manifest_entry():
    system, machine = windows_host()
    with system, machine:
        selected = runtime.windows_distribution(manifest())
    assert selected["platform"] == runtime.WINDOWS_TRIPLE
    assert selected["sha256"] == "1" * 64
    assert selected["python"] == "3.12.15"


@pytest.mark.parametrize(
    "field,value", [("sha256", "bad"), ("url", "http://example.invalid/archive")]
)
def test_bad_windows_manifest_refuses_without_fallback(field, value):
    description = manifest()
    description["additional_platforms"][runtime.WINDOWS_TRIPLE][field] = value
    system, machine = windows_host()
    with system, machine, pytest.raises(ValueError):
        runtime.windows_distribution(description)


def test_non_windows_installation_refuses_before_creating_destination(tmp_path):
    description = tmp_path / "manifest.json"
    description.write_text(json.dumps(manifest()))
    with (
        patch.object(runtime.runtime, "MANIFEST", description),
        patch.object(runtime.platform, "system", return_value="Linux"),
        pytest.raises(runtime.runtime.UnsupportedPlatform),
    ):
        runtime.install(tmp_path / "destination", tmp_path / "receipt.json")
    assert not (tmp_path / "destination").exists()


def archive(tmp_path, names):
    path = tmp_path / "input.tar.gz"
    with tarfile.open(path, "w:gz") as output:
        for name in names:
            member = tarfile.TarInfo(name)
            member.size = 1
            output.addfile(member, io.BytesIO(b"x"))
    return path


@pytest.mark.parametrize(
    "names",
    [
        ["python/file:stream"],
        ["python/wildcard?"],
        ["python/control\x01"],
        ["python/NUL"],
        ["python/con.txt"],
        ["python/trailing."],
        ["python/trailing "],
        ["python/File", "python/file"],
        ["python/../../outside"],
    ],
)
def test_windows_archive_refuses_native_path_aliases(tmp_path, names):
    with pytest.raises(ValueError):
        runtime.check_windows_archive(archive(tmp_path, names))


def test_windows_archive_accepts_regular_distribution_paths(tmp_path):
    runtime.check_windows_archive(
        archive(tmp_path, ["python/python.exe", "python/DLLs/_sqlite3.pyd"])
    )


def test_windows_extract_works_without_posix_nofollow(tmp_path, monkeypatch):
    source = archive(tmp_path, ["python/python.exe", "python/DLLs/_sqlite3.pyd"])
    destination = tmp_path / "fresh"
    destination.mkdir(mode=0o700)
    monkeypatch.delattr(runtime.os, "O_NOFOLLOW", raising=False)
    with patch.object(
        runtime.runtime,
        "safe_extract",
        side_effect=AssertionError("POSIX extractor used"),
    ):
        runtime.extract_windows(source, destination)
    assert (destination / "python/python.exe").read_bytes() == b"x"
    assert (destination / "python/DLLs/_sqlite3.pyd").read_bytes() == b"x"


def test_windows_extract_requires_empty_destination(tmp_path):
    source = archive(tmp_path, ["python/python.exe"])
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "preserved").write_bytes(b"existing data")
    with pytest.raises(ValueError, match="empty private destination"):
        runtime.extract_windows(source, destination)
    assert (destination / "preserved").read_bytes() == b"existing data"
    assert not (destination / "python").exists()


@pytest.mark.skipif(
    os.name != "posix", reason="symlink creation needs no Windows privilege"
)
def test_windows_extract_refuses_link_destination(tmp_path):
    source = archive(tmp_path, ["python/python.exe"])
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "linked"
    destination.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="link or reparse"):
        runtime.extract_windows(source, destination)
    assert list(outside.iterdir()) == []


def test_windows_extract_refuses_archive_links_before_writes(tmp_path):
    source = tmp_path / "linked.tar.gz"
    with tarfile.open(source, "w:gz") as output:
        ordinary = tarfile.TarInfo("python/python.exe")
        ordinary.size = 1
        output.addfile(ordinary, io.BytesIO(b"x"))
        linked = tarfile.TarInfo("python/DLLs")
        linked.type = tarfile.SYMTYPE
        linked.linkname = "../outside"
        output.addfile(linked)
    destination = tmp_path / "fresh"
    destination.mkdir()
    with pytest.raises(ValueError, match="archive links"):
        runtime.extract_windows(source, destination)
    assert list(destination.iterdir()) == []


def test_changed_runtime_reference_refuses_even_when_python_version_matches():
    measured = {
        key: "unchanged"
        for key in (
            "python",
            "base_executable",
            "base_executable_sha256",
            "sqlite_version",
            "sqlite_source_id",
            "sqlite_threadsafety",
            "sqlite_module",
            "sqlite_module_sha256",
            "compile_options",
            "sqlite_mappings",
        )
    }
    original = {"status": "passed", "runtime": copy.deepcopy(measured)}
    measured["sqlite_source_id"] = "changed"
    with pytest.raises(RuntimeError, match="sqlite_source_id"):
        runtime.check_reference(measured, original)


def test_failed_probe_does_not_print_success_and_retains_failure(tmp_path, capsys):
    installation = tmp_path / "install.json"
    installation.write_text("{}")
    output = tmp_path / "probe.json"
    with (
        patch.object(runtime, "identity", return_value={}),
        patch.object(
            runtime, "check_selected", side_effect=RuntimeError("broken distribution")
        ),
        pytest.raises(RuntimeError, match="broken distribution"),
    ):
        runtime.probe(installation, output)
    result = json.loads(output.read_text())
    assert result["status"] == "failed"
    assert "broken distribution" in result["error"]
    assert "passed" not in capsys.readouterr().out


def test_installation_digest_failure_retains_failure_without_extracting(
    tmp_path, capsys
):
    destination = tmp_path / "python-install"
    receipt = tmp_path / "receipt.json"
    with (
        patch.object(runtime, "windows_distribution", return_value={}),
        patch.object(
            runtime.runtime,
            "download_verified",
            side_effect=ValueError("digest mismatch"),
        ),
        patch.object(runtime, "extract_windows") as extract,
        pytest.raises(ValueError, match="digest mismatch"),
    ):
        runtime.install(destination, receipt)
    extract.assert_not_called()
    assert list(destination.iterdir()) == []
    assert json.loads(receipt.read_text())["status"] == "failed"
    assert "installed" not in capsys.readouterr().out


@pytest.mark.parametrize("change", ["tree", "library", "base"])
def test_probe_refuses_changed_or_external_runtime(tmp_path, change):
    distribution = tmp_path / "python"
    distribution.mkdir()
    executable = distribution / "python.exe"
    executable.write_bytes(b"complete-interpreter")
    module = distribution / "_sqlite3.pyd"
    module.write_bytes(b"extension")
    selection = {"python": "3.12.15"}
    installed = {
        "schema": runtime.SCHEMA,
        "status": "installed",
        "selection": selection,
        "directory": str(distribution),
        "executable": str(executable),
        "executable_sha256": runtime.runtime.sha256_file(executable),
        "tree": runtime.runtime.tree_digest(distribution),
    }
    measured = {
        "base_executable": str(executable),
        "base_executable_sha256": installed["executable_sha256"],
        "python": "3.12.15",
        "sqlite_module": str(module),
        "sqlite_mappings": {},
    }
    if change == "tree":
        module.write_bytes(b"replaced-extension")
    elif change == "library":
        measured["sqlite_mappings"] = {str(tmp_path / "external.dll"): "digest"}
    else:
        measured["base_executable"] = str(tmp_path / "unselected.exe")
    with (
        patch.object(runtime, "windows_distribution", return_value=selection),
        pytest.raises(RuntimeError),
    ):
        runtime.check_selected(measured, installed)
