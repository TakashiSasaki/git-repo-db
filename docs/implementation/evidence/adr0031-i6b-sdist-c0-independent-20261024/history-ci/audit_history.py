"""Independent read-only Git-object audit. Run from the reviewed checkout."""
import ast
import gzip
import hashlib
import itertools
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
OUT = pathlib.Path(__file__).resolve().parent
TARGET = "fee364c6d61a5feebf08dbdd830a5a57ee2d872b"
HEADS = {"154": "91827360c185cbf813277bf32a6627d894b1b20a", "144": "ededcd83eb2d99a602ba18c8fe3c177125c825ac", "147": "e7762952e18061de8c8235beaeddf42f20ad9f5a", "150": "4fc00b1fbc57f10f6c0c6352dee702e1738f65b7"}

def command(*args, allowed=(0,)):
    p = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode not in allowed:
        raise RuntimeError((args, p.returncode, p.stderr.decode()))
    return p

def git(*args):
    return command("git", *args).stdout

def text(*args):
    return git(*args).decode().strip()

def inventory(ref, *paths):
    return {line.split("\t", 1)[1]: line.split()[2] for line in git("ls-tree", "-r", ref, "--", *paths).decode().splitlines()}

def digest(ref, path):
    data = git("show", ref + ":" + path)
    return {"blob": text("rev-parse", ref + ":" + path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def main():
    result = {"target": TARGET, "tree": text("rev-parse", TARGET + "^{tree}"), "main": text("rev-parse", "origin/main"), "heads": HEADS}
    result["ancestry"] = {n: command("git", "merge-base", "--is-ancestor", h, TARGET, allowed=(0, 1)).returncode == 0 for n, h in HEADS.items()}
    assert result["ancestry"] == {"154": True, "144": True, "147": True, "150": False}
    result["merge_bases"] = {a+"-"+b: text("merge-base", HEADS[a], HEADS[b]) for a,b in itertools.combinations(("154", "144", "147"), 2)}
    changed = {n: set(git("diff", "--name-only", result["merge_bases"]["154-144"], HEADS[n]).decode().splitlines()) for n in ("154", "144", "147")}
    shared = sorted(set.union(*(changed[a] & changed[b] for a,b in itertools.combinations(changed, 2))))
    result["shared_paths"] = {p: {n: digest(h,p) for n,h in {**HEADS, "target": TARGET}.items()} for p in shared}
    assert len(shared) == 6
    merges = [(HEADS["154"],HEADS["147"],"9c3de77475d042bb5e8c465a64e5f4b47d2eda23"), ("9c3de77475d042bb5e8c465a64e5f4b47d2eda23",HEADS["144"],"9f005eb2dbd97a5c160872740794143a2bd560f7")]
    result["integration_merges"] = []
    for i,(left,right,actual) in enumerate(merges):
        p = command("git", "merge-tree", "--write-tree", left, right, allowed=(0,1))
        (OUT / f"raw/merge-tree-{i}.txt").write_bytes(p.stdout)
        actual_parents = text("show", "-s", "--format=%P", actual).split()
        assert actual_parents == [left,right]
        result["integration_merges"].append({"left":left,"right":right,"actual":actual,"parents":actual_parents,"tree":text("rev-parse",actual+"^{tree}"),"automatic_exit":p.returncode,"automatic_tree":p.stdout.decode().splitlines()[0]})
    assert result["integration_merges"][0]["automatic_exit"] == 0
    assert result["integration_merges"][0]["automatic_tree"] == result["integration_merges"][0]["tree"]
    result["two_conflict_resolution_diff"] = "raw/conflict-resolution.patch.gz"
    (OUT / result["two_conflict_resolution_diff"]).write_bytes(gzip.compress(git("show", "--format=fuller", "--cc", merges[1][2]),mtime=0))
    # Independently compare auto-merged, non-conflict shared blobs at the merge.
    auto = result["integration_merges"][1]["automatic_tree"]
    conflicts = [".agents/skills/ci-final-tree-verification/SKILL.md", "tests/packaging/test_p1_distribution.py"]
    result["exact_conflict_unions"] = {}
    for path in conflicts:
        marked = git("show",auto+":"+path).decode()
        union = "".join(line for line in marked.splitlines(keepends=True) if not line.startswith(("<<<<<<< ", "=======", ">>>>>>> ")))
        result["exact_conflict_unions"][path] = union.encode() == git("show",merges[1][2]+":"+path)
    assert all(result["exact_conflict_unions"].values())
    result["automatic_shared_paths_preserved"] = {p:text("rev-parse",auto+":"+p)==text("rev-parse",merges[1][2]+":"+p) for p in shared if p not in conflicts}
    assert all(result["automatic_shared_paths_preserved"].values())
    source = git("show",TARGET+":tests/packaging/test_p1_distribution.py").decode()
    imports = {a.name for node in ast.walk(ast.parse(source)) if isinstance(node,ast.ImportFrom) for a in node.names}
    assert {"stage_support","check_sdist","compare_wheels","save"} <= imports
    result["import_union"] = sorted(imports)
    skill_path = ".agents/skills/ci-final-tree-verification/SKILL.md"
    skill = git("show",TARGET+":"+skill_path).decode()
    result["skill_sections"] = {s:s in skill for s in ["## Stage installed test support separately and bind pytest imports", "## Inspect actual sdist members after positive selection", "## Pytest subtest reports are additional measured phases"]}
    assert all(result["skill_sections"].values())
    result["product_inventory"] = {p:digest(TARGET,p) for p in inventory(TARGET,"src")}
    assert inventory(HEADS["154"],"src") == inventory(TARGET,"src")
    result["all_product_blobs_equal154"] = True
    ddl=git("show",TARGET+":src/repo_catalog/adapters/sqlite/p1_ddl/context.sql").decode()
    result["exact_transfer_fences"] = {}
    for name in ("i2_transfer_stage_fence", "i2_transfer_report_stage_fence"):
        start=ddl.index("CREATE TRIGGER "+name)
        fence=ddl[start:ddl.index(" END;",start)+5]
        assert "RAISE(ABORT,'I2_TRANSFER_UNSUPPORTED')" in fence
        result["exact_transfer_fences"][name]={"text":fence,"bytes":len(fence.encode()),"sha256":hashlib.sha256(fence.encode()).hexdigest()}
    expected = {"144": ["scripts/check_sdist_contract.py","scripts/ci_plan.py","scripts/ci_execute.py","scripts/ci_dependencies.json"], "147": ["scripts/emit_ci_evidence.py","tests/unit/test_emit_ci_evidence.py"]}
    result["authority_preservation"] = {n:{p:digest(HEADS[n],p)==digest(TARGET,p) for p in paths} for n,paths in expected.items()}
    assert all(all(x.values()) for x in result["authority_preservation"].values())
    old = inventory(HEADS["154"],"docs/adr")
    accepted = {p:h for p,h in old.items() if p.split('/')[-1][:4].isdigit() and b"status: accepted" in git("show",HEADS["154"]+":"+p)[:200]}
    result["all_numbered_adrs_equal154"] = {p:h == inventory(TARGET,"docs/adr").get(p) for p,h in old.items() if p.split('/')[-1][:4].isdigit()}
    assert all(result["all_numbered_adrs_equal154"].values())
    result["accepted_adrs_equal154"] = {p:h == inventory(TARGET,"docs/adr").get(p) for p,h in accepted.items()}
    assert all(result["accepted_adrs_equal154"].values())
    result["adr0033_equal144"] = digest(HEADS["144"],"docs/adr/0033-minimal-product-sdist.md") == digest(TARGET,"docs/adr/0033-minimal-product-sdist.md")
    assert result["adr0033_equal144"]
    # Preserve all pre-existing evidence under each integrated head, not just named reports.
    result["historical_evidence"] = {}
    for n in ("154","144","147"):
        before=inventory(HEADS[n],"docs/implementation/evidence")
        after=inventory(TARGET,"docs/implementation/evidence")
        delta=[p for p,h in before.items() if after.get(p)!=h]
        result["historical_evidence"][n]={"files":len(before),"changed_or_missing":delta}
        assert not delta
    tested="fb5d7b5a0c4b92c8a282daac154e66fa6d361e64"
    inputs=inventory(tested,"src","tests","scripts",".github","pyproject.toml","uv.lock","README.md",".gitignore")
    final=inventory(TARGET)
    result["tested_input_binding"]={"tested_head":tested,"files":len(inputs),"changed_or_missing":[p for p,h in inputs.items() if final.get(p)!=h],"new_paths":[p for p in final if p not in inputs and (p.startswith(("src/","tests/","scripts/",".github/")) or p in ("pyproject.toml","uv.lock","README.md",".gitignore"))]}
    assert not result["tested_input_binding"]["changed_or_missing"] and not result["tested_input_binding"]["new_paths"]
    merge=text("rev-parse","refs/review155/merge")
    result["github_test_merge"]={"head":merge,"parents":text("show","-s","--format=%P",merge).split(),"tree":text("rev-parse",merge+"^{tree}")}
    assert result["github_test_merge"]["parents"]==[HEADS["154"],TARGET]
    assert result["github_test_merge"]["tree"]==result["tree"]
    directory="docs/implementation/evidence/adr0031-i6b-sdist-c0-integration-20261024/"
    index_bytes=git("show",TARGET+":"+directory+"ARTIFACTS.json")
    index=json.loads(index_bytes)
    mismatches=[]
    for path,expected in index["files"].items():
        data=git("show",TARGET+":"+directory+path)
        actual={"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        if actual!=expected:mismatches.append({"path":path,"expected":expected,"actual":actual})
    result["published_author_index"]={"entries":len(index["files"]),"index_sha256":hashlib.sha256(index_bytes).hexdigest(),"mismatches":mismatches}
    assert not mismatches
    (OUT/"history-results.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("shared_paths","product_inventory","accepted_adrs_equal154")},indent=2))

if __name__=="__main__":
    main()
