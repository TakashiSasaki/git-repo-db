"""Content-bound cache identity and immutable publication regressions."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tests.support.distributions import build_once, package_build_inputs

ROOT = Path(__file__).resolve().parents[2]
SPECIMEN = (
    ROOT
    / "docs/implementation/evidence/adr0033-independent-review-20261023/archive/counterexamples/source"
)


def products(root):
    result = {}
    for name in ("wheel", "sdist_wheel", "sdist", "sdist_contract", "requirements"):
        path = root / name
        path.write_text(name)
        result[name] = path
    return result


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    shutil.copytree(SPECIMEN, root)
    (root / "uv.lock").write_text("lock-v1")
    return root


def test_content_identity_reuses_equal_trees_and_invalidates_working_edits(
    source, tmp_path
):
    env = {"SOURCE_DATE_EPOCH": "1"}

    def inputs():
        return package_build_inputs(source, env)

    cache = tmp_path / "cache"
    first = build_once(cache, products, inputs=inputs)
    clone = tmp_path / "clone"
    shutil.copytree(source, clone)
    assert package_build_inputs(clone, env) == inputs()
    assert (
        build_once(cache, lambda _: pytest.fail("must reuse"), inputs=inputs) == first
    )
    readme = source / "README.md"
    readme.write_text(readme.read_text() + "changed at same path")
    changed = build_once(cache, products, inputs=inputs)
    assert first != changed
    assert package_build_inputs(clone, env) != inputs()
    previous = inputs()
    (source / "uv.lock").write_text("lock-v2")
    assert inputs() != previous
    previous = inputs()
    (source / "pyproject.toml").write_text(
        (source / "pyproject.toml").read_text() + "\n# new build config\n"
    )
    assert inputs() != previous
    previous = inputs()
    (source / "src/repo_catalog/new.py").write_text("# untracked input")
    assert inputs() != previous
    assert package_build_inputs(source, {"SOURCE_DATE_EPOCH": "2"}) != inputs()


def test_wheelhouse_and_runner_are_build_inputs(source, tmp_path):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "manifest.json").write_text("{}")
    before = package_build_inputs(source, {}, wheels)
    (wheels / "dep.whl").write_bytes(b"dependency")
    assert package_build_inputs(source, {}, wheels) != before
    assert package_build_inputs(source, {}, wheels, products) != package_build_inputs(
        source, {}, wheels
    )


@pytest.mark.parametrize(
    "fault",
    [
        "absent-receipt",
        "corrupt-receipt",
        "wrong-input",
        "missing-artifact",
        "changed-artifact",
    ],
)
def test_missing_or_invalid_evidence_cannot_authorize_reuse(tmp_path, fault):
    fingerprint = "b" * 64

    def inputs():
        return fingerprint

    files = build_once(tmp_path, products, inputs=inputs)
    receipt = tmp_path / fingerprint / "ready.json"
    if fault == "absent-receipt":
        receipt.unlink()
    elif fault == "corrupt-receipt":
        receipt.write_text("{broken")
    elif fault == "wrong-input":
        data = json.loads(receipt.read_text())
        data["inputs"] = "c" * 64
        receipt.write_text(json.dumps(data))
    elif fault == "missing-artifact":
        files["wheel"].unlink()
    else:
        files["wheel"].write_text("tampered")

    def forbidden(_):
        raise RuntimeError("fresh validation required")

    with pytest.raises((ValueError, FileNotFoundError, RuntimeError)):
        build_once(tmp_path, forbidden, inputs=inputs)


def test_input_change_during_build_is_not_published(tmp_path):
    state = ["a" * 64]

    def mutate(root):
        files = products(root)
        state[0] = "b" * 64
        return files

    with pytest.raises(ValueError, match="changed during build"):
        build_once(tmp_path, mutate, inputs=lambda: state[0])
    assert not list(tmp_path.rglob("ready.json"))


@pytest.mark.parametrize("worker", range(8))
def test_xdist_workers_share_only_sealed_artifacts(tmp_path_factory, worker):
    base = tmp_path_factory.getbasetemp()
    while base.name.startswith("popen-gw"):
        base = base.parent
    cache = base / "identity-concurrency"

    def build(root):
        with (cache / "build-count").open("a") as counter:
            counter.write("build\n")
        return products(root)

    files = build_once(cache, build, inputs=lambda: "d" * 64)
    assert (cache / "build-count").read_text().splitlines() == ["build"]
    data = json.loads((cache / ("d" * 64) / "ready.json").read_text())
    for key, path in files.items():
        assert (
            data["files"][key]["sha256"]
            == hashlib.sha256(path.read_bytes()).hexdigest()
        )
