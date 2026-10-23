"""Exact ordinary-source mapping of independently executed installed cohorts."""

import gzip
import hashlib
import json
from pathlib import Path
import sys


def lines(path):
    values=path.read_text().splitlines()
    assert len(values)==len(set(values))
    return set(values)


def main():
    root=Path(sys.argv[1])
    artifact=Path(sys.argv[2])
    out=Path(sys.argv[3])
    ordinary_path=artifact/"regression/full/ordinary.selected.txt"
    ordinary=lines(ordinary_path)
    result={"reviewed_source":"fee364c6d61a5feebf08dbdd830a5a57ee2d872b",
        "ordinary_source_count":len(ordinary),
        "ordinary_manifest_sha256":hashlib.sha256(ordinary_path.read_bytes()).hexdigest(),
        "separate_unmapped_checks_per_form":{"new_bounded_contract_script":58,"doctor":"separate CLI execution","original_Access_smoke":"separate generated installed smoke, failure retained by distribution"},"forms":{}}
    for form in ("direct","derived"):
        i6=json.loads((out/"reconciliation.json").read_text())["installed-"+form]["nodes"]
        mapped_path=artifact/f"distribution/installed-cohorts/{form}-mapped-source-nodes.txt"
        i4i5=lines(mapped_path)
        executed=set(i6)|i4i5
        assert len(i6)==len(set(i6))
        assert executed<=ordinary
        missing=ordinary-executed
        details={"i6_nodes":len(i6),"i4_i5_nodes":len(i4i5),"overlap":len(set(i6)&i4i5),
            "ordinary_source_union":len(executed),"ordinary_source_unexecuted":len(missing),
            "i4_i5_manifest_sha256":hashlib.sha256(mapped_path.read_bytes()).hexdigest()}
        result["forms"][form]=details
        (out/f"installed-{form}-mapped-source-nodes.txt.gz").write_bytes(gzip.compress(("\n".join(sorted(executed))+"\n").encode(),mtime=0))
        (out/f"installed-{form}-unexecuted-source-nodes.txt.gz").write_bytes(gzip.compress(("\n".join(sorted(missing))+"\n").encode(),mtime=0))
    (out/"installed-scope.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
