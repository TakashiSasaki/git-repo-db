"""Audit the current separated schema/class boundary without retained DB access.

The older schema-inventory.json and table-disposition files are historical
normal-format migration inputs. They are preserved, never regenerated here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.persistence_model import (  # noqa: E402
    load_model,
    render_markdown,
    validate_model,
)
from scripts.schema_inventory import introspect_all  # noqa: E402

OUTPUT = ROOT / "docs/implementation"


def build() -> tuple[dict, str]:
    inventory = introspect_all()
    model = load_model()
    errors = validate_model(model, inventory)
    if errors:
        raise ValueError("Invalid separated boundary: " + "; ".join(errors))
    inventory["audit_contract"] = {
        "status": "current-separated-schema-and-class-boundary",
        "schema_definitions": len(inventory["stores"]),
        "logical_persistent_classes": sum(
            store["table_count"] for store in inventory["stores"].values()
        ),
        "inputs": [
            "docs/architecture/persistence-model.json",
            "scripts/schema_catalog.py registered packaged factories",
            "declared distribution source ownership",
        ],
        "checks": [
            "Every current DDL table has one owning role and dedicated row class",
            "Ordered keys, columns, generated fields, FKs and all SQL retained",
            "Current factory fingerprints and qualified optional references",
        ],
        "limits": [
            "In-memory definitions only; no retained database was opened",
            "Structural coverage and Python symbol presence are not semantic proof",
            "Registered roles do not prescribe a startup set",
        ],
    }
    return inventory, render_markdown(model, inventory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    inventory, markdown = build()
    artifacts = {
        "separated-schema-inventory.json": json.dumps(
            inventory, indent=2, sort_keys=True
        )
        + "\n",
        "separated-persistence-boundary.md": markdown,
    }
    stale = []
    for name, content in artifacts.items():
        path = OUTPUT / name
        if args.check:
            if not path.is_file() or path.read_text() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content, encoding="utf-8")
    if stale:
        print("stale audit artifacts: " + ", ".join(stale), file=sys.stderr)
        return 1
    print(json.dumps(inventory["audit_contract"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
