"""Index and independently verify every published review payload and ZIP member."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
INDEX = HERE / "ARTIFACTS.json"
SOURCE = "fee364c6d61a5feebf08dbdd830a5a57ee2d872b"


def inventory():
    result = []
    for path in sorted(HERE.rglob("*")):
        if (
            not path.is_file()
            or path == INDEX
            or "__pycache__" in path.parts
            or path.suffix == ".pyc"
        ):
            continue
        assert not path.is_symlink()
        data = path.read_bytes()
        result.append(
            dict(
                path=path.relative_to(HERE).as_posix(),
                bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-index", action="store_true")
    args = parser.parse_args()
    rows = inventory()
    if args.write_index:
        INDEX.write_text(
            json.dumps(
                dict(
                    format="independent-review-index-v1",
                    reviewed_head=SOURCE,
                    reviewed_tree="ace7e44cd89194d189a30a0aa6cf513a45b3b87c",
                    payloads=rows,
                ),
                indent=2,
            )
            + "\n"
        )
    saved = json.loads(INDEX.read_text())
    assert saved["payloads"] == rows
    zipped_members = 0
    for row in rows:
        path = HERE / row["path"]
        if path.suffix != ".zip":
            continue
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert len(names) == len(set(names))
            for name in names:
                assert not name.startswith("/") and ".." not in Path(name).parts
                archive.read(name)
            zipped_members += len(names)
    changes = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            SOURCE,
            "--",
            ".",
            ":(exclude)" + HERE.relative_to(ROOT).as_posix(),
        ],
        cwd=ROOT,
        text=True,
    )
    assert not changes, changes
    finding = json.loads((HERE / "findings.json").read_text())
    assert finding["verdict"] == "FAIL"
    for item in finding["findings"]:
        for name in item["evidence"]:
            assert (HERE / name).is_file(), name
    print(
        json.dumps(
            dict(
                verified=True,
                payloads=len(rows),
                bytes=sum(row["bytes"] for row in rows),
                zipped_members_read=zipped_members,
                artifact_index_sha256=hashlib.sha256(INDEX.read_bytes()).hexdigest(),
                changes_outside_new_review_directory=0,
            )
        )
    )


if __name__ == "__main__":
    main()
