"""Verify all Task C payloads and indexed raw members without extraction."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def verify(raw, entry):
    assert len(raw) == entry['bytes']
    assert hashlib.sha256(raw).hexdigest() == entry['sha256']


def main():
    root = Path(__file__).resolve().parent
    payloads = json.loads((root / 'artifact-index.json').read_text())['payloads']
    assert {p.name for p in root.iterdir() if p.is_file()} == set(payloads) | {'artifact-index.json'}
    for name, entry in payloads.items():
        assert Path(name).name == name
        verify((root / name).read_bytes(), entry)
    members = json.loads((root / 'raw-index.json').read_text())['members']
    with zipfile.ZipFile(root / 'raw-evidence.zip') as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) and set(names) == set(members)
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts
            verify(archive.read(name), members[name])
    print(json.dumps({'verified': True, 'payloads': len(payloads), 'raw_members': len(members)}))


if __name__ == '__main__':
    main()
