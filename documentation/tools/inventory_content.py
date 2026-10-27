"""Inspect the explicit file-level documentation ownership inventory.

Run from the repository root with the isolated documentation environment:
    documentation/.venv/bin/python documentation/tools/inventory_content.py
Frozen historical collections are checked against their original Git objects.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "documentation/content-inventory.json"
FROZEN_BASELINE = "5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d"
FROZEN_TREES = {
    "docs/implementation/evidence/": "5900b3783d59104ef86765c5d44847d788b468fa",
    "docs/phase2/reviews/": "0ec5f25e7cd48b7f4dcccec69dc55154b6b030eb",
}


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _manifest() -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(data.get("records"), dict) or not isinstance(
        data.get("frozen"), dict
    ):
        raise ValueError("Malformed ownership inventory")
    if data.get("baseline") != FROZEN_BASELINE or data["frozen"] != FROZEN_TREES:
        raise ValueError("Frozen evidence baseline mismatch")
    return data


def _frozen(data: dict) -> dict[str, dict[str, str]]:
    """Enumerate only exact baseline blob paths and modes; reject added files."""
    entries = {}
    baseline = data["baseline"]
    for directory, expected_tree in data["frozen"].items():
        name = directory.rstrip("/")
        if _git("rev-parse", f"{baseline}:{name}").decode().strip() != expected_tree:
            raise ValueError(f"Frozen tree identity mismatch: {directory}")
        raw = _git("ls-tree", "-rz", baseline, "--", name)
        for item in raw.split(b"\0"):
            if not item:
                continue
            metadata, path = item.split(b"\t", 1)
            mode, kind, blob = metadata.decode().split()
            if kind != "blob":
                raise ValueError(f"Unexpected frozen entry type: {path!r}")
            filename = path.decode()
            entries[filename] = {
                "status": "frozen-historical-evidence",
                "owner": directory,
                "authority": "Historical evidence only; read the referenced record for its exact scope.",
                "source": f"{baseline}:{filename}",
                "producer": "Original recorded review or validation run; retain its bytes.",
                "consumers": "Historical evidence and associated review records.",
                "publication": "not staged",
                "mode": mode,
                "blob": blob,
            }
    return entries


def classify(path: str) -> dict:
    data = _manifest()
    records = data["records"]
    if path in records:
        return records[path]
    frozen = _frozen(data)
    if path in frozen:
        return frozen[path]
    raise ValueError(f"Unclassified path: {path}")


def inventory() -> list[dict]:
    data = _manifest()
    explicit = data["records"]
    frozen = _frozen(data)
    overlap = set(explicit) & set(frozen)
    if overlap:
        raise ValueError(f"Duplicate inventory entries: {sorted(overlap)[:3]}")
    tracked = set(
        filter(
            None,
            _git(
                "ls-files",
                "-z",
                "--",
                "docs",
                "documentation",
                ".agents/skills",
                "AGENTS.md",
                "README.md",
                "scripts/schema_inventory.py",
                "scripts/verification_outputs.py",
                "scripts/check_sqlite_validation_policy.py",
            )
            .decode()
            .split("\0"),
        )
    )
    expected = set(explicit) | set(frozen)
    if tracked != expected:
        raise ValueError(
            f"Unclassified tracked paths: {sorted(tracked - expected)[:5]}; "
            f"stale inventory paths: {sorted(expected - tracked)[:5]}"
        )
    for directory in data["frozen"]:
        # Compare both index and worktree against the baseline, including file
        # modes and bytes. Untracked additions are also refused.
        for index_only in (True, False):
            command = ["git", "diff", "--quiet"]
            if index_only:
                command.append("--cached")
            command.extend([data["baseline"], "--", directory])
            diff = subprocess.run(command, cwd=ROOT)
            if diff.returncode != 0:
                raise ValueError(f"Frozen evidence changed: {directory}")
        if _git("ls-files", "--others", "--exclude-standard", "-z", "--", directory):
            raise ValueError(f"Untracked frozen evidence: {directory}")
    required = {
        "status",
        "owner",
        "authority",
        "source",
        "producer",
        "consumers",
        "publication",
    }
    result = []
    for path in sorted(expected):
        record = explicit.get(path) or frozen[path]
        if not required <= record.keys() or any(not record[key] for key in required):
            raise ValueError(f"Incomplete inventory entry: {path}")
        if record["status"] == "needs_assessment" or any(
            str(record[key]).lower().strip() in {"not assessed", "unknown", "todo"}
            for key in required
        ):
            raise ValueError(f"Unresolved inventory entry: {path}")
        if re.fullmatch(r"docs/adr/\d{4}-[^/]+\.md", path):
            text = (ROOT / path).read_text(encoding="utf-8")
            match = re.search(r"^status:\s*(.+)$", text, re.MULTILINE)
            if match is None:
                match = re.search(
                    r"^-\s*\*\*Status:\*\*\s*(.+)$", text, re.MULTILINE | re.IGNORECASE
                )
            if (
                match is None
                or record.get("status_in_source") != match.group(1).strip()
            ):
                raise ValueError(f"ADR status evidence mismatch: {path}")
        result.append({"path": path, **record})
    return result


def main() -> None:
    print(json.dumps(inventory(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
