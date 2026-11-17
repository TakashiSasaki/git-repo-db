"""Check product working bytes before loading any executable product controls."""

from __future__ import annotations

import ast
import hashlib
import stat
import subprocess
from pathlib import Path


def verify_checkout(root: Path, commit: str) -> None:
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root)

    if git("rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("Product checkout does not match selected commit")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Product checkout has uncommitted inputs")
    control_source = ast.parse(git("show", commit + ":scripts/schema_inventory.py"))
    declaration = next(
        n.value
        for n in control_source.body
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "PRODUCER_CONTROLS" for t in n.targets
        )
    )
    if (
        not isinstance(declaration, ast.Call)
        or not isinstance(declaration.func, ast.Name)
        or declaration.func.id != "frozenset"
        or len(declaration.args) != 1
    ):
        raise ValueError("Unsupported product control declaration")
    controls = ast.literal_eval(declaration.args[0])
    tree = {}
    for entry in git("ls-tree", "-rz", commit).split(b"\0"):
        if entry:
            metadata, name = entry.split(b"\t", 1)
            tree[name.decode()] = metadata.decode().split()
    if not set(controls).issubset(tree):
        raise ValueError("Missing committed producer controls")
    selected = {
        p
        for p in tree
        if p.startswith(("src/", "packages/"))
        or p.startswith("scripts/")
        or p in controls
    }
    # Compare raw bytes, not git-diff output: index flags must not conceal drift.
    for name in selected:
        path = root / name
        mode, kind, oid = tree[name]
        if (
            kind != "blob"
            or mode not in {"100644", "100755"}
            or any(p.is_symlink() for p in (path, *path.parents))
        ):
            raise ValueError("Unsafe product input: " + name)
        metadata = path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or bool(metadata.st_mode & 0o111) != (mode == "100755")
        ):
            raise ValueError("Aliased or modified product input mode: " + name)
        raw = path.read_bytes()
        blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if blob != oid:
            raise ValueError(
                "Product executable/input differs from selected commit: " + name
            )
