"""Inventory tracked documentation by one role and owning location.

Run from the repository root: documentation/.venv/bin/python documentation/tools/inventory_content.py > inventory.json
The index includes staged paths; historical bytes are never read or changed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Explicit root-level exceptions have dependencies outside the documentation
# renderer or are preserved historical navigation. Never silently relocate them.
ROOT_GUIDES = {
    "application-json-contracts.md",
    "change-aware-ci.md",
    "ci-python-runtime.md",
    "latest-state-transport.md",
    "local-python.md",
    "operations.md",
    "repository-identity.md",
    "testing.md",
}
ROOT_POINTERS = {"current-runtime-reference.md"}
ROOT_RECORDS = {
    "architecture.md",
    "ci-performance-baseline.json",
    "ci-performance-results.json",
    "ci-performance.md",
    "ci-selection-results.json",
    "cli.md",
    "current-state-boundaries-inventory.json",
    "current-state-boundaries.md",
    "current-state-schema-closure.md",
    "current-state-schema-inventory.json",
    "current-state-schema-inventory.md",
    "current-state-schema-liveness.md",
    "data-model.md",
    "developer-site.md",
    "implementation-status.md",
    "latest-state-table-inventory.json",
    "latest-state-table-inventory.md",
    "latest-state-transport-implementation.md",
    "model-contract-completion.md",
    "model-integration-audit.md",
    "model-integration-handoff.md",
    "model-integration-status.md",
    "multi-provider-design-analysis.md",
    "phase1-api-original-retirement-implementation.md",
    "phase1-api-original-retirement-inventory.json",
    "phase1-api-original-retirement.md",
    "test-suite-efficiency.md",
    "transport-independent-core-adr.md",
    "transport-independent-core-implementation.md",
}
ROOT_CONTROL = {
    "AGENTS.md",
    "README.md",
    "scripts/schema_inventory.py",
    "scripts/verification_outputs.py",
    "scripts/check_sqlite_validation_policy.py",
}


def classify(path: str) -> tuple[str, str]:
    """Exactly one storage role; authority is established by contents/ADRs."""
    parts = path.split("/")
    if path in ROOT_CONTROL:
        return "repository-control-file", path
    if path.startswith(".agents/skills/"):
        return "agent-procedure", ".agents/skills/"
    if path.startswith("docs/"):
        if len(parts) == 2 and parts[1] == "README.md":
            return "directory-instructions", "docs/"
        if len(parts) == 2:
            if parts[1] in ROOT_GUIDES:
                return "protected-product-guidance", "docs/"
            if parts[1] in ROOT_POINTERS:
                return "historical-link-pointer", "docs/"
            if parts[1] in ROOT_RECORDS:
                if path.endswith((".json", ".sql", ".json.gz")):
                    return "machine-structured-artifact", "docs/"
                return "retained-engineering-record", "docs/"
            raise ValueError(f"Unclassified docs root: {path}")
        section = parts[1]
        if section == "adr":
            return "canonical-adr-and-governance", "docs/adr/"
        if section == "architecture":
            return "canonical-architecture-source", "docs/architecture/"
        if section in {"validation", "integration", "schema-hardening"}:
            if section == "schema-hardening" and path.endswith((".json", ".sql")):
                return "machine-structured-artifact", f"docs/{section}/"
            return "retained-engineering-record", f"docs/{section}/"
        if section in {"implementation", "phase2"}:
            if (section == "implementation" and parts[2] == "evidence") or (
                section == "phase2" and parts[2] == "reviews"
            ):
                return "historical-evidence", f"docs/{section}/{parts[2]}/"
            if parts[-1] == "AGENTS.md":
                return "directory-instructions", f"docs/{section}/"
            if path.endswith((".json", ".sql", ".json.gz")):
                return "machine-structured-artifact", f"docs/{section}/"
            return "retained-engineering-record", f"docs/{section}/"
        raise ValueError(f"Unclassified docs directory: {path}")
    if path.startswith("documentation/"):
        if len(parts) == 2:
            if parts[1] == "current-runtime-reference.md":
                return "derived-current-guide", "documentation/"
            if parts[1] in {"AGENTS.md", "README.md"}:
                return "directory-instructions", "documentation/"
            if parts[1] in {".gitignore", "mkdocs.yml", "pyproject.toml", "uv.lock"}:
                return "documentation-build-config", "documentation/"
            raise ValueError(f"Unclassified documentation root: {path}")
        section = parts[1]
        if section == "content":
            if path.endswith(".md"):
                return "published-prose-source", "documentation/content/"
            return "published-site-asset", "documentation/content/"
        if section == "schema":
            if parts[-1] == "README.md":
                return "derived-current-guide", "documentation/schema/"
            return "generated-schema-presentation", "documentation/schema/"
        if section == "overrides":
            return "documentation-template", "documentation/overrides/"
        if section == "tools":
            return "documentation-tool", "documentation/tools/"
        if section == "tests":
            return "documentation-test", "documentation/tests/"
        raise ValueError(f"Unclassified documentation directory: {path}")
    raise ValueError(f"Unclassified scope: {path}")


def inventory() -> list[dict[str, str]]:
    paths = (
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "-z",
                "--",
                "docs",
                "documentation",
                ".agents/skills",
                *sorted(ROOT_CONTROL),
            ],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    result = []
    for path in filter(None, paths):
        role, owner = classify(path)
        result.append({"path": path, "role": role, "owner": owner})
    return result


def main() -> None:
    print(json.dumps(inventory(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
