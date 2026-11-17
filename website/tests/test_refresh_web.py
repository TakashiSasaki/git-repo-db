"""Refresh decisions use real Git snapshots and isolated fake producer/renderers."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.product_context import PRODUCT_ROOT

SPEC = importlib.util.spec_from_file_location(
    "web_refresh_command",
    Path(__file__).resolve().parents[2] / "scripts/refresh_web.py",
)
refresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def initialize(root):
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Refresh tests")
    git(root, "config", "user.email", "refresh-tests@example.invalid")


def commit(root, message):
    git(root, "add", ".")
    git(root, "commit", "-qm", message)


def put(root, name, text):
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    web, product = tmp_path / "web", tmp_path / "product"
    initialize(web)
    initialize(product)
    for name, text in {
        "src/domain.py": "one",
        "scripts/schema_inventory.py": "PRODUCER_CONTROLS = frozenset({'scripts/schema_inventory.py', 'pyproject.toml'})",
        "pyproject.toml": "project",
        "docs/web-source-policy.json": json.dumps(
            {
                "canonical_index": "docs/adr/README.md",
                "public_adrs": [],
                "support": ["docs/public.md"],
            }
        ),
        "docs/adr/README.md": "index",
        "docs/public.md": "public contract",
        "docs/architecture/private.md": "unpublished contract",
    }.items():
        put(product, name, text)
    commit(product, "initial product")
    for name, text in {
        ".gitignore": "website/.build/\nwebsite/.venv/\n",
        "product-source.json": "{}",
        "website/pyproject.toml": "website project",
        "website/uv.lock": "lock",
        "website/tools/schema_viz.py": "renderer",
        "website/schema/README.md": "old artifact",
        "website/content/architecture/index.md": "Read docs/architecture/private.md",
        "website/content/development/index.md": "Development instructions",
        "website/content/design/model.json": '{"reference": "docs/architecture/private.md"}',
    }.items():
        put(web, name, text)
    commit(web, "initial website")
    monkeypatch.setattr(refresh, "ROOT", web)
    spec = importlib.util.spec_from_file_location(
        "refresh_private_writer", PRODUCT_ROOT / "scripts/verification_outputs.py"
    )
    private = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(private)
    calls = SimpleNamespace(prepare=0, generate=0, verify=0)

    def verify(root, source):
        calls.verify += 1
        if git(root, "rev-parse", "HEAD") != source:
            raise ValueError("Source changed")

    integrity = SimpleNamespace(verify_checkout=verify)

    def helpers(snapshot):
        verify(Path(snapshot["path"]), snapshot["commit"])
        return integrity, private

    def prepare(snapshot, *, log=None):
        calls.prepare += 1
        root = Path(snapshot["path"])
        base = web / "website/.build/inputs"
        ir = json.dumps({"data": (root / "src/domain.py").read_text()}).encode()
        identity = {k: snapshot[k] for k in ("commit", "tree")}
        producer = {
            "product_source": identity,
            "ir_sha256": refresh.digest(ir),
            "input_sha256": {
                p: refresh.digest((root / p).read_bytes())
                for p in (
                    "src/domain.py",
                    "scripts/schema_inventory.py",
                    "pyproject.toml",
                )
            },
        }
        canonical = {
            "product_source": identity,
            "ir_sha256": refresh.digest(ir),
            "canonical_sources": {
                p: refresh.digest((root / p).read_bytes())
                for p in (
                    "docs/web-source-policy.json",
                    "docs/adr/README.md",
                    "docs/public.md",
                )
            },
        }
        private.write_private(web, base / "inventory.json", ir)
        put(web, "website/.venv/bin/python", "isolated test interpreter")
        for name, value in [
            ("producer.json", producer),
            ("source-manifest.json", canonical),
            ("product-location.json", snapshot),
        ]:
            private.write_private_json(web, base / name, value)

    def generate(snapshot, destination, log):
        calls.generate += 1
        value = json.loads((web / "website/.build/inputs/inventory.json").read_text())[
            "data"
        ]
        put(destination, "README.md", "generated " + value)

    monkeypatch.setattr(refresh.prepare, "product_helpers", helpers)
    monkeypatch.setattr(refresh.prepare, "prepare_inputs", prepare)
    monkeypatch.setattr(refresh, "generate", generate)

    def select():
        return refresh.prepare.prepare_checkout(
            {"repository": str(product), "ref": "main"}, cache=tmp_path / "checkouts"
        )

    return SimpleNamespace(
        web=web,
        product=product,
        calls=calls,
        select=select,
        private=private,
        state=web / refresh.REPORT / "state.json",
    )


def test_first_refresh_then_noop_reuses_inputs_and_retains_pending(workspace):
    w = workspace
    first = refresh.refresh(w.select())
    assert first["baseline"] == "unassessed" and first["pending_review"]
    assert first["generated_files_changed"] == ["website/schema/README.md"]
    before = (w.web / "website/schema/README.md").stat().st_mtime_ns
    second = refresh.refresh(w.select())
    assert second["actions"] == {
        "prepared": False,
        "generated": False,
        "reused_prepared_inputs": True,
    }
    assert second["pending_review"] == first["pending_review"]
    assert w.calls.prepare == w.calls.generate == 1
    assert w.calls.verify > 1
    assert (w.web / "website/schema/README.md").stat().st_mtime_ns == before


def test_identical_generated_bytes_preserve_local_file_permissions(workspace):
    w = workspace
    target = w.web / "website/schema/README.md"
    target.write_text("generated one")
    commit(w.web, "existing generated output")
    target.chmod(0o600)
    before = target.stat().st_mtime_ns
    report = refresh.refresh(w.select())
    assert report["generated_files_changed"] == []
    assert target.stat().st_mtime_ns == before
    assert target.stat().st_mode & 0o777 == 0o600


def test_unpublished_contract_change_adds_review_without_generation(workspace):
    w = workspace
    first = refresh.refresh(w.select())
    old_record = (w.web / "website/.build/inputs/producer.json").read_bytes()
    put(w.product, "docs/architecture/private.md", "changed contract")
    commit(w.product, "contract only")
    report = refresh.refresh(
        w.select(), acknowledge=[x["path"] for x in first["pending_review"]]
    )
    assert report["inspected_source"]["commit"] != report["prepared_source"]["commit"]
    assert not report["actions"]["prepared"] and not report["actions"]["generated"]
    assert (w.web / "website/.build/inputs/producer.json").read_bytes() == old_record
    assert {x["path"] for x in report["pending_review"]} == {
        "website/content/architecture/index.md",
        "website/content/design/model.json",
    }
    assert all(
        "Initial" not in reason
        for x in report["pending_review"]
        for reason in x["reasons"]
    )


def test_public_contract_refreshes_inputs_but_identical_ir_skips_generation(workspace):
    w = workspace
    refresh.refresh(w.select())
    put(w.product, "docs/public.md", "new public contract")
    commit(w.product, "canonical only")
    report = refresh.refresh(w.select())
    assert report["actions"]["prepared"] and not report["actions"]["generated"]
    assert w.calls.prepare == 2 and w.calls.generate == 1


def test_program_change_regenerates_and_check_leaves_baseline_unchanged(workspace):
    w = workspace
    refresh.refresh(w.select())
    state = w.state.read_bytes()
    put(w.product, "src/domain.py", "two")
    commit(w.product, "new schema")
    plan = refresh.refresh(w.select(), check=True)
    assert plan["actions"]["prepare_needed"] and w.state.read_bytes() == state
    assert w.calls.prepare == w.calls.generate == 1
    report = refresh.refresh(w.select())
    assert report["actions"]["generated"]
    assert (w.web / "website/schema/README.md").read_text() == "generated two"


def test_tampered_ir_is_rebuilt_not_accepted_by_fingerprint(workspace):
    w = workspace
    refresh.refresh(w.select())
    (w.web / "website/.build/inputs/inventory.json").write_text("tampered")
    report = refresh.refresh(w.select())
    assert report["actions"]["prepared"] and w.calls.prepare == 2
    assert not report["actions"]["generated"] and w.calls.generate == 1


@pytest.mark.parametrize("change", ["lock", "missing-environment"])
def test_render_environment_is_prepared_again_when_needed(workspace, change):
    w = workspace
    refresh.refresh(w.select())
    if change == "lock":
        put(w.web, "website/uv.lock", "changed locked dependencies")
    else:
        (w.web / "website/.venv/bin/python").unlink()
    report = refresh.refresh(w.select())
    assert report["actions"]["prepared"] and w.calls.prepare == 2
    assert (w.web / "website/.venv/bin/python").is_file()


def test_ignored_existing_generator_destination_is_preserved(workspace, monkeypatch):
    w = workspace
    refresh.refresh(w.select())
    name = "website/schema/dbml/new.dbml"
    put(w.web, ".git/info/exclude", name + "\n")
    put(w.web, name, "untracked ignored manual work")
    put(w.product, "src/domain.py", "two")
    commit(w.product, "new schema")
    original = refresh.generate

    def generate(snapshot, destination, log):
        original(snapshot, destination, log)
        put(destination, "dbml/new.dbml", "new generated artifact")

    monkeypatch.setattr(refresh, "generate", generate)
    state = w.state.read_bytes()
    with pytest.raises(ValueError, match="Uncommitted schema edit"):
        refresh.refresh(w.select())
    assert (w.web / name).read_text() == "untracked ignored manual work"
    assert w.state.read_bytes() == state


def test_failed_generation_preserves_artifacts_and_successful_baseline(
    workspace, monkeypatch
):
    w = workspace
    refresh.refresh(w.select())
    state = w.state.read_bytes()
    old_artifact = (w.web / "website/schema/README.md").read_bytes()
    put(w.product, "src/domain.py", "two")
    commit(w.product, "new schema")

    def fail(*args):
        raise ValueError("deliberate generator failure")

    monkeypatch.setattr(refresh, "generate", fail)
    with pytest.raises(ValueError, match="deliberate"):
        refresh.refresh(w.select())
    assert w.state.read_bytes() == state
    assert (w.web / "website/schema/README.md").read_bytes() == old_artifact
    assert (
        json.loads((w.web / refresh.REPORT / "report.json").read_text())["status"]
        == "failed"
    )


@pytest.mark.parametrize("kind", ["dirty", "hidden", "symlink", "hardlink", "staged"])
def test_unrelated_schema_edits_and_aliases_are_preserved(workspace, kind):
    w = workspace
    refresh.refresh(w.select())
    target = w.web / "website/schema/README.md"
    if kind in {"dirty", "hidden", "staged"}:
        if kind == "hidden":
            git(w.web, "update-index", "--assume-unchanged", "website/schema/README.md")
        target.write_text("manual work")
        if kind == "staged":
            git(w.web, "add", "website/schema/README.md")
    else:
        original = w.web / "manual.md"
        original.write_text("manual work")
        target.unlink()
        if kind == "symlink":
            target.symlink_to(original)
        else:
            os.link(original, target)
    state = w.state.read_bytes()
    with pytest.raises(ValueError):
        refresh.refresh(w.select())
    assert target.read_text() == "manual work" and w.state.read_bytes() == state
