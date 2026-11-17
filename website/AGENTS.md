# Isolated documentation workspace

[Root AGENTS.md](../AGENTS.md) and accepted ADRs remain authoritative, including
the current development-phase guidance. ADR 0035 was adopted 2026-10-26. This project is not a root uv workspace member. For Python documentation tooling, use its
own pyproject.toml, uv.lock and .venv; never change the
product environment, test selection or checks as a shortcut for documentation.
Use the environment's loaded SQLite; never replace/build/spoof SQLite.

The semantic explorer also has a Node/Vite authoring entry at repository-root
`index.html` and `package.json`; its sources are under `website/web/`.
Follow [the frontend instructions](web/AGENTS.md) for that scope. The frontend
uses one `app.js` renderer, `style.css`, and cited semantic model for both the
Vite entry and the MkDocs `/design/semantic/` page. Update those shared sources
instead of maintaining a second UI in a generated page. `npm run build` checks
the standalone frontend; the existing Python/MkDocs pipeline stages and builds
the complete site. Website-only work does not require product runtime tests
unless it changes product behavior or inputs.

The renderer and documentation tests live in this workspace; neutral schema
inventory and product checks remain outside it. Product changes take precedence;
adapt this workspace to a selected product revision without freezing another
branch. Keep documentation source SHA/tree, selected product SHA/tree and full
neutral IR digest separate. Use one prepared snapshot within an attempt; main may advance independently.
Source IDs are automatic diagnostic records, not maintained pins or a promise
that every handwritten explanation reflects the recorded product commit.

Canonical ADRs/contracts/machine evidence stay on main. Read them through the external snapshot prepared from main for this attempt. Never
create an editable second ADR source. Build staging may copy only the
explicit publication allowlist from website/tools/build_docs_site.py
and website/tools/adr_publication.py; schema
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

Audience: public readers explore accepted design responsibilities, relations,
semantic keys and constraints. Repository contributors use the CLI and development
guides; reviewers need dated evidence and exact revisions. The published homepage and architecture pages are entry points, not
canonical replacements for source code or accepted ADRs. The repository's
`docs/current-runtime-reference.md` on main navigates current CLI/data-model/status
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

Use [documentation-content-refresh](https://github.com/TakashiSasaki/resource-atlas/blob/main/.agents/skills/documentation-content-refresh/SKILL.md)
for the bounded procedure: prepare main once and record actual inputs, inventory
claims and unknowns, map them to code and ADRs, update derived explanations and
navigation, preserve dates/provenance and historical evidence, test within the
independent documentation workspace, then obtain independent review. Documentation
may lag product without blocking it; a known false statement is a correction,
not a demand for synchronous publication. A build's product/IR provenance does
not establish semantic verification of all handwritten text.

Main owns the product inventory and frozen-evidence checks; web tracks only website sources. Consult
[main records](https://github.com/TakashiSasaki/resource-atlas/blob/main/docs/README.md) for role meanings and explicit placement
exceptions. Keep the tracked web tree below 1,000 files and update the branch-specific source/test manifest when adding files.

The separate five-store projection in `content/design/model.json` is derived
presentation, never accepted physical DDL or the product neutral IR. Pin its
canonical design revision/tree, cite individual facts and preserve A/I/P/U scope.
Keep same-named entities qualified by model/store/name and semantic relationships
distinct from enforced SQLite FKs. Public ADR staging follows the explicit current
selection and copies canonical bodies read-only with applicability from the index.
