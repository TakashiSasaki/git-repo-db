# Isolated documentation workspace

Root AGENTS.md and accepted ADRs remain authoritative. ADR0035 was adopted2026-10-26. This project is not a root uv workspace member. Use its
own pyproject.toml, uv.lock and .venv for documentation-only work; never change the
product environment, test selection or checks as a shortcut for documentation.
Use the environment's loaded SQLite; never replace/build/spoof SQLite.

The renderer and documentation tests live in this workspace; neutral schema
inventory and product checks remain outside it. Product changes take precedence;
adapt this workspace to a selected product revision without freezing another
branch. Keep documentation source SHA/tree, selected product SHA/tree and full
neutral IR digest separate. Pin explicit commits, not moving latest HEAD.

Canonical ADRs/contracts/machine evidence stay at their original paths. Never
create an editable second ADR source. Build staging may copy only the
existing explicit publication allowlist from documentation/tools/build_docs_site.py; schema
viewer URL partitioning and dual SVG paths stay unchanged. No new public content,
workflow, deployment or settings are authorized by these instructions. Private build
inputs/provenance belong under .build/, not in published site outputs.

Product-scoped success is distinct from complete local/hosted release acceptance.
The provenance consumer checks consistency, not trusted execution or permission
to publish. The producer records its executed control closure and checks working
bytes before and after execution. The release verifier validates recorded evidence
against committed inputs, artifacts and provider evidence; it does not rerun the
producer. Preview rendering cannot establish full
release acceptance; complete acceptance requires the independent product and
documentation evidence described in README.md.
