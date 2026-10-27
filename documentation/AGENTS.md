# Isolated documentation workspace

[Root AGENTS.md](../AGENTS.md) and accepted ADRs remain authoritative, including
the current development-phase guidance. ADR 0035 was adopted 2026-10-26. This project is not a root uv workspace member. Use its
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

## Content structure and refresh

Audience: operators need current CLI and data behavior; contributors need source,
contracts, validation and boundaries; reviewers need dated evidence and exact
revisions. The published homepage and architecture pages are entry points, not
canonical replacements for source code or accepted ADRs. The repository's
`documentation/current-runtime-reference.md` navigates current CLI/data-model/status
and explicitly points to the older Schema 20 and audit snapshots. This maintained
guide is repository-only; it is not staged as a site page under the current
publication allowlist. Preserve their
original historical bodies and receipts; add navigation outside the evidence.

Every refresh distinguishes (1) actual normal runtime and activation, (2)
implemented opt-in surfaces, (3) accepted target design and outstanding work,
and (4) dated historical evidence. Link source code for implementation and the
ADR index/accepted ADRs for decisions; don't convert a proposed target to a
runtime claim or treat four P1 factories as the total architecture. Existing
site allowlist alone decides published inputs. External links to exact canonical
source revisions do not publish additional repository files.

Use [documentation-content-refresh](../.agents/skills/documentation-content-refresh/SKILL.md)
for the bounded procedure: pin product and documentation sources, inventory
claims and unknowns, map them to code and ADRs, update derived explanations and
navigation, preserve dates/provenance and historical evidence, test within the
independent documentation workspace, then obtain independent review. Documentation
may lag product without blocking it; a known false statement is a correction,
not a demand for synchronous publication. A build's product/IR provenance does
not establish semantic verification of all handwritten text.

The inventory tool enumerates each tracked file in `docs/`, `documentation/`,
relevant repository entry points and repository skills. Consult
[docs/README.md](../docs/README.md) for role meanings and explicit placement
exceptions. Every new nested or root path must have an explicit file-level
classification before completion; the ownership test refuses unknown paths.
