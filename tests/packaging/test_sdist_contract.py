"""Adversarial archive checks and real independent distribution builds for ADR 0033."""

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import check_sdist_contract as contract

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    package = root / "src/repo_catalog"
    package.mkdir(parents=True)
    for name, raw in {
        "__init__.py": b"",
        "schema.sql": b"SELECT 1;",
        "contract.json": b"{}",
        "query.graphql": b"query { viewer { login } }",
    }.items():
        (package / name).write_bytes(raw)
    (root / "pyproject.toml").write_text(
        '[project]\nname="repo-catalog"\nversion="0.2.0"\n'
    )
    (root / "README.md").write_text("# Fixture\n")
    (root / ".gitignore").write_text("__pycache__/\n")
    return root


def archive(source, path, *, omit=(), extra=(), changed=None):
    members = {n: (source / n).read_bytes() for n in contract.source_inventory(source)}
    members["PKG-INFO"] = (
        b"Metadata-Version: 2.4\nName: repo-catalog\nVersion: 0.2.0\n\n"
    )
    members.update(changed or {})
    with tarfile.open(path, "w:gz") as tar:
        for name, raw in members.items():
            if name in omit:
                continue
            info = tarfile.TarInfo("repo_catalog-0.2.0/" + name)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
        for name, kind in extra:
            info = tarfile.TarInfo(name)
            info.type = kind
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                info.linkname = "../../outside"
            tar.addfile(info, io.BytesIO())
    return path


def test_complete_source_hashes_and_metadata(source, tmp_path):
    result = contract.check_sdist(archive(source, tmp_path / "source.tar.gz"), source)
    assert result["status"] == "passed"
    assert result["product_files"] == 4
    assert result["file_count"] == 8
    assert (
        result["source_files"]["src/repo_catalog/schema.sql"]["sha256"]
        == hashlib.sha256(b"SELECT 1;").hexdigest()
    )
    assert result["compressed_bytes"] > 0 and result["unpacked_bytes"] > 0


@pytest.mark.parametrize(
    "name",
    [
        "repo_catalog-0.2.0/docs/evidence.zip",
        "repo_catalog-0.2.0/tests/test_x.py",
        "repo_catalog-0.2.0/scripts/check.py",
        "repo_catalog-0.2.0/unclassified.bin",
        "repo_catalog-0.2.0/src/repo_catalog/evidence.zip",
        "repo_catalog-0.2.0/../escape",
        "/absolute",
        "other-0.2.0/README.md",
        "repo_catalog-0.2.0/./README.md",
        "repo_catalog-0.2.0//README.md",
        "repo_catalog-0.2.0/C:/escape",
        "repo_catalog-0.2.0\\escape",
        "repo_catalog-0.2.0/README.md",
    ],
)
def test_unexpected_unsafe_or_duplicate_members_fail(source, tmp_path, name):
    path = archive(source, tmp_path / "bad.tar.gz", extra=[(name, tarfile.REGTYPE)])
    with pytest.raises(ValueError):
        contract.check_sdist(path, source)


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]
)
def test_links_and_special_files_are_rejected(source, tmp_path, kind):
    path = archive(
        source, tmp_path / "link.tar.gz", extra=[("repo_catalog-0.2.0/link", kind)]
    )
    with pytest.raises(ValueError, match="links/special"):
        contract.check_sdist(path, source)


@pytest.mark.parametrize(
    "missing",
    [
        "PKG-INFO",
        "README.md",
        "pyproject.toml",
        ".gitignore",
        "src/repo_catalog/schema.sql",
        "src/repo_catalog/contract.json",
        "src/repo_catalog/query.graphql",
    ],
)
def test_missing_required_inputs_fail(source, tmp_path, missing):
    with pytest.raises(ValueError, match="missing"):
        contract.check_sdist(
            archive(source, tmp_path / "missing.tar.gz", omit=[missing]), source
        )


def test_changed_product_hash_and_metadata_fail(source, tmp_path):
    for name, value in [
        ("src/repo_catalog/schema.sql", b"SELECT 2;"),
        ("PKG-INFO", b"Name: other\nVersion: 0.2.0\n"),
    ]:
        with pytest.raises(ValueError):
            contract.check_sdist(
                archive(source, tmp_path / "changed.tar.gz", changed={name: value}),
                source,
            )


@pytest.mark.parametrize("budget", ["MAX_COMPRESSED", "MAX_UNPACKED", "MAX_MEMBERS"])
def test_finite_budgets_fail_closed(source, tmp_path, monkeypatch, budget):
    path = archive(source, tmp_path / "large.tar.gz")
    monkeypatch.setattr(contract, budget, 1)
    with pytest.raises(ValueError, match="budget exceeded"):
        contract.check_sdist(path, source)


def test_cli_failure_is_nonzero_and_preserves_failed_receipt(source, tmp_path):
    path = archive(source, tmp_path / "bad.tar.gz", omit=["PKG-INFO"])
    output = tmp_path / "result.json"
    result = subprocess.run(
        [
            sys.executable,
            ROOT / "scripts/check_sdist_contract.py",
            "--source-root",
            source,
            "--sdist",
            path,
            "--output",
            output,
        ],
        capture_output=True,
    )
    assert result.returncode == 1
    assert json.loads(output.read_text())["status"] == "failed"


