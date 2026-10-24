"""Build distributions, execute scanner cohorts across source and wheels, and record evidence."""

import base64
import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path

ROOT = Path(
    "/home/ubuntu/github/git-repo-db/fix/adr0031-i155-m01-dataclass-selection-20261024"
)
EVIDENCE = (
    ROOT / "docs/implementation/evidence/adr0031-i155-m01-dataclass-selection-20261024"
)
SCANNER_DIR = EVIDENCE / "scanner"
DIST_DIR = EVIDENCE / "distribution"
WORK = Path("/tmp/i155-dataclass-dist")

PYTHON = "/home/ubuntu/venv/bin/python"
UV = "/usr/local/bin/uv"
BASE_HEAD = "bebc039ed9772edf0737caf8f5520134907317e0"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob_oid(path: Path) -> str:
    raw = path.read_bytes()
    header = f"blob {len(raw)}\0".encode()
    return hashlib.sha1(header + raw).hexdigest()


def run_cmd(argv, cwd=None, env=None):
    res = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED: {argv}\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        raise RuntimeError(f"Command failed: {argv}")
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
        record_name = next(n for n in contents if n.endswith(".dist-info/RECORD"))
        seen = set()
        for row in csv.reader(io.StringIO(contents[record_name].decode())):
            if not row:
                continue
            name, digest, size = row[0], row[1], row[2]
            assert name in contents and name not in seen
            seen.add(name)
            if name != record_name:
                expected = (
                    "sha256="
                    + base64.urlsafe_b64encode(hashlib.sha256(contents[name]).digest())
                    .rstrip(b"=")
                    .decode()
                )
                assert digest == expected and size == str(len(contents[name]))
            else:
                assert not digest and not size
        assert seen == set(contents)
    return result, contents


