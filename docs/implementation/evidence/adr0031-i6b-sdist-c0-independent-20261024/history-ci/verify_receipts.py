"""Independent strict decoder for saved final-155 hosted job-log receipts."""
import base64
import gzip
import hashlib
import io
import json
import pathlib
import re
import sys
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
EXPECTED = {"120597093781": ("40006927076", "9449cf850e69b9922fc8604f308d63f370e9b8df599e60ded74f823ae90a895c", 86002), "120597093978": ("40006927148", "60b73fee0f3fed6d0c220d94a5fb62b450ad18bbb2ff58c662bb3f9bee3b090a", 1993958)}
TREE = "ace7e44cd89194d189a30a0aa6cf513a45b3b87c"
MERGE = "90e222635a01e89f095e9a256ac69ecfc759ec4e"
TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z (CI_RECEIPTS_(?:BEGIN|DATA|END)_V1 .*)$")

def decode(log):
    records = [m.group(1) for l in log.splitlines() if (m := TIMESTAMP.fullmatch(l))]
    assert len(records) >= 3
    begin = re.fullmatch(r"CI_RECEIPTS_BEGIN_V1 ([0-9a-f]{64}) ([0-9]+)", records[0])
    assert begin
    end = re.fullmatch(r"CI_RECEIPTS_END_V1 ([0-9a-f]{64})", records[-1])
    assert end and end[1] == begin[1]
    payload = []
    for line in records[1:-1]:
        match = re.fullmatch(r"CI_RECEIPTS_DATA_V1 ([A-Za-z0-9+/]+={0,2})", line)
        assert match
        payload.append(match[1])
    body = base64.b64decode("".join(payload), validate=True)
    assert len(body) == int(begin[2]) and hashlib.sha256(body).hexdigest() == begin[1]
    # Roundtrip forbids noncanonical trailing bits/padding, beyond validate=True.
    assert base64.b64encode(body).decode() == "".join(payload)
    return body

def main():
    summaries = {}
    for job, (run,digest,length) in EXPECTED.items():
        log = gzip.decompress((HERE / f"raw/job-{job}.log.gz").read_bytes()).decode("utf-8-sig")
        try:
            body = decode(log)
        except (AssertionError, ValueError) as error:
            summaries[run]={"job":job,"status":"FAIL_CLOSED","reason":"current job-log receipt fails declared byte length / SHA256; no missing byte inference","exception_class":type(error).__name__,"declared_bytes":length,"declared_sha256":digest}
            continue
        assert len(body) == length and hashlib.sha256(body).hexdigest() == digest
        (HERE/f"raw/receipt-{run}.zip").write_bytes(body)
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            names=z.namelist()
            assert len(names)==len(set(names))
            assert z.testzip() is None
            for name in names:
                p=pathlib.PurePosixPath(name)
                assert not p.is_absolute() and ".." not in p.parts and "\\" not in name
            index=json.loads(z.read("receipt-index.json"))
            assert set(index)==set(names)-{"receipt-index.json"}
            members={}
            for name,expect in index.items():
                data=z.read(name)
                actual={"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
                assert actual==expect,(name,actual,expect)
                members[name]=actual
            binding=json.loads(z.read("receipt-binding.json"))
            assert binding["head"]==MERGE and binding["tree"]==TREE
            assert str(binding["run_id"])==run and str(binding["run_attempt"])=="1"
            manifests={name:json.loads(z.read(name)) for name in names if name.endswith(("validation-manifest.json","selection.json","coverage.json","runtime.json","python-runtime.json"))}
            summaries[run]={"job":job,"status":"VERIFIED","bytes":len(body),"sha256":digest,"members":members,"binding":binding,"selected_manifests":manifests}
    (HERE/"receipt-results.json").write_text(json.dumps(summaries,indent=2)+"\n")
    print(json.dumps({run:{k:v for k,v in d.items() if k not in ("members","selected_manifests")} for run,d in summaries.items()},indent=2))
    return int(any(row["status"]!="VERIFIED" for row in summaries.values()))

if __name__=="__main__":
    sys.exit(main())
