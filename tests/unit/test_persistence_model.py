"""Separated design mapping regressions; no retained catalogue fixtures."""

import copy
import importlib.util
import os
import sqlite3
import stat
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import get_type_hints

import pytest

from scripts import generate_persistence_rows
from scripts.generate_persistence_rows import check_generated, render_modules
from scripts.persistence_model import (
    MODEL,
    ROOT,
    TARGET_FORMATS,
    load_model,
    physical_references,
    render_markdown,
    row_type_binding,
    validate_model,
)
from scripts.schema_catalog import build_catalog


@pytest.fixture(scope="module")
def catalog():
    return build_catalog()


@pytest.fixture(scope="module")
def model():
    return load_model()


@pytest.fixture(scope="module")
def row_types(model):
    modules, classes = {}, {}
    for record in model["classes"]:
        binding = record["row_type"]
        source = binding["path"]
        if source not in modules:
            name = "_persistence_rows_" + record["domain"]
            spec = importlib.util.spec_from_file_location(name, ROOT / source)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules[source] = module
        module = modules[source]
        cls = getattr(module, binding["symbol"])
        assert module.ROW_TYPES[record["table"]] is cls
        classes[record["id"]] = cls
    for source, module in modules.items():
        assert set(module.ROW_TYPES) == {
            record["table"]
            for record in model["classes"]
            if record["row_type"]["path"] == source
        }
    return classes


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
        (
            lambda m: row(m, "Core.Repository").update(row_type=None),
            "row_type binding is required",
        ),
        (
            lambda m: row(m, "Core.Repository")["row_type"].update(symbol="GoneRow"),
            "dedicated domain module/name",
        ),
        (
            lambda m: row(m, "Core.Repository")["row_type"].update(
                path="packages/context/src/repo_catalog/adapters/sqlite/context_rows.py"
            ),
            "dedicated domain module/name",
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
    extra["row_type"] = row_type_binding(extra)
    extended["classes"].append(extra)
    # The mapping accepts a new class without a fixed count. Its generated source
    # must then be written before the default symbol/staleness checks can pass.
    assert validate_model(extended, changed, inspect_row_types=False) == []
    assert any(
        "Python class not found" in error for error in validate_model(extended, changed)
    )


@pytest.mark.parametrize(
    "section, identifier, change",
    [
        ("python", "Core.ScalarClaim", {"verified": True}),
        ("python", "Core.ScalarClaim", {"columns": ["field"]}),
        ("python", "Core.ScalarClaim", {"role": None}),
        ("row_type", "Core.ScalarClaim", {"columns": ["field"]}),
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
    elif section == "row_type":
        target = row(broken, identifier)["row_type"]
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


def sample_values(table):
    """Primitive examples exercise codecs, without claiming domain admissibility."""
    examples = {"TEXT": "value", "INTEGER": 7, "BLOB": b"\xff\x00path"}
    return {column["name"]: examples[column["type"]] for column in table["columns"]}


def test_every_generated_row_has_complete_typed_frozen_ddl_binding(
    model, catalog, row_types
):
    for record in model["classes"]:
        cls = row_types[record["id"]]
        table = catalog["stores"][TARGET_FORMATS[record["domain"]]]["tables"][
            record["table"]
        ]
        columns = table["columns"]
        assert is_dataclass(cls) and cls.__dataclass_params__.frozen
        assert (
            tuple(field.name for field in fields(cls))
            == cls.COLUMNS
            == tuple(column["name"] for column in columns)
        )
        assert cls.WRITE_COLUMNS == tuple(
            column["name"]
            for column in columns
            if not column["is_generated"] and not column["is_hidden"]
        )
        assert cls.KEY_COLUMNS == tuple(table["primary_key"])
        hints = get_type_hints(cls)
        primitive_types = {"TEXT": str, "INTEGER": int, "BLOB": bytes}
        for column in columns:
            expected = primitive_types[column["type"]]
            if not column["notnull"]:
                expected |= None
            assert hints[column["name"]] == expected
        values = sample_values(table)
        decoded = cls.from_record(dict(reversed(list(values.items()))))
        assert {
            field.name: getattr(decoded, field.name) for field in fields(cls)
        } == values
        assert decoded.key_values() == tuple(
            values[column] for column in table["primary_key"]
        )
        with pytest.raises(FrozenInstanceError):
            setattr(decoded, cls.COLUMNS[0], "changed")
        with pytest.raises(ValueError, match="full row"):
            cls.from_record(
                {key: value for key, value in values.items() if key != cls.COLUMNS[0]}
            )
        with pytest.raises(ValueError, match="unknown"):
            cls.from_record({**values, "not_a_column": "extra"})


def test_every_codec_preserves_nulls_and_rejects_coercion(model, catalog, row_types):
    for record in model["classes"]:
        cls = row_types[record["id"]]
        table = catalog["stores"][TARGET_FORMATS[record["domain"]]]["tables"][
            record["table"]
        ]
        values = sample_values(table)
        writable = {column: values[column] for column in cls.WRITE_COLUMNS}
        columns, bindings = cls.insert_bindings(dict(reversed(list(writable.items()))))
        assert columns == cls.WRITE_COLUMNS
        assert bindings == tuple(values[column] for column in columns)
        for column in table["columns"]:
            name = column["name"]
            null_values = {**values, name: None}
            if column["notnull"]:
                with pytest.raises(TypeError, match=name):
                    cls.from_record(null_values)
            else:
                assert getattr(cls.from_record(null_values), name) is None
            # bool is an int subclass, but never an admitted INTEGER primitive.
            wrong = True if column["type"] == "INTEGER" else 1
            with pytest.raises(TypeError, match=name):
                cls.from_record({**values, name: wrong})
            if name in cls.WRITE_COLUMNS:
                with pytest.raises(TypeError, match=name):
                    cls.insert_bindings({**writable, name: wrong})
                if column["default_value"] is None:
                    with pytest.raises(ValueError, match="missing required"):
                        cls.insert_bindings(
                            {
                                key: value
                                for key, value in writable.items()
                                if key != name
                            }
                        )
                else:
                    bound_columns, bound_values = cls.insert_bindings(
                        {key: value for key, value in writable.items() if key != name}
                    )
                    assert name not in bound_columns
                    assert bound_values == tuple(values[key] for key in bound_columns)
            else:
                with pytest.raises(ValueError, match="generated/hidden"):
                    cls.insert_bindings({**writable, name: values[name]})
        with pytest.raises(ValueError, match="unknown"):
            cls.insert_bindings({**writable, "not_a_column": None})
        # Direct construction has the same primitive validation as decoding.
        with pytest.raises(TypeError):
            cls(**{**values, cls.COLUMNS[0]: object()})


def test_sqlite_rows_keep_raw_paths_generated_values_and_sql_defaults(
    catalog, row_types
):
    from repo_catalog.adapters.sqlite.p1_schema import register_functions

    def insert(db, table, cls, values):
        columns, bindings = cls.insert_bindings(values)
        names = ", ".join(f'"{name}"' for name in columns)
        placeholders = ", ".join("?" for _ in columns)
        db.execute(f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})', bindings)
        return cls.from_record(db.execute(f'SELECT * FROM "{table}"').fetchone())

    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        # These isolated tables exercise actual DDL codecs/defaults, not complete
        # store admission, foreign-key relationships, or recovery semantics.
        register_functions(db, "context")
        for store, table in (
            ("filesystem", "entries"),
            ("p1.context", "field_candidates"),
            ("p1.operational", "request_budgets"),
        ):
            db.execute(catalog["stores"][store]["tables"][table]["sql"])
        entry_type = row_types["Filesystem.Entry"]
        entry_values = dict.fromkeys(entry_type.WRITE_COLUMNS)
        entry_values.update(
            namespace_uuid="namespace",
            scan_uuid="scan",
            relative_path=b"\xffnative\x00path",
            kind="directory",
            hash_status="not-applicable",
        )
        entry = insert(db, "entries", entry_type, entry_values)
        assert entry.relative_path == b"\xffnative\x00path"
        assert entry.key_values() == ("namespace", "scan", b"\xffnative\x00path")
        assert entry.size is None and entry.link_target is None

        field_type = row_types["Context.FieldCandidate"]
        field = insert(
            db,
            "field_candidates",
            field_type,
            {
                "service_instance_uuidv4": "service",
                "resource_kind": "issue",
                "provider_resource_id": "resource",
                "field_name": "title",
                "value_json": '"title"',
                "clock_json": '{"at_us":7,"domain":"source"}',
                "provenance_json": '{"evidence":"test","source":"provider"}',
                "observed_at_us": None,
            },
        )
        assert field.clock_domain == "source" and field.source_clock_us == 7
        assert field.text_body_sha256 is None
        assert {"clock_domain", "source_clock_us", "text_body_sha256"}.isdisjoint(
            field_type.WRITE_COLUMNS
        )
        with pytest.raises(ValueError, match="full row"):
            field_type.from_record(
                db.execute("SELECT field_name FROM field_candidates").fetchone()
            )

        budget = insert(
            db,
            "request_budgets",
            row_types["Operational.RequestBudget"],
            {
                "request_origin_uuidv4": "origin",
                "request_uuidv4": "request",
                "work_kind": "input_bytes",
                "finite_limit": 10,
            },
        )
        assert budget.spent_or_reserved == 0


def test_generated_modules_are_current_deterministic_and_independent(model, catalog):
    assert check_generated(model, catalog) == []
    modules = render_modules(model, catalog)
    assert modules == render_modules(copy.deepcopy(model), copy.deepcopy(catalog))
    assert len(modules) == len(TARGET_FORMATS)
    for source, contents in modules.items():
        assert (ROOT / source).read_bytes() == contents.encode("utf-8")
        assert "repo_catalog" not in contents
        assert "execute(" not in contents and "PRAGMA" not in contents


def test_generator_check_is_read_only_and_write_repairs_only_derived_files(
    model, catalog, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(generate_persistence_rows, "ROOT", tmp_path)
    monkeypatch.setattr(generate_persistence_rows, "load_model", lambda: model)
    monkeypatch.setattr(generate_persistence_rows, "build_catalog", lambda: catalog)
    assert generate_persistence_rows.main([]) == 1
    assert not list(tmp_path.iterdir())
    assert "stale generated" in capsys.readouterr().err
    assert generate_persistence_rows.main(["--write"]) == 0
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.py")}
    assert len(before) == len(TARGET_FORMATS)
    assert generate_persistence_rows.main(["--check"]) == 0
    assert {path: path.read_bytes() for path in before} == before
    stale = next(iter(before))
    stale.write_bytes(before[stale] + b"# stale\n")
    assert generate_persistence_rows.main([]) == 1
    assert stale.read_bytes().endswith(b"# stale\n")
    assert generate_persistence_rows.main(["--write"]) == 0
    assert {path: path.read_bytes() for path in before} == before


def test_generator_handles_hidden_columns_and_fails_closed_for_unknown_sql_types(
    model, catalog
):
    changed = copy.deepcopy(catalog)
    column = changed["stores"]["filesystem"]["tables"]["entries"]["columns"][2]
    column["is_hidden"] = True
    source = render_modules(model, changed)[
        row(model, "Filesystem.Entry")["row_type"]["path"]
    ]
    namespace = {"__name__": "_persistence_rows_hidden_test"}
    # A registered module is needed for dataclasses' standard annotation lookup.
    import types

    module = types.ModuleType(namespace["__name__"])
    sys.modules[module.__name__] = module
    exec(compile(source, "<generated hidden-column test>", "exec"), module.__dict__)
    cls = module.EntryRow
    assert "relative_path" in cls.COLUMNS and "relative_path" not in cls.WRITE_COLUMNS
    column["type"] = "REAL"
    with pytest.raises(ValueError, match="unsupported row column type"):
        render_modules(model, changed)


@pytest.mark.parametrize(
    "alias_kind", ["hardlink", "destination-symlink", "parent-symlink", "directory"]
)
def test_generator_refuses_late_alias_before_changing_any_output(
    model, catalog, tmp_path, monkeypatch, capsys, alias_kind
):
    root = tmp_path / "repository"
    root.mkdir()
    modules = render_modules(model, catalog)
    targets = [root / source for source in modules]
    for index, path in enumerate(targets):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"original output {index}\n".encode())
    # Worktrees is the last generated domain: earlier valid outputs must survive
    # refusal of this target. All outside files are disposable test sentinels.
    invalid = targets[-1]
    sentinel = tmp_path / "outside-sentinel.py"
    sentinel.write_bytes(b"outside sentinel must not change\n")
    invalid.unlink()
    if alias_kind == "hardlink":
        os.link(sentinel, invalid)
    elif alias_kind == "destination-symlink":
        invalid.symlink_to(sentinel)
    elif alias_kind == "parent-symlink":
        invalid.parent.rmdir()
        outside = tmp_path / "outside-parent"
        outside.mkdir()
        sentinel = outside / invalid.name
        sentinel.write_bytes(b"outside parent sentinel must not change\n")
        invalid.parent.symlink_to(outside, target_is_directory=True)
    else:
        invalid.mkdir()

    def snapshot(path):
        metadata = path.lstat()
        return (
            metadata.st_mode,
            metadata.st_ino,
            metadata.st_nlink,
            path.readlink() if path.is_symlink() else None,
            path.read_bytes() if path.is_file() else None,
        )

    before = {path: snapshot(path) for path in targets}
    outside_before = snapshot(sentinel)
    tree_before = set(root.rglob("*"))
    monkeypatch.setattr(generate_persistence_rows, "ROOT", root)
    monkeypatch.setattr(generate_persistence_rows, "load_model", lambda: model)
    monkeypatch.setattr(generate_persistence_rows, "build_catalog", lambda: catalog)
    assert generate_persistence_rows.main(["--write"]) == 1
    error = capsys.readouterr().err
    expected = (
        "real directory"
        if alias_kind == "parent-symlink"
        else "regular single-link file"
    )
    assert expected in error
    assert {path: snapshot(path) for path in targets} == before
    assert snapshot(sentinel) == outside_before
    assert set(root.rglob("*")) == tree_before
    assert not list(root.rglob("*.tmp"))


@pytest.mark.parametrize(
    "source",
    [
        "../outside.py",
        "./later.py",
        "nested/../later.py",
        "nested//later.py",
        ".",
        "",
        "absolute",
    ],
)
def test_generator_refuses_late_non_normalized_path_before_writing(tmp_path, source):
    root = tmp_path / "repository"
    root.mkdir()
    first = root / "first.py"
    first.write_bytes(b"original first output\n")
    sentinel = tmp_path / "outside.py"
    sentinel.write_bytes(b"outside sentinel\n")
    if source == "absolute":
        source = sentinel.as_posix()
    with pytest.raises(ValueError, match="normalized and repository-relative"):
        generate_persistence_rows.write_generated(
            {"first.py": "changed", source: "changed"}, root
        )
    assert first.read_bytes() == b"original first output\n"
    assert sentinel.read_bytes() == b"outside sentinel\n"
    assert set(root.iterdir()) == {first}


def test_generator_replaces_inodes_preserves_modes_and_cleans_staging(
    tmp_path, monkeypatch
):
    first, second = tmp_path / "first.py", tmp_path / "second.py"
    first.write_bytes(b"old first")
    second.write_bytes(b"old second")
    first.chmod(0o640)
    old_inode = first.stat().st_ino
    generate_persistence_rows.write_generated(
        {"first.py": "new first", "second.py": "new second"}, tmp_path
    )
    assert first.read_bytes() == b"new first" and second.read_bytes() == b"new second"
    assert first.stat().st_ino != old_inode
    assert stat.S_IMODE(first.stat().st_mode) == 0o640
    assert set(tmp_path.iterdir()) == {first, second}

    original_mkstemp = generate_persistence_rows.tempfile.mkstemp
    calls = 0

    def fail_second_temporary(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disposable temporary-file failure")
        return original_mkstemp(**kwargs)

    monkeypatch.setattr(
        generate_persistence_rows.tempfile, "mkstemp", fail_second_temporary
    )
    with pytest.raises(OSError, match="temporary-file failure"):
        generate_persistence_rows.write_generated(
            {"first.py": "never applied", "second.py": "never applied"}, tmp_path
        )
    assert first.read_bytes() == b"new first" and second.read_bytes() == b"new second"
    assert stat.S_IMODE(first.stat().st_mode) == 0o640
    assert set(tmp_path.iterdir()) == {first, second}