def test_source_links_and_unclassified_package_inputs_fail(source):
    path = source / "src/repo_catalog/evidence.zip"
    path.write_bytes(b"not product data")
    with pytest.raises(ValueError, match="unclassified"):
        contract.source_inventory(source)
    path.unlink()
    path.symlink_to(source / "README.md")
    with pytest.raises(ValueError, match="linked"):
        contract.source_inventory(source)


@pytest.fixture(scope="module")
def real_build(tmp_path_factory):
    work = tmp_path_factory.mktemp("sdist-contract-build")
    source = work / "source"
    source.mkdir()
    shutil.copytree(
        ROOT / "src",
        source / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in contract.ROOT_FILES:
        shutil.copyfile(ROOT / name, source / name)
    direct, derived = work / "direct", work / "derived"
    env = dict(os.environ, UV_PYTHON_DOWNLOADS="never", SOURCE_DATE_EPOCH="1700000000")

    def build(root, out, *targets):
        command = [sys.executable, "-m", "hatchling", "build", "-d", str(out)]
        for target in targets:
            command += ["-t", target]
        subprocess.run(command, cwd=root, env=env, check=True, capture_output=True)

    build(source, direct, "wheel", "sdist")
    sdist = next(direct.glob("*.tar.gz"))
    report = contract.check_sdist(sdist, source)
    unpack = work / "unpack"
    with tarfile.open(sdist) as tar:
        tar.extractall(unpack, filter="data")
    isolated = next(unpack.iterdir())
    assert not (isolated / ".git").exists()
    assert not any(
        (isolated / p).exists() for p in ("docs", "tests", "scripts", "uv.lock")
    )
    build(isolated, derived, "wheel")
    return (
        source,
        report,
        sdist,
        next(direct.glob("*.whl")),
        next(derived.glob("*.whl")),
        build,
    )


def test_real_sdist_independent_wheel_has_complete_equal_content(real_build):
    _, report, _, direct, derived, _ = real_build
    equivalent = contract.compare_wheels(
        direct, derived, sdist_metadata=report["members"]["PKG-INFO"]["sha256"]
    )
    assert equivalent["product_files"] == report["product_files"]
    assert equivalent["metadata_files"] > 0
    assert all(
        any(n.endswith(ext) for n in equivalent["members"])
        for ext in (".sql", ".json", ".graphql")
    )


def test_new_evidence_and_unclassified_files_do_not_enter_sdist(real_build, tmp_path):
    source, before, old, _, _, build = real_build
    for name in (
        "docs/implementation/evidence/new.zip",
        "tests/new.txt",
        "scripts/new.py",
        "unclassified.bin",
    ):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(os.urandom(65536))
    build(source, tmp_path, "sdist")
    new = next(tmp_path.glob("*.tar.gz"))
    after = contract.check_sdist(new, source)
    assert before["members"] == after["members"]
    assert old.read_bytes() == new.read_bytes()


def rewrite_wheel(original, output, changed, fix_record=True):
    files = contract.wheel_contents(original)
    files.update(changed)
    record = next(n for n in files if n.endswith(".dist-info/RECORD"))
    if fix_record:
        import base64

        stream = io.StringIO()
        writer = csv.writer(stream, lineterminator="\n")
        for n, raw in sorted(files.items()):
            writer.writerow(
                [n, "", ""]
                if n == record
                else [
                    n,
                    "sha256="
                    + base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
                    .rstrip(b"=")
                    .decode(),
                    len(raw),
                ]
            )
        files[record] = stream.getvalue().encode()
    with zipfile.ZipFile(output, "w") as wheel:
        for n, raw in files.items():
            wheel.writestr(n, raw)
    return output


@pytest.mark.parametrize("metadata", [False, True])
def test_valid_record_does_not_hide_wheel_content_or_metadata_changes(
    real_build, tmp_path, metadata
):
    _, _, _, direct, _, _ = real_build
    name = (
        "repo_catalog/__main__.py"
        if not metadata
        else next(
            n
            for n in contract.wheel_contents(direct)
            if n.endswith(".dist-info/METADATA")
        )
    )
    changed = rewrite_wheel(direct, tmp_path / "changed.whl", {name: b"changed"})
    with pytest.raises(ValueError, match="content/metadata mismatch"):
        contract.compare_wheels(direct, changed)


def test_wheel_record_tampering_is_rejected(real_build, tmp_path):
    _, _, _, direct, _, _ = real_build
    changed = rewrite_wheel(
        direct,
        tmp_path / "changed.whl",
        {"repo_catalog/__main__.py": b"changed"},
        fix_record=False,
    )
    with pytest.raises(ValueError, match="RECORD hash"):
        contract.compare_wheels(direct, changed)


def test_sdist_metadata_must_match_the_wheel(real_build):
    _, _, _, direct, derived, _ = real_build
    with pytest.raises(ValueError, match="PKG-INFO differs"):
        contract.compare_wheels(direct, derived, sdist_metadata="0" * 64)
