"""Verify published Task A payloads and raw ZIP members without extraction."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def check(raw, entry):
    assert len(raw) == entry["bytes"]
    assert digest(raw) == entry["sha256"]


def main():
    root = Path(__file__).resolve().parent
    index = json.loads((root / "artifact-index.json").read_text())
    expected = set(index["payloads"]) | {"artifact-index.json"}
    assert {p.name for p in root.iterdir() if p.is_file()} == expected
    for name, entry in index["payloads"].items():
        assert Path(name).name == name
        check((root / name).read_bytes(), entry)
    raw_index = json.loads((root / "raw-index.json").read_text())
    with zipfile.ZipFile(root / "raw-evidence.zip") as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert set(names) == set(raw_index["members"])
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and ".." not in path.parts
            check(archive.read(name), raw_index["members"][name])
    print(json.dumps({"payloads": len(index["payloads"]),
                      "raw_members": len(raw_index["members"]), "verified": True}))


if __name__ == "__main__":
    main()
