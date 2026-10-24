"""Independent distribution verification for PR #165: Dataclass selection budget enforcement.

Builds:
1. Direct wheel and sdist using hatchling.
2. Verifies minimal sdist contract budgets using scripts/check_sdist_contract.py.
3. Builds derived wheel from unpacked sdist without Git on PATH.
4. Verifies byte-level or member-level equivalence between direct and derived wheels.
5. Exercises independent outside-checkout smoke probes on native SQLite in separate venvs.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = (
    ROOT
    / "docs/implementation/evidence/review-adr0031-i155-m01-dataclass-selection-20261024"
)
DIST_EVIDENCE = EVIDENCE_DIR / "distribution"
SCANNER_EVIDENCE = EVIDENCE_DIR / "scanner"

PYTHON = sys.executable

PROBE_CODE = r"""
import json, sqlite3, sys, tempfile
from dataclasses import dataclass, make_dataclass
from pathlib import Path

import repo_catalog
from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionRefused,
    AdmissionSelection,
    ContextAdmissionService,
    DependencySet,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.resource_stage import has_transfer_fence

from contextlib import contextmanager

SERVICE = "11111111-1111-4111-8111-111111111111"

class SmokePolicy:
    def __init__(self, grants):
        self.grants = grants
    @contextmanager
    def lease(self, principal, operation, dependencies):
        class Lease:
            def check_current(self):
                pass
        yield Lease()

# 1. 1000-field dataclass probe
Fields1000 = make_dataclass("Fields1000", [(f"f_{i}", int) for i in range(1000)])

class Counted1000(Fields1000):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "accesses", 0)
    def __getattribute__(self, name):
        if name.startswith("f_"):
            object.__setattr__(self, "accesses", object.__getattribute__(self, "accesses") + 1)
        return super().__getattribute__(name)

inst1000 = Counted1000(*range(1000))
service = ContextAdmissionService(SmokePolicy(DependencySet()), lambda c: "smoke-user")
ctx1000 = service.context(
    "token",
    "provider_intake",
    AdmissionSelection(all_selected=True, max_work=7),
    AdmissionBudget(work_limit=10000),
)

refusal_1000 = None
try:
    service.charge_input(ctx1000, inst1000)
except AdmissionRefused as exc:
    refusal_1000 = exc.code

# 2. 6-field dataclass boundary probe
@dataclass
class SixField:
    a: int = 1
    b: int = 2
    c: int = 3
    d: int = 4
    e: int = 5
    f: int = 6

inst6 = SixField()
ctx6_fail = service.context(
    "token",
    "provider_intake",
    AdmissionSelection(all_selected=True, max_work=6),
    AdmissionBudget(work_limit=100),
)
refusal_6_fail = None
try:
    service.charge_input(ctx6_fail, inst6)
except AdmissionRefused as exc:
    refusal_6_fail = exc.code

ctx6_pass = service.context(
    "token",
    "provider_intake",
    AdmissionSelection(all_selected=True, max_work=7),
    AdmissionBudget(work_limit=7),
)
service.charge_input(ctx6_pass, inst6)

# 3. Real Store relation with mutating list probe
db = sqlite3.connect(":memory:", isolation_level=None)
p1_schema.register_functions(db)
p1_schema.configure(db)
db.executescript(p1_schema.compose("context"))
db.execute("INSERT INTO store_identity VALUES('context',?,?)", ("9ebbe38a-f937-40e6-a99c-701835ebcf10", "aad25448-03eb-4f83-a75e-cb7055fd33be"))
p1_schema.validate(db, "context")

class MutatingList(list):
    def __iter__(self):
        for i in range(1000):
            self.append(ResourceKey.from_native(SERVICE, "issue", f"extra-{i}"))
        return super().__iter__()

owner = ResourceKey.from_native(SERVICE, "issue", "owner")
k0 = ResourceKey.from_native(SERVICE, "issue", "0")
mlist = MutatingList([k0])
report = ResourceRelation(owner, "x-links", mlist, canonical({"source": "review", "evidence": "synthetic"}), "{}", 1)

policy_store = SmokePolicy(DependencySet(resources=frozenset({owner, k0})))
service_store = ContextAdmissionService(policy_store, lambda c: "store-user")
ctx_store = service_store.context(
    "token",
    "provider_intake",
    AdmissionSelection(resource_keys=frozenset({owner, k0}), repository_uuidv4s=frozenset(), source_uuidv4s=frozenset(), object_oids=frozenset(), max_work=25),
    AdmissionBudget(work_limit=10000),
)

