"""Independent exact-boundary archive controls with disposable source trees."""

import argparse
import copy
import gzip
import importlib.util
import io
import json
import shutil
import tarfile
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    spec=importlib.util.spec_from_file_location("checker",a.root/"scripts/check_sdist_contract.py");c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
    a.out.mkdir(parents=True,exist_ok=True)
    good=next((a.out.parent/"run1/direct").glob("*.tar.gz")).read_bytes()
    raw=gzip.decompress(good)
    source=a.out.parent/"run1/backend-only-source"
    rows=[]
    def check(name,data,tree,accept):
        path=a.out/(name+".tar.gz");path.write_bytes(data)
        try:
            receipt=c.check_sdist(path,tree);error=None
        except ValueError as e:
            receipt=None;error=str(e)
        rows.append({"name":name,"expected_accept":accept,"accepted":error is None,"error":error,"compressed_bytes":len(data),"receipt":{k:receipt[k] for k in ("member_count","unpacked_bytes","tar_stream_bytes")} if receipt else None})
        assert (error is None)==accept
    # Real optional gzip FNAME padding changes compressed input size without
    # changing its archive. This is not a fabricated archive-length measurement.
    assert good[3]==0
    for size,accept in ((2097152,True),(2097153,False)):
        data=good[:3]+b"\x08"+good[4:10]+b"n"*(size-len(good)-1)+b"\0"+good[10:]
        assert len(data)==size
        check("compressed-"+str(size),data,source,accept)
    for size,accept in ((c.MAX_TAR_STREAM,True),(c.MAX_TAR_STREAM+512,False)):
        data=gzip.compress(raw+b"\0"*(size-len(raw)))
        check("tar-stream-"+str(size),data,source,accept)
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:
        original=[(i,t.extractfile(i).read()) for i in t.getmembers()]
    def archive(items):
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode="w",format=tarfile.USTAR_FORMAT) as t:
            for i,data in items:
                t.addfile(i,io.BytesIO(data))
        return gzip.compress(stream.getvalue())
    for size,accept in ((8388608,True),(8388609,False)):
        target=a.out/("regular-source-"+str(size));shutil.copytree(source,target)
        delta=size-sum(len(data) for _,data in original)
        items=[]
        for i,data in original:
            i=copy.copy(i)
            if i.name.endswith("/README.md"):
                data+=b"x"*delta;i.size=len(data);(target/"README.md").write_bytes(data)
            items.append((i,data))
        check("regular-"+str(size),archive(items),target,accept)
    for count,accept in ((512,True),(513,False)):
        target=a.out/("member-source-"+str(count));shutil.copytree(source,target)
        items=list(original)
        for n in range(count-len(items)):
            name="src/repo_catalog/review_bound_"+str(n)+".py"
            (target/name).write_bytes(b"")
            i=tarfile.TarInfo("repo_catalog-0.2.0/"+name);i.size=0;items.append((i,b""))
        check("members-"+str(count),archive(items),target,accept)
    (a.out/"results.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    print(json.dumps(rows))


if __name__=="__main__":main()
