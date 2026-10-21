"""Build an external proposal over frozen product DDL, never patch product files."""
from pathlib import Path
from repo_catalog.adapters.sqlite import p1_schema
from resource_udfs import register

ROOT = Path(__file__).resolve().parent


def compose():
    baseline = p1_schema.compose("context")
    start = baseline.index("CREATE TABLE resources(")
    end = baseline.index("CREATE TABLE text_bodies(", start)
    result = baseline[:start] + (ROOT / "resources.sql").read_text() + "\n" + baseline[end:]
    old = "REFERENCES resources(service_instance_uuidv4,resource_kind,provider_resource_id,document_kind,parent_resource_kind)"
    new = "REFERENCES resources(service_instance_uuidv4,resource_kind,provider_resource_id,reference_document_kind,identifier_namespace_kind)"
    assert result.count(old) == 1
    result = result.replace(old, new)
    # Fresh format only. No persisted old endpoint can be grandfathered in.
    result += """
-- I2-only staging fence: removed only with reviewed I3/I4/I5 replacement.
CREATE TRIGGER i2_transfer_stage_fence BEFORE INSERT ON resource_repository_relations
WHEN NEW.relation_kind IN('transfer_from_repository','transfer_to_repository')
BEGIN SELECT RAISE(ABORT,'Transfer requires I3-I5 implementation'); END;
"""
    return result


def configure(db):
    p1_schema.register_functions(db)
    register(db)
    for name, value in (("foreign_keys", "ON"), ("recursive_triggers", "ON"),
                        ("ignore_check_constraints", "OFF"),
                        ("defer_foreign_keys", "OFF"), ("trusted_schema", "ON"),
                        ("synchronous", "EXTRA")):
        db.execute(f"PRAGMA {name}={value}")
    expected = {"foreign_keys": 1, "recursive_triggers": 1,
                "ignore_check_constraints": 0, "defer_foreign_keys": 0,
                "trusted_schema": 1}
    for name, value in expected.items():
        assert db.execute(f"PRAGMA {name}").fetchone()[0] == value
