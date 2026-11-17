"""Tests run in the docs environment against an explicit selected checkout."""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "website"))
from tools.product_context import PRODUCT_ROOT  # noqa: E402

PRODUCT_SOURCE_ROOTS = (
    PRODUCT_ROOT / "src",
    *sorted((PRODUCT_ROOT / "packages").glob("*/src")),
)
sys.path[:0] = [str(PRODUCT_ROOT), *(str(p) for p in PRODUCT_SOURCE_ROOTS)]
os.environ["RESOURCE_ATLAS_PRODUCT_ROOT"] = str(PRODUCT_ROOT)


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

    path = ROOT / "website/.build/inputs/inventory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.with_name("producer.json").exists():
        path.write_text(json.dumps(introspect_all()) + "\n")
