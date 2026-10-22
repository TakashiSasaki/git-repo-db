"""Author I2 collection/execution receipts on an explicitly measured SQLite.

Reuses the repository's duplicate-aware JUnit/journal reconciliation. This is
development evidence, not independent acceptance or release qualification.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import verify_i5_offline as evidence  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 0:
        parser.error("workers must be nonnegative")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    )
    db = sqlite3.connect(":memory:")
    evidence.write_json(
        out / "runtime-before-checks.json", evidence.runtime_metadata(db)
    )
    from repo_catalog.adapters.sqlite import p1_schema

    p1_schema.register_functions(db)
    p1_schema.configure(db)
    actual = db.execute("SELECT sqlite_version(),sqlite_source_id()").fetchone()
    runtime = {
        "python": sys.version,
        "executable": sys.executable,
        "sqlite_version": actual[0],
        "sqlite_source_id": actual[1],
        "compile_options": db.execute("PRAGMA compile_options").fetchall(),
        "pragmas": {
            name: db.execute(f"PRAGMA {name}").fetchall()
            for name in (
                *p1_schema.REQUIRED_PRAGMAS,
                "journal_mode",
                "synchronous",
                "encoding",
            )
        },
    }
    db.close()
    frozen = evidence.input_hashes()
    binding = {
        "head": evidence.git("rev-parse", "HEAD"),
        "tree": evidence.git("rev-parse", "HEAD^{tree}"),
        "tracked_status": evidence.git("status", "--porcelain", "--untracked-files=no"),
        "inputs": frozen,
        "runtime": runtime,
        "author_verification": True,
        "full_acceptance": False,
    }
    evidence.write_json(out / "input-binding.json", binding)
    targets = sorted(
        set(
            evidence.ci_targets()
            + [
                "tests/unit/test_resource_identity.py",
                "tests/unit/test_resource_key_identity.py",
                "tests/unit/test_resource_identification.py",
                "tests/unit/test_github_identity_boundaries.py",
                "tests/integration/p2_p3_compatibility/test_production_pair.py",
                "tests/packaging/test_p1_distribution.py",
                "tests/packaging/test_p2_distribution.py",
                "tests/packaging/test_p3_distribution.py",
                "tests/packaging/test_p4_distribution.py",
                "tests/packaging/test_p6_distribution.py",
                "tests/packaging/test_p7_distribution.py",
            ]
        )
    )
    evidence.write_json(out / "targets.json", targets)
    ordinary, ordinary_receipt = evidence.collect(
        out, "ordinary-collection", ["tests"], "not live and not benchmark"
    )
    selected, selected_receipt = evidence.collect(
        out, "selected-collection", targets, "not live and not benchmark"
    )
    if ordinary_receipt["exit_code"] or selected_receipt["exit_code"]:
        raise SystemExit("collection failed; see preserved receipts")
    assert len(selected) == len(set(selected))
    assert set(selected) <= set(ordinary)
    (out / "ordinary-not-executed.txt").write_text(
        "".join(node + "\n" for node in sorted(set(ordinary) - set(selected)))
    )
    run = evidence.run_cohort(out, "regressions", selected, args.workers)
    same = evidence.input_hashes() == frozen
    summary = {
        "ordinary_collected": len(ordinary),
        "selected": len(selected),
        "unexecuted_ordinary": len(set(ordinary) - set(selected)),
        "inputs_unchanged": same,
        "run": run,
    }
    evidence.write_json(out / "summary.json", summary)
    raise SystemExit(0 if same and evidence.cohort_succeeded(run) else 1)


if __name__ == "__main__":
    main()