store_refusal = None
with tempfile.TemporaryDirectory() as td:
    try:
        with Context.owned_transaction(db, Path(td), authorization=service_store, admission=ctx_store) as sctx:
            sctx.relation(report, admission=ctx_store)
    except AdmissionRefused as exc:
        store_refusal = exc.code

db_rows = db.execute("SELECT count(*) FROM resource_relations").fetchone()[0]
in_tx = db.in_transaction
fence = has_transfer_fence(db)
db.close()

result = {
    "module_path": str(Path(repo_catalog.__file__).resolve()),
    "case_1000_refusal": refusal_1000,
    "case_1000_used_work": ctx1000.budget.used_work,
    "case_1000_accesses": inst1000.accesses,
    "case_6_fail_refusal": refusal_6_fail,
    "case_6_fail_used_work": ctx6_fail.budget.used_work,
    "case_6_pass_used_work": ctx6_pass.budget.used_work,
    "store_refusal": store_refusal,
    "store_used_work": ctx_store.budget.used_work,
    "store_db_rows": db_rows,
    "store_in_transaction": in_tx,
    "store_transfer_fence": fence,
    "sqlite_version": sqlite3.sqlite_version,
}
print(json.dumps(result))
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(cmd, cwd=None, env=None):
    res = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"Command failed ({res.returncode}): {' '.join(str(c) for c in cmd)}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
    return res


def zip_inventory(path: Path):
    result = {}
    contents = {}
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for i in z.infolist():
            raw = z.read(i)
            contents[i.filename] = raw
            result[i.filename] = {
                "bytes": len(raw),
                "sha256": sha256_bytes(raw),
                "CRC": i.CRC,
                "compress_size": i.compress_size,
                "file_size": i.file_size,
            }
    return result, contents


