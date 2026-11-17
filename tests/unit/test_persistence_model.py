"""Separated design mapping regressions; no retained catalogue fixtures."""

import copy
import subprocess
import sys

import pytest

from scripts.persistence_model import (
    MODEL,
    ROOT,
    TARGET_FORMATS,
    load_model,
    physical_references,
    render_markdown,
    validate_model,
)
from scripts.schema_catalog import build_catalog


@pytest.fixture(scope="module")
def catalog():
    return build_catalog()


@pytest.fixture(scope="module")
def model():
    return load_model()


def row(model, ident):
    return next(item for item in model["classes"] if item["id"] == ident)


def test_current_separated_ddl_has_exactly_one_class_per_table(model, catalog):
    assert validate_model(model, catalog) == []
    expected = {
        (store, name)
        for store in TARGET_FORMATS.values()
        for name in catalog["stores"][store]["tables"]
    }
    actual = [
        (TARGET_FORMATS[item["domain"]], item["table"]) for item in model["classes"]
    ]
    assert len(actual) == len(expected)
    assert set(actual) == expected
    assert (
        row(model, "Core.CoverageClaim")["table"]
        == row(model, "Context.CoverageClaim")["table"]
    )
    assert all(not store.startswith("normal.") for store, _ in actual)


@pytest.mark.parametrize(
    "mutate, diagnostic",
    [
        (lambda m: m["classes"].pop(), "table needs exactly one class"),
        (
            lambda m: m["classes"].append(copy.deepcopy(m["classes"][0])),
            "duplicate class identity",
        ),
        (
            lambda m: row(m, "Core.Repository").update(table="not_a_table"),
            "unknown target table",
        ),
        (
            lambda m: row(m, "Core.Repository").update(domain="context"),
            "responsibility ownership",
        ),
        (
            lambda m: row(m, "Core.Repository").update(kind="dto"),
            "persistent class kind",
        ),
        (
            lambda m: row(m, "Core.Repository").update(primary_key=["made_up"]),
            "must be derived",
        ),
        (
            lambda m: m["domains"]["core"].update(store="normal.core"),
            "wrong target format",
        ),
        (
            lambda m: m["nonpersistent_types"][0].update(table="scalar_claims"),
            "cannot own a table",
        ),
        (
            lambda m: m["nonpersistent_types"][0]["sources"].append("Core.Missing"),
            "unknown source class",
        ),
        (
            lambda m: m["nonpersistent_types"][0]["sources"].append("Core.OID"),
            "source must be a persistent class",
        ),
        (lambda m: m["external_references"].pop(), "reference coverage differs"),
        (
            lambda m: m["external_references"][0].update(source="Core.Repository"),
            "external source class differs",
        ),
        (
            lambda m: m["external_references"][0].update(target="Filesystem.Entry"),
            "external target class differs",
        ),
        (
            lambda m: m["external_references"][1].update(target="Context.Resource"),
            "declared domain",
        ),
        (
            lambda m: row(m, "Core.ScalarClaim")["python"].update(symbol="Gone"),
            "Python class not found",
        ),
        (
            lambda m: row(m, "Core.ScalarClaim")["python"].update(path="../outside.py"),
            "repository-relative",
        ),
        (
            lambda m: row(m, "Core.ScalarClaim")["python"].update(
                path="scripts/persistence_model.py"
            ),
            "product distribution",
        ),
        (
            lambda m: row(m, "Core.ScalarClaim")["python"].update(
                role="complete-row-proof"
            ),
            "Python role",
        ),
    ],
)
def test_missing_or_misclassified_correspondence_is_rejected(
    model, catalog, mutate, diagnostic
):
    broken = copy.deepcopy(model)
    mutate(broken)
    assert any(diagnostic in error for error in validate_model(broken, catalog))


def test_new_ddl_table_requires_a_mapping_without_a_fixed_table_count(model, catalog):
    changed = copy.deepcopy(catalog)
    store = changed["stores"]["filesystem"]
    table = copy.deepcopy(store["tables"]["catalog_metadata"])
    table["name"] = "additional_metadata"
    store["tables"]["additional_metadata"] = table
    store["table_count"] += 1
    store["extracted_objects"].append({"type": "table", "name": "additional_metadata"})
    assert validate_model(model, changed) == [
        "table needs exactly one class: filesystem.additional_metadata"
    ]
    extended = copy.deepcopy(model)
    extra = copy.deepcopy(row(extended, "Filesystem.CatalogMetadata"))
    extra.update(id="Filesystem.AdditionalMetadata", table="additional_metadata")
    extended["classes"].append(extra)
    assert validate_model(extended, changed) == []


