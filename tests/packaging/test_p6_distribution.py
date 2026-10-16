"""Installed opt-in P6 query, Search, and CLI from wheel and wheel built from sdist."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.packaging.test_p1_distribution import p1_distributions, run  # noqa: F401


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_p6_installed_query_search_and_cli(
    p1_distributions,  # noqa: F811
    tmp_path: Path,
    variant: int,
    fmt: str,
) -> None:
    env, wheels = p1_distributions
    outside = tmp_path / "outside"
    outside.mkdir()
    venv = tmp_path / "venv"
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--no-deps",
            wheels[variant],
        ],
        outside,
        env,
    )
    script = r"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.p1_schema import initialize, verify_declared
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_context import FieldCandidate, FieldClock, ResourceKey, canonical
from repo_catalog.domain.p1_core import OID, NativeObject, native_oid
from repo_catalog.domain.production_query import PageRequest, SearchQuery

assert "site-packages" in str(Path(__import__("repo_catalog.application.production_query", fromlist=["x"]).__file__))
verify_declared()

repo, instance, service = (str(uuid4()) for _ in range(3))
cat = Path("catalog")
cat.mkdir()
for role in ("core", "context", "operational", "search"):
    initialize(cat / f"{role}.sqlite3", role, repo, instance)

class Budget:
    class Limits:
        note_bytes = 1024 * 1024
    limits = Limits()
    def require(self, unit, amount=1): pass
    def charge(self, unit, amount): pass

fmt = "FORMAT"
tree_body = b""
tree_oid_hex = native_oid(fmt, "tree", tree_body)
tree_native = NativeObject(OID(fmt, tree_oid_hex), "tree", tree_body, 0, hashlib.sha256(tree_body).hexdigest())

commit_raw = (
    f"tree {tree_oid_hex}\n"
    f"author Alice <alice@example.com> 1700000000 +0000\n"
    f"committer Alice <alice@example.com> 1700000000 +0000\n\n"
    f"installed p6 commit needle\n"
).encode("utf-8")
commit_oid_hex = native_oid(fmt, "commit", commit_raw)
commit_native = NativeObject(OID(fmt, commit_oid_hex), "commit", commit_raw, len(commit_raw), hashlib.sha256(commit_raw).hexdigest())

pr_key = ResourceKey(service, "pull_request", "1")
prov = canonical({"source": "github.rest", "evidence": "ev-1"})

def core_unit(db):
    with GitCore.for_transaction(db) as core:
        core.admit_repository(repo)
        core.admit_metadata(tree_native, str(uuid4()), Budget())
        core.admit_metadata(commit_native, str(uuid4()), Budget())

def ctx_unit(db):
    with Context.for_transaction(db, cat) as ctx:
        ctx.provider(service, "github", "{}")
        ctx.repository(repo, "{}")
        ctx.resource(pr_key, repo)
        ctx.admit_field(FieldCandidate(pr_key, "title", canonical("installed p6 pr needle"), FieldClock("gh", 10), prov, 10))
        ctx.link_core(pr_key, "head", fmt, commit_oid_hex, prov, lambda f, o: (f, o) == (fmt, commit_oid_hex))

PairCoordinator(cat).admit(core_unit, ctx_unit)

svc = ProductionQueryService(cat)
assert svc.detect_mode() == "paired"
paired_view = svc.get_paired_resource(pr_key, include_core_bytes=True)
assert paired_view.core_resolutions[0].available_in_core is True
assert paired_view.core_resolutions[0].object_view.retained_bytes.body_bytes == commit_raw

counts = svc.rebuild_search()
assert counts["git_metadata"] > 0 and counts["context_text"] > 0
res_proj = svc.search(SearchQuery(query_text="needle"))
assert res_proj.backend == "projection" and res_proj.total_count == 2

(cat / "search.sqlite3").unlink()
res_scan = svc.search(SearchQuery(query_text="needle"))
assert res_scan.backend == "authority_scan" and res_scan.hits == res_proj.hits

cli_out = subprocess.run(
    [sys.executable, "-m", "repo_catalog.cli.production_query", "status", "--catalog", str(cat)],
    check=True,
    capture_output=True,
    text=True,
)
assert json.loads(cli_out.stdout.strip())["mode"] == "paired"
""".replace("FORMAT", fmt)
    run([python, "-c", script], outside, env)