def build_and_verify_distribution():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)

    direct_dir = WORK / "direct"
    direct_dir.mkdir()
    print("Building direct sdist and wheel...")
    run_cmd(
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

    sdist_path = next(direct_dir.glob("*.tar.gz"))
    wheel_path = next(direct_dir.glob("*.whl"))

    print("Checking sdist contract via check_sdist_contract.py...")
    sdist_check_out = DIST_DIR / "check-sdist-contract.json"
    run_cmd(
        [
            PYTHON,
            str(ROOT / "scripts/check_sdist_contract.py"),
            "--sdist",
            str(sdist_path),
            "--source-root",
            str(ROOT),
            "--output",
            str(sdist_check_out),
        ]
    )

    # Unpack sdist
    extracted_dir = WORK / "extracted"
    extracted_dir.mkdir()
    raw_tar = gzip.decompress(sdist_path.read_bytes())
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as tar:
        members = tar.getmembers()
        assert all(m.type in (tarfile.REGTYPE, tarfile.AREGTYPE) for m in members)
        for m in members:
            rel = m.name.split("/", 1)[1]
            dest = extracted_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(tar.extractfile(m).read())

    # Build derived wheel from extracted source without Git on PATH
    derived_dir = WORK / "derived"
    derived_dir.mkdir()
    runner = WORK / "backend_build.py"
    runner.write_text(
        "import hatchling.build, sys; print(hatchling.build.build_wheel(sys.argv[1]))\n"
    )

    env_no_git = {
        **os.environ,
        "PATH": str(Path(PYTHON).parent),  # only python venv bin
        "PYTHONPATH": "",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    print("Building derived wheel from unpacked sdist without Git...")
    run_cmd([PYTHON, str(runner), str(derived_dir)], cwd=extracted_dir, env=env_no_git)
    derived_wheel_path = next(derived_dir.glob("*.whl"))

    # Compare direct wheel vs derived wheel
    direct_inv, direct_contents = zip_inventory(wheel_path)
    derived_inv, derived_contents = zip_inventory(derived_wheel_path)
    assert direct_inv == derived_inv
    assert direct_contents == derived_contents
    assert wheel_path.read_bytes() == derived_wheel_path.read_bytes()

    dist_measurements = {
        "sdist": {
            "name": sdist_path.name,
            "bytes": sdist_path.stat().st_size,
            "sha256": sha256_bytes(sdist_path.read_bytes()),
            "git_blob_oid": git_blob_oid(sdist_path),
            "tar_stream_bytes": len(raw_tar),
            "members": len(members),
        },
        "wheel": {
            "name": wheel_path.name,
            "bytes": wheel_path.stat().st_size,
            "sha256": sha256_bytes(wheel_path.read_bytes()),
            "git_blob_oid": git_blob_oid(wheel_path),
            "members": len(direct_inv),
            "equal_full_zip_bytes": True,
        },
        "contract_budgets": {
            "sdist_max_compressed_bytes": 2097152,
            "sdist_actual_compressed_bytes": sdist_path.stat().st_size,
            "sdist_max_members": 512,
            "sdist_actual_members": len(members),
            "tar_max_unpacked_bytes": 8388608,
            "tar_actual_unpacked_bytes": sum(m.size for m in members),
        },
    }
    (DIST_DIR / "build-measurements.json").write_text(
        json.dumps(dist_measurements, indent=2) + "\n"
    )
    (DIST_DIR / "wheel-members.json").write_text(
        json.dumps(direct_inv, indent=2) + "\n"
    )
    print("Distribution build & comparison complete.")

    return wheel_path, derived_wheel_path


def setup_environments(direct_wheel, derived_wheel):
    direct_venv = WORK / "direct-venv"
    derived_venv = WORK / "derived-venv"
    print("Creating isolated venvs...")
    run_cmd([UV, "venv", "--python", PYTHON, str(direct_venv)])
    run_cmd([UV, "venv", "--python", PYTHON, str(derived_venv)])

    print("Installing wheels into venvs...")
    run_cmd(
        [
            UV,
            "pip",
            "install",
            "--python",
            str(direct_venv / "bin/python"),
            "--no-deps",
            str(direct_wheel),
        ]
    )
    run_cmd(
        [
            UV,
            "pip",
            "install",
            "--python",
            str(derived_venv / "bin/python"),
            "--no-deps",
            str(derived_wheel),
        ]
    )

    # Setup source162-unfixed tree from BASE_HEAD
    source_unfixed = WORK / "source162-unfixed"
    source_unfixed.mkdir()
    with tarfile.open(
        fileobj=io.BytesIO(
            subprocess.run(
                ["git", "archive", BASE_HEAD, "src"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
        )
    ) as tar:
        tar.extractall(source_unfixed)

    return {
        "source162-unfixed": (PYTHON, str(source_unfixed / "src")),
        "source-fixed": (PYTHON, str(ROOT / "src")),
        "direct": (str(direct_venv / "bin/python"), None),
        "derived": (str(derived_venv / "bin/python"), None),
    }


def run_scanner_probes(cohorts):
    store_script = (
        ROOT
        / "docs/implementation/evidence/adr0031-i6b-sdist-c0-independent-20261024/scanner/store_case.py"
    )
    study_script = (
        ROOT
        / "docs/implementation/evidence/adr0031-i6b-sdist-c0-independent-20261024/scanner/study.py"
    )
    reproduce_script = SCANNER_DIR / "reproduce_reviewer_finding.py"

    executions = []
    store_results = {}
    study_results = {}
    mutation_results = {}

    for label, (interpreter, pythonpath) in cohorts.items():
        print(f"Running scanner probes for {label}...")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        # Include ROOT for tests.support
        base_pp = str(ROOT)
        if pythonpath is not None:
            env["PYTHONPATH"] = f"{pythonpath}:{base_pp}"
        else:
            env["PYTHONPATH"] = base_pp

        # 1. Run store_case.py
        store_out = SCANNER_DIR / f"store-{label}.json"
        cmd_store = [interpreter, str(store_script), "--output", str(store_out)]
        t0 = time.time()
        p_store = subprocess.run(
            cmd_store, cwd="/tmp", env=env, capture_output=True, text=True
        )
        t1 = time.time()
        assert p_store.returncode == 0, (
            f"store_case failed for {label}: {p_store.stderr}"
        )

        executions.append(
            {
                "cohort": label,
                "script": "store_case.py",
                "argv": cmd_store,
                "pythonpath": env["PYTHONPATH"],
                "exit_code": p_store.returncode,
                "duration_s": round(t1 - t0, 3),
                "output_sha256": sha256_bytes(store_out.read_bytes()),
            }
        )
        store_results[label] = json.loads(store_out.read_text())

        # 2. Run study.py
        study_out = SCANNER_DIR / f"study-{label}.json"
        cmd_study = [interpreter, str(study_script), "--output", str(study_out)]
        t0 = time.time()
        p_study = subprocess.run(
            cmd_study, cwd="/tmp", env=env, capture_output=True, text=True
        )
        t1 = time.time()
        assert p_study.returncode == 0, f"study failed for {label}: {p_study.stderr}"

        executions.append(
            {
                "cohort": label,
                "script": "study.py",
                "argv": cmd_study,
                "pythonpath": env["PYTHONPATH"],
                "exit_code": p_study.returncode,
                "duration_s": round(t1 - t0, 3),
                "output_sha256": sha256_bytes(study_out.read_bytes()),
            }
        )
        study_results[label] = json.loads(study_out.read_text())

        # 3. Run reproduce_reviewer_finding.py
        mutation_out = SCANNER_DIR / f"mutation-{label}.json"
        cmd_mut = [
            interpreter,
            str(reproduce_script),
            "--output",
            str(mutation_out),
        ]
        t0 = time.time()
        p_mut = subprocess.run(
            cmd_mut, cwd="/tmp", env=env, capture_output=True, text=True
        )
        t1 = time.time()
        assert p_mut.returncode == 0, (
            f"mutation probe failed for {label}: {p_mut.stderr}"
        )

        executions.append(
            {
                "cohort": label,
                "script": "reproduce_reviewer_finding.py",
                "argv": cmd_mut,
                "pythonpath": env["PYTHONPATH"],
                "exit_code": p_mut.returncode,
                "duration_s": round(t1 - t0, 3),
                "output_sha256": sha256_bytes(mutation_out.read_bytes()),
            }
        )
        mutation_results[label] = json.loads(mutation_out.read_text())

    (SCANNER_DIR / "executions.json").write_text(
        json.dumps(executions, indent=2) + "\n"
    )

    # Generate summary comparison
    summary = {
        "finding": "I155-M01 Final Author Correction",
        "description": "Admission scanner work-budget enforcement, callback exception containment, and bounded queue/snapshot verification",
        "cohorts": list(cohorts.keys()),
        "mutation_probes_comparison": {},
        "store_case_comparison": {},
        "study_admission_comparison": {},
    }

    for label in cohorts:
        mut = mutation_results[label]
        summary["mutation_probes_comparison"][label] = {
            "case_1_appending_list": mut["case_1_appending_list"],
            "case_2_changing_len": mut["case_2_changing_len"],
            "case_3_same_final_length": mut["case_3_same_final_length"],
            "case_4_deceptive_len": mut["case_4_deceptive_len"],
            "case_5_exceeds_during_snapshot": mut["case_5_exceeds_during_snapshot"],
            "case_6_exact_boundaries": mut["case_6_exact_boundaries"],
            "case_7_dataclass_capacity": mut["case_7_dataclass_capacity"],
            "case_7b_dataclass_selection_1000_fields": mut[
                "case_7b_dataclass_selection_1000_fields"
            ],
            "case_8_callback_containment": mut["case_8_callback_containment"],
            "case_9_single_charge_mutation": mut["case_9_single_charge_mutation"],
            "real_store_relation": mut["real_store_relation"],
        }

        st = store_results[label]
        summary["store_case_comparison"][label] = [
            {
                "case_index": i,
                "input_children": c["input_children"],
                "work_limit": c["work_limit"],
                "prior_work": c["prior_work"],
                "remaining_work": c["remaining_work"],
                "selection_work_limit": c["selection_work_limit"],
                "used_work": c["used_work"],
                "refusal_code": c["result"].get("code"),
                "max_queue_length": c["maxima"]["charge_input:queue_length"],
                "policy_calls": c["policy_calls"],
                "rows_after": c["rows_after"],
            }
            for i, c in enumerate(st["cases"])
        ]

        sd = study_results[label]
        summary["study_admission_comparison"][label] = [
            {
                "index": i,
                "shape": c.get("shape"),
                "outcome": c.get("outcome"),
                "used_work": c.get("used_work"),
                "max_queue_length": c.get("maxima", {}).get(
                    "charge_input:queue_length"
                ),
            }
            for i, c in enumerate(sd["admission"])
        ]

    (SCANNER_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("Scanner probe runs complete.")


def main():
    direct_whl, derived_whl = build_and_verify_distribution()
    cohorts = setup_environments(direct_whl, derived_whl)
    run_scanner_probes(cohorts)
    print("All tasks finished successfully.")


if __name__ == "__main__":
    main()
