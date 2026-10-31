"""Tests run in the docs environment against an explicit selected checkout."""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_SOURCE_ROOTS = (
    ROOT / "src",
    ROOT / "packages/core/src",
    ROOT / "packages/contracts/src",
)
sys.path[:0] = [
    str(ROOT),
    *(str(path) for path in PRODUCT_SOURCE_ROOTS),
    str(ROOT / "documentation"),
]


@pytest.fixture
def product_source_env():
    """Fresh processes load all owners from this selected source checkout."""
    return dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(str(path) for path in PRODUCT_SOURCE_ROOTS),
    )


@pytest.fixture(scope="session", autouse=True)
def complete_inventory_fixture():
    # Unit tests consume the selected checkout's complete neutral IR. Hosted
    # build provenance is separately produced/verified before this test step.
    from scripts.schema_inventory import introspect_all

    path = ROOT / "documentation/.build/inputs/inventory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.with_name("producer.json").exists():
        path.write_text(json.dumps(introspect_all()) + "\n")