@pytest.mark.parametrize(
    "section, identifier, change",
    [
        ("python", "Core.ScalarClaim", {"verified": True}),
        ("python", "Core.ScalarClaim", {"columns": ["field"]}),
        ("python", "Core.ScalarClaim", {"role": None}),
        ("type-python", "Core.OID", {"verified": True}),
        ("type-python", "Core.OID", {"role": "row-input"}),
        ("external", "worktrees.filesystem-scan", {"physical_foreign_key": True}),
        ("external", "worktrees.filesystem-scan", {"source_columns": ["root_path"]}),
    ],
)
def test_nested_bindings_reject_copied_ddl_or_proof_fields(
    model, catalog, section, identifier, change
):
    broken = copy.deepcopy(model)
    if section == "external":
        target = next(
            item for item in broken["external_references"] if item["id"] == identifier
        )
    elif section == "type-python":
        target = next(
            item for item in broken["nonpersistent_types"] if item["id"] == identifier
        )["python"]
    else:
        target = row(broken, identifier)["python"]
    target.update(change)
    assert any(
        "binding fields" in error or "Python role" in error
        for error in validate_model(broken, catalog)
    )


@pytest.mark.parametrize(
    "section, field", [("python", "symbol"), ("python", "role"), ("external", "target")]
)
def test_incomplete_nested_bindings_fail(model, catalog, section, field):
    broken = copy.deepcopy(model)
    target = (
        row(broken, "Core.ScalarClaim")["python"]
        if section == "python"
        else broken["external_references"][0]
    )
    del target[field]
    assert any("binding fields" in error for error in validate_model(broken, catalog))


def test_report_keeps_actual_keys_and_resolves_implicit_physical_fk_order(
    model, catalog
):
    report = render_markdown(model, catalog)
    for item in model["classes"]:
        store = TARGET_FORMATS[item["domain"]]
        expected = catalog["stores"][store]["tables"][item["table"]]["primary_key"]
        assert f"`({', '.join(expected)})`" in report
    assert "`(namespace_uuid, scan_uuid, relative_path)`" in report
    assert "`(observation_uuid, root_path)`" in report
    assert (
        "Core.GitObject | entity | `git_objects` | `(object_format, object_oid)`"
        in report
    )
    refs = physical_references(catalog, "p1.operational", "work_accounting")
    assert refs == [
        {
            "source_columns": fk["from_columns"],
            "target_table": fk["target_table"],
            "target_columns": catalog["stores"]["p1.operational"]["tables"][
                fk["target_table"]
            ]["primary_key"],
        }
        for fk in catalog["stores"]["p1.operational"]["tables"]["work_accounting"][
            "foreign_keys"
        ]
    ]
    assert all(None not in ref["target_columns"] for ref in refs)
    assert "repo-catalog-contracts" in report and "Composition:" in report


def test_aggregate_values_and_optional_links_remain_distinct_from_rows(model, catalog):
    types = {item["id"]: item for item in model["nonpersistent_types"]}
    assert set(types["Filesystem.ScanResult"]["sources"]) == {
        "Filesystem.Scan",
        "Filesystem.ScanOutcome",
        "Filesystem.Entry",
    }
    assert types["Filesystem.RootPath"]["kind"] == "value"
    assert types["Worktrees.WorktreeEntry"]["kind"] == "dto"
    assert "WorktreeEntry" not in {
        item.get("python", {}).get("symbol")
        for item in model["classes"]
        if item.get("python")
    }
    assert row(model, "Core.Repository")["python"] is None
    report = render_markdown(model, catalog)
    external = report.split("## Registered optional external references", 1)[1].split(
        "## Nonpersistent types", 1
    )[0]
    assert "Worktrees.ScanReference" in external and "Filesystem.Scan" in external
    assert "domain claim; no target-row verification" in external
    assert "missing target: unresolved" in external
    assert "not cross-DB physical FKs" in external
    assert "runtime-created virtual/shadow" in report
    assert "AST presence does not prove row serialization" in report


@pytest.mark.parametrize("arguments", [[], ["--check"], ["--format", "markdown"]])
def test_command_works_outside_checkout_and_writes_no_files(tmp_path, arguments):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/persistence_model.py"), *arguments],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.startswith(
        "# Separated" if "--format" in arguments else "Persistence mapping OK:"
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("payload", ["{", "[]", '{"schema_version":1,"domains":null}'])
def test_malformed_input_fails_cleanly_without_emitting_a_report(tmp_path, payload):
    source = tmp_path / "bad.json"
    source.write_text(payload)
    before = MODEL.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/persistence_model.py"),
            "--format",
            "markdown",
            "--model",
            str(source),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    assert result.stdout == "" and "Traceback" not in result.stderr
    assert "Persistence mapping" in result.stderr
    assert MODEL.read_bytes() == before and source.read_text() == payload
