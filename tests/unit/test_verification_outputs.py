"""Disposable sentinels for every private-output publication primitive."""

import os

import pytest

from scripts.verification_outputs import (
    private_attempt,
    private_log,
    write_private,
    write_private_json,
)


@pytest.mark.parametrize(
    "attack", ["leaf-link", "parent-link", "hardlink", "catalog", "source-overlap"]
)
def test_private_outputs_refuse_unsafe_targets_without_overwriting(tmp_path, attack):
    root = tmp_path / "repository"
    root.mkdir()
    outside = tmp_path / "product-state"
    outside.write_bytes(b"unchanged product sentinel")
    parent = root / "documentation/.build/inputs"
    parent.mkdir(parents=True)
    target = parent / "documentation-inputs.json"
    if attack == "leaf-link":
        target.symlink_to(outside)
    elif attack == "parent-link":
        target = parent / "linked/metadata.json"
        directory = tmp_path / "outside"
        directory.mkdir()
        (parent / "linked").symlink_to(directory, target_is_directory=True)
    elif attack == "hardlink":
        os.link(outside, target)
    elif attack == "catalog":
        target.write_bytes(b"SQLite format 3\x00" + b"catalog sentinel")
    else:
        target = root / "source.json"
        target.write_bytes(b"unchanged source")
    before = target.read_bytes() if target.is_file() else None
    with pytest.raises((ValueError, OSError)):
        write_private_json(root, target, {"new": "metadata"})
    assert outside.read_bytes() == b"unchanged product sentinel"
    if before is not None:
        assert target.read_bytes() == before


def test_attempts_are_unique_and_log_copy_receipt_writes_are_confined(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    a, b = private_attempt(root), private_attempt(root)
    assert a != b
    with private_log(root, a / "command.log") as log:
        log.write("actual command output")
    write_private(root, a / "inventory.json", b'{"complete":"inventory"}')
    write_private_json(root, a / "receipt.json", {"status": "passed"})
    assert (a / "command.log").read_text() == "actual command output"
    outside = tmp_path / "outside"
    outside.write_text("retain")
    (b / "command.log").symlink_to(outside)
    with pytest.raises((ValueError, OSError)):
        with private_log(root, b / "command.log") as stream:
            stream.write("overwrite")
    assert outside.read_text() == "retain"
