"""Inspect current independent role definitions without opening retained data.

Prior Phase 2 comparison receipts remain historical evidence. This is a structural
inventory, not an acceptance certificate or a new domain eligibility layer.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.schema_catalog import build_catalog

ROOT = Path(__file__).resolve().parents[1]


def report():
    return build_catalog()


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, ensure_ascii=False))