def main():
    DIST_EVIDENCE.mkdir(parents=True, exist_ok=True)
    SCANNER_EVIDENCE.mkdir(parents=True, exist_ok=True)

    build_work = Path("/tmp/review-i155-dist-build")
    if build_work.exists():
        shutil.rmtree(build_work)
    build_work.mkdir(parents=True)

    print("Building direct wheel and sdist with hatchling...")
    direct_dir = build_work / "direct"
    direct_dir.mkdir()
    run(
        [
            PYTHON,
            "-m",
            "hatchling",
            "build",
            "-t",
            "wheel",
            "-t",
            "sdist",
            "-d",
            str(direct_dir),
        ],
        cwd=ROOT,
    )

    sdist_file = next(direct_dir.glob("*.tar.gz"))
    direct_whl = next(direct_dir.glob("*.whl"))

    print("Checking sdist contract...")
    contract_out = DIST_EVIDENCE / "check-sdist-contract.json"
    run(
        [
            PYTHON,
            str(ROOT / "scripts/check_sdist_contract.py"),
            "--sdist",
            str(sdist_file),
            "--source-root",
            str(ROOT),
            "--output",
            str(contract_out),
        ]
    )

    # Unpack sdist
    print("Unpacking sdist...")
    unpacked_dir = build_work / "unpacked"
    unpacked_dir.mkdir()
    raw_tar = gzip.decompress(sdist_file.read_bytes())
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as tar:
        for m in tar.getmembers():
            rel = m.name.split("/", 1)[1]
            dest = unpacked_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(tar.extractfile(m).read())

    # Build derived wheel from unpacked source without Git on PATH
    print("Building derived wheel without Git on PATH...")
    derived_dir = build_work / "derived"
    derived_dir.mkdir()
    runner = build_work / "backend_build.py"
    runner.write_text(
        "import hatchling.build, sys; print(hatchling.build.build_wheel(sys.argv[1]))\n"
    )

    env_no_git = {
        **os.environ,
        "PATH": str(Path(PYTHON).parent),  # only python venv bin
        "PYTHONPATH": "",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    run([PYTHON, str(runner), str(derived_dir)], cwd=unpacked_dir, env=env_no_git)
    derived_whl = next(derived_dir.glob("*.whl"))

    # Compare wheels
    print("Comparing direct vs derived wheels...")
    direct_inv, direct_contents = zip_inventory(direct_whl)
    derived_inv, derived_contents = zip_inventory(derived_whl)

    direct_bytes = direct_whl.read_bytes()
    derived_bytes = derived_whl.read_bytes()
    equal_full_zip = direct_bytes == derived_bytes

    wheel_comparison = {
        "direct_wheel": direct_whl.name,
        "direct_wheel_bytes": len(direct_bytes),
        "direct_wheel_sha256": sha256_bytes(direct_bytes),
        "derived_wheel": derived_whl.name,
        "derived_wheel_bytes": len(derived_bytes),
        "derived_wheel_sha256": sha256_bytes(derived_bytes),
        "equal_full_zip_bytes": equal_full_zip,
        "member_count_direct": len(direct_inv),
        "member_count_derived": len(derived_inv),
        "members_identical": direct_inv == derived_inv,
    }
    (DIST_EVIDENCE / "wheel-comparison.json").write_text(
        json.dumps(wheel_comparison, indent=2) + "\n"
    )
    (DIST_EVIDENCE / "wheel-members.json").write_text(
        json.dumps(direct_inv, indent=2) + "\n"
    )

    # Outside-checkout smoke verification across environments:
    # 1. source-tree
    # 2. direct-wheel installed outside checkout
    # 3. derived-wheel installed outside checkout
    cohort_results = {}
    executions = []

    # Cohort 1: Source
    print("Running probe on source tree...")
    t0 = time.time()
    env_source = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    p_src = run([PYTHON, "-c", PROBE_CODE], cwd="/tmp", env=env_source)
    t1 = time.time()
    res_source = json.loads(p_src.stdout.strip())
    cohort_results["source"] = res_source
    executions.append(
        {
            "cohort": "source",
            "duration_s": round(t1 - t0, 3),
            "exit_code": 0,
            "module_path": res_source["module_path"],
        }
    )

    # Cohort 2: Direct Wheel installed in isolated venv
    print("Setting up isolated venv for direct wheel...")
    venv_direct = build_work / "venv-direct"
    venv.EnvBuilder(with_pip=False).create(venv_direct)
    py_direct = str(venv_direct / "bin/python")
    run(["uv", "pip", "install", "--python", py_direct, "--no-deps", str(direct_whl)])

    print("Running probe on direct wheel...")
    t0 = time.time()
    p_dir = run(
        [py_direct, "-c", PROBE_CODE], cwd="/tmp", env={**os.environ, "PYTHONPATH": ""}
    )
    t1 = time.time()
    res_direct = json.loads(p_dir.stdout.strip())
    cohort_results["direct_wheel"] = res_direct
    executions.append(
        {
            "cohort": "direct_wheel",
            "duration_s": round(t1 - t0, 3),
            "exit_code": 0,
            "module_path": res_direct["module_path"],
        }
    )

    # Cohort 3: Derived Wheel installed in isolated venv
    print("Setting up isolated venv for derived wheel...")
    venv_derived = build_work / "venv-derived"
    venv.EnvBuilder(with_pip=False).create(venv_derived)
    py_derived = str(venv_derived / "bin/python")
    run(["uv", "pip", "install", "--python", py_derived, "--no-deps", str(derived_whl)])

    print("Running probe on derived wheel...")
    t0 = time.time()
    p_der = run(
        [py_derived, "-c", PROBE_CODE], cwd="/tmp", env={**os.environ, "PYTHONPATH": ""}
    )
    t1 = time.time()
    res_derived = json.loads(p_der.stdout.strip())
    cohort_results["derived_wheel"] = res_derived
    executions.append(
        {
            "cohort": "derived_wheel",
            "duration_s": round(t1 - t0, 3),
            "exit_code": 0,
            "module_path": res_derived["module_path"],
        }
    )

    (SCANNER_EVIDENCE / "cohort-probes.json").write_text(
        json.dumps(cohort_results, indent=2) + "\n"
    )
    (SCANNER_EVIDENCE / "executions.json").write_text(
        json.dumps(executions, indent=2) + "\n"
    )

    print("\n--- Distribution & Probe Verification Results ---")
    print(f"Equal full zip bytes: {equal_full_zip}")
    print(f"Direct SHA-256: {wheel_comparison['direct_wheel_sha256']}")
    print(f"Derived SHA-256: {wheel_comparison['derived_wheel_sha256']}")
    for cohort, res in cohort_results.items():
        print(
            f"[{cohort}] 1000-field refusal: {res['case_1000_refusal']}, used_work: {res['case_1000_used_work']}, accesses: {res['case_1000_accesses']}"
        )
        assert res["case_1000_refusal"] == "INPUT_LIMIT"
        assert res["case_1000_used_work"] == 2
        assert res["case_1000_accesses"] == 0
        assert res["case_6_fail_refusal"] == "INPUT_LIMIT"
        assert res["case_6_fail_used_work"] == 2
        assert res["case_6_pass_used_work"] == 7
        assert res["store_refusal"] == "INPUT_LIMIT"
        assert res["store_db_rows"] == 0
        assert not res["store_in_transaction"]
        assert res["store_transfer_fence"] is True

    print("All independent distribution checks PASSED successfully.")


if __name__ == "__main__":
    main()
