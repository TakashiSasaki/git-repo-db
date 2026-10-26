# Isolated documentation preparation

Root AGENTS.md and accepted ADRs remain authoritative. ADR0035 was adopted2026-10-26. This project is not a root uv workspace member. Use its
own pyproject.toml, uv.lock and .venv for documentation-only work; never change the
product environment, test selection or checks as a shortcut for documentation.
Use the environment's loaded SQLite; never replace/build/spoof SQLite.

SEP3 owns renderer/shared-file relocation and coordinated CI cutover. Do not edit schema_viz
or schema_inventory concurrently with SEP1. Product changes take precedence;
adapt this workspace to a selected product revision without freezing another
branch. Keep documentation source SHA/tree, selected product SHA/tree and full
neutral IR digest separate. Pin explicit commits, not moving latest HEAD.

Canonical ADRs/contracts/machine evidence stay at their original paths. Never
create an editable second ADR source. Future build staging may copy only the
existing explicit publication allowlist from scripts/build_docs_site.py; schema
viewer URL partitioning and dual SVG paths stay unchanged. No new public content,
workflow, deployment or settings are authorized by preparation. Private build
inputs/provenance belong under .build/, not in published site outputs.

Product-scoped success is distinct from complete local/hosted release acceptance.
The scaffold checks provenance consistency only, not trusted execution, producer
input completeness, release acceptance or permission to publish.
