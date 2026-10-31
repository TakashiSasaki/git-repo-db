"""Content-bound cache identity and immutable publication regressions."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support.distributions import (
    build_cache_key,
    build_once,
    package_build_environment,
    package_build_inputs,
)

ROOT = Path(__file__).resolve().parents[2]
SPECIMEN = (
    ROOT
    / "docs/implementation/evidence/adr0033-independent-review-20261023/archive/counterexamples/source"
)


@pytest.mark.parametrize("explicit", [False, True])
def test_distribution_build_uses_the_dependency_setup_uv_cache(
    tmp_path, monkeypatch, explicit
):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "default-cache"))
    if explicit:
        monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "explicit cache"))
    else:
        monkeypatch.delenv("UV_CACHE_DIR", raising=False)

    def cache_directory(env):
        return subprocess.check_output(
            ["uv", "cache", "dir"], env=env, text=True
        ).strip()

    setup_cache = cache_directory(dict(os.environ))
    build_env = package_build_environment()
    assert cache_directory(build_env) == setup_cache
    assert build_env["UV_PYTHON"]


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
    receipt = tmp_path / build_cache_key(tmp_path, fingerprint) / "ready.json"
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
    data = json.loads(
        (cache / build_cache_key(cache, "d" * 64) / "ready.json").read_text()
    )
    for key, path in files.items():
        assert (
            data["files"][key]["sha256"]
            == hashlib.sha256(path.read_bytes()).hexdigest()
        )


@pytest.mark.parametrize(
    "name,content",
    [
        (".hgignore", "syntax: glob\nsrc/repo_catalog/__init__.py\n"),
        ("hatch.toml", "[build]\nignore-vcs = true\n"),
        ("hatch_build.py", "# backend default build script\n"),
        ("uv.toml", "offline = true\n"),
    ],
)
def test_backend_controls_cannot_hide_behind_previous_success(
    source, tmp_path, name, content
):
    def inputs():
        return package_build_inputs(source, {})

    cache = tmp_path / "cache"
    before = inputs()
    build_once(cache, products, inputs=inputs)
    control = source / name
    control.write_text(content)
    calls = []

    def rejecting_build(_):
        calls.append("fresh backend validation")
        raise ValueError("new backend input rejected")

    with pytest.raises(ValueError, match="new backend input rejected"):
        build_once(cache, rejecting_build, inputs=inputs)
    assert calls == ["fresh backend validation"]
    assert inputs() != before
    changed = inputs()
    control.write_text(content + "\n# changed at same path\n")
    assert inputs() != changed
    control.unlink()
    assert inputs() == before
    assert build_once(
        cache,
        lambda _: pytest.fail("unchanged original inputs should reuse"),
        inputs=inputs,
    )


def test_inherited_controls_and_explicit_uv_configuration_are_content_inputs(
    source, tmp_path
):
    from tests.support.distributions import backend_control_inputs

    initial = backend_control_inputs(source, {})
    inherited = source.parent / ".hgignore"
    inherited.write_text("syntax: glob\n*.py\n")
    inherited_key = backend_control_inputs(source, {})
    assert inherited_key != initial
    inherited.write_text("syntax: glob\n*.sql\n")
    assert backend_control_inputs(source, {}) != inherited_key
    (source / ".hg").mkdir()
    assert backend_control_inputs(source, {}) == initial

    config = tmp_path / "external-uv.toml"
    env = {"UV_CONFIG_FILE": str(config), "XDG_CONFIG_HOME": str(tmp_path / "user")}
    absent = backend_control_inputs(source, env)
    config.write_text("offline = true\n")
    present = backend_control_inputs(source, env)
    assert present != absent
    config.write_text("offline = false\n")
    assert backend_control_inputs(source, env) != present
    user_config = tmp_path / "user/uv/uv.toml"
    user_config.parent.mkdir(parents=True)
    before = backend_control_inputs(source, env)
    user_config.write_text("offline = true\n")
    assert backend_control_inputs(source, env) != before


def test_unknown_root_control_files_and_links_fail_closed(source, tmp_path):
    from tests.support.distributions import backend_control_inputs

    before = backend_control_inputs(source, {})
    control = source / ".future-backend-control"
    control.write_text("a control not in a filename allowlist")
    assert backend_control_inputs(source, {}) != before
    control.unlink()
    control.symlink_to(tmp_path / "missing-control")
    with pytest.raises(ValueError, match="Linked backend"):
        backend_control_inputs(source, {})


def test_xdg_system_config_addition_is_not_hidden_by_a_warm_cache(source, tmp_path):
    system = tmp_path / "system"
    system.mkdir()
    env = {"XDG_CONFIG_DIRS": str(system)}

    def inputs():
        return package_build_inputs(source, env)

    cache = tmp_path / "cache"
    before = inputs()
    build_once(cache, products, inputs=inputs)
    config = system / "uv/uv.toml"
    config.parent.mkdir()
    config.write_text("not valid TOML\n")

    def reject(_):
        raise ValueError("fresh uv rejected system config")

    with pytest.raises(ValueError, match="fresh uv rejected"):
        build_once(cache, reject, inputs=inputs)
    assert inputs() != before


def test_documentation_bytes_reuse_product_cache_but_root_edits_invalidate(
    source, tmp_path
):
    env = {"SOURCE_DATE_EPOCH": "1"}

    def inputs():
        return package_build_inputs(source, env)

    cache = tmp_path / "cache"
    first = build_once(cache, products, inputs=inputs)
    identity = inputs()
    docs = source / "documentation"
    docs.mkdir()
    config = docs / "mkdocs.yml"
    config.write_text("broken: [documentation-only")
    assert inputs() == identity
    assert (
        build_once(cache, lambda _: pytest.fail("docs-only rebuild"), inputs=inputs)
        == first
    )
    config.write_text("another broken documentation configuration")
    assert inputs() == identity
    assert (
        build_once(cache, lambda _: pytest.fail("docs-only rebuild"), inputs=inputs)
        == first
    )
    root_config = source / "pyproject.toml"
    root_config.write_text(
        root_config.read_text() + "\n# real root build input changed\n"
    )
    assert inputs() != identity
    assert build_once(cache, products, inputs=inputs) != first


def test_selected_workspace_distribution_and_sibling_inputs_are_cache_identity(
    source, tmp_path
):
    workspace = tmp_path / "workspace"
    shutil.copytree(source, workspace)
    child = workspace / "packages/core"
    shutil.copytree(source, child)
    root_config = workspace / "pyproject.toml"
    root_config.write_text(
        root_config.read_text() + '\n[tool.uv.workspace]\nmembers = ["packages/core"]\n'
    )
    child_config = child / "pyproject.toml"
    child_config.write_text(
        child_config.read_text().replace(
            'name="repo-catalog"', 'name="repo-catalog-core"'
        )
    )
    before = package_build_inputs(workspace, {})
    selected_core = package_build_inputs(child, {})
    assert before != selected_core
    resource = child / "src/repo_catalog/schema.sql"
    # The specimen's runtime source set is finite; use a new classified resource
    # to show a same-path checkout edit affects both owning and composed builds.
    resource.write_text("SELECT 1;")
    assert package_build_inputs(workspace, {}) != before
    assert package_build_inputs(child, {}) != selected_core
    old = package_build_inputs(child, {})
    root_config.write_text(root_config.read_text() + "# changed workspace metadata\n")
    assert package_build_inputs(child, {}) != old
    for name, content in (
        ("hatch.toml", "[build]\nignore-vcs = true\n"),
        ("hatch_build.py", "# changed sibling backend hook\n"),
        ("uv.toml", "offline = true\n"),
    ):
        old_root = package_build_inputs(workspace, {})
        control = child / name
        control.write_text(content)
        assert package_build_inputs(workspace, {}) != old_root
        control.unlink()
        assert package_build_inputs(workspace, {}) == old_root
    old = package_build_inputs(child, {})
    (workspace / "uv.lock").write_text("changed shared dependency lock")
    assert package_build_inputs(child, {}) != old


def test_cached_dependency_artifact_tampering_is_rejected(tmp_path):
    def build(root):
        result = products(root)
        dependency = root / "dependencies/contract.whl"
        dependency.parent.mkdir()
        dependency.write_bytes(b"original dependency")
        result["sdist_contract"].write_text(
            json.dumps(
                {
                    "dependencies": [
                        {
                            "wheel": {
                                "path": str(dependency.relative_to(root)),
                                "sha256": hashlib.sha256(
                                    dependency.read_bytes()
                                ).hexdigest(),
                            }
                        }
                    ],
                }
            )
        )
        return result

    cached = build_once(tmp_path, build, inputs=lambda: "e" * 64)
    dependency = cached["wheel"].parent / "dependencies/contract.whl"
    dependency.write_bytes(b"tampered dependency")
    with pytest.raises(ValueError, match="Dependency build product changed"):
        build_once(
            tmp_path,
            lambda _: pytest.fail("must not rebuild silently"),
            inputs=lambda: "e" * 64,
        )
