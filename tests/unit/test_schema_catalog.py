"""All-format coverage and counterexamples, using actual packaged DDL."""

import copy
import json
import subprocess
import sys

import pytest

from scripts.schema_catalog import ROOT, validate_catalog, workspace_sources
from scripts.schema_inventory import introspect_all


@pytest.fixture(scope="module")
def catalog():
    return introspect_all("all")


def test_actual_formats_domains_and_distribution_ownership(catalog):
    assert validate_catalog(catalog) == []
    assert len(catalog["stores"]) == 10
    assert len(catalog["authority_domains"]) == 7
    assert len(catalog["distributions"]) == 15
    assert catalog["configurations"]["local"]["owned_stores"] == []
    assert (
        catalog["distributions"]["repo-catalog-filesystem"]["dependency_requirements"]
        == []
    )
    assert (
        catalog["distributions"]["repo-catalog-worktrees"]["dependency_requirements"]
        == []
    )
    core = catalog["stores"]["p1.core"]
    assert core["composition_distribution"] == "repo-catalog-runtime"
    assert {source["distribution"] for source in core["definition_sources"]} == {
        "repo-catalog-core",
        "repo-catalog-runtime",
        "repo-catalog-contracts",
    }


def test_p1_extraction_matches_committed_product_manifest(catalog):
    manifest = json.loads(
        (
            ROOT
            / "packages/runtime/src/repo_catalog/adapters/sqlite/p1_ddl/fingerprints.json"
        ).read_text()
    )
    for role, expected in manifest["stores"].items():
        actual = catalog["stores"]["p1." + role]
        assert sorted(actual["tables"]) == sorted(expected["tables"])
        assert actual["ddl_sha256"] == expected["ddl_sha256"]
        assert actual["format_id"] == manifest["format"]
        # The product exposes a format ID, not a separate integer schema version.
        assert actual["schema_version"] is None


def test_local_keys_raw_path_types_and_nonphysical_references(catalog):
    fs = catalog["stores"]["filesystem"]
    wt = catalog["stores"]["worktrees"]
    assert fs["format_id"] is None and fs["schema_version"] == 1
    assert (
        wt["format_id"] == "repo-catalog/worktrees-1" and wt["schema_version"] is None
    )
    entries = fs["tables"]["entries"]
    assert entries["primary_key"] == ["namespace_uuid", "scan_uuid", "relative_path"]
    assert (
        next(c for c in entries["columns"] if c["name"] == "relative_path")["type"]
        == "BLOB"
    )
    refs = wt["tables"]["scan_references"]
    assert refs["without_rowid"] and refs["is_strict"]
    assert [fk["target_table"] for fk in refs["foreign_keys"]] == ["worktrees"]
    assert catalog["optional_references"][0]["target_columns"] == [
        "namespace_uuid",
        "scan_uuid",
    ]
    assert all(
        r["missing_target"] == "unresolved" for r in catalog["optional_references"]
    )
    assert catalog["scope"]["instances_read"] == 0


def test_udfs_and_extraction_settings_are_observed_not_semantically_proved(catalog):
    for store in catalog["stores"].values():
        assert store["extraction_connection"]["pragmas"]["foreign_keys"] == 1
    core = catalog["stores"]["p1.core"]["extraction_connection"]
    assert core["pragmas"]["recursive_triggers"] == 1
    assert "p1_uuid4" in {f["name"] for f in core["registered_functions"]}
    fs = catalog["stores"]["filesystem"]["extraction_connection"]
    assert fs["pragmas"]["trusted_schema"] == 0
    assert not any(f["name"].startswith("p1_") for f in fs["registered_functions"])


@pytest.mark.parametrize(
    "mutation,diagnostic",
    [
        (lambda c: c["stores"].pop("filesystem"), "schema coverage"),
        (lambda c: c["stores"].clear(), "schema coverage"),
        (
            lambda c: c["stores"]["worktrees"]["tables"].pop("repository_links"),
            "schema object coverage",
        ),
        (
            lambda c: c["stores"]["filesystem"]["tables"]["entries"]["columns"].pop(),
            "column coverage",
        ),
        (
            lambda c: c["stores"]["filesystem"]["triggers"].pop("entries_closed"),
            "schema object coverage",
        ),
        (
            lambda c: c["stores"]["filesystem"].update(
                composition_distribution="repo-catalog-core"
            ),
            "ownership/domain",
        ),
        (lambda c: c["source_ownership"].clear(), "source ownership"),
        (lambda c: c["configurations"].pop("p1"), "configuration coverage"),
        (
            lambda c: c["configurations"]["local"].update(owned_stores=["filesystem"]),
            "must not own",
        ),
        (lambda c: c["optional_references"].clear(), "reference coverage"),
        (
            lambda c: c["optional_references"][0]["source_columns"].pop(),
            "incomplete qualified",
        ),
        (
            lambda c: c["optional_references"][0].update(physical_foreign_key=True),
            "misclassified",
        ),
        (
            lambda c: c["stores"]["worktrees"]["tables"]["scan_references"][
                "foreign_keys"
            ][0].update(target_table="scans"),
            "physical FK endpoint",
        ),
    ],
)
def test_missing_targets_and_broken_structure_do_not_pass(
    catalog, mutation, diagnostic
):
    broken = copy.deepcopy(catalog)
    mutation(broken)
    assert any(diagnostic in error for error in validate_catalog(broken))


def test_inventory_is_deterministic_and_creates_no_persistent_databases(
    catalog, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert introspect_all("all") == catalog
    assert list(tmp_path.iterdir()) == []
    assert set(introspect_all()["stores"]) == {"core", "operational", "search"}
    with pytest.raises(ValueError, match="Unknown inventory profile"):
        introspect_all("missing")


def test_duplicate_namespace_definition_is_rejected(tmp_path):
    (tmp_path / "pyproject.toml").write_text("""
[project]
name = "one"
version = "1"
[tool.uv.workspace]
members = ["packages/two"]
[tool.hatch.build.targets.wheel]
packages = ["src/repo_catalog"]
""")
    other = tmp_path / "packages/two"
    other.mkdir(parents=True)
    (other / "pyproject.toml").write_text("""
[project]
name = "two"
version = "1"
[tool.hatch.build.targets.wheel]
packages = ["src/repo_catalog"]
""")
    for base in (tmp_path, other):
        source = base / "src/repo_catalog/example.py"
        source.parent.mkdir(parents=True)
        source.write_text("# same installed path, different distribution\n")
    with pytest.raises(ValueError, match="Duplicate installed source path"):
        workspace_sources(tmp_path)


def test_all_inventory_has_no_documentation_or_reasoner_dependency():
    script = """
import importlib.abc, sys
sys.path.insert(0, sys.argv[1])
class RefuseOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"rdflib", "pyshacl", "yaml", "mkdocs", "documentation"}:
            raise ImportError("unexpected optional dependency: " + fullname)
sys.meta_path.insert(0, RefuseOptional())
from scripts.schema_inventory import introspect_all, validate_inventory
assert not validate_inventory(introspect_all("all"), "all")
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
