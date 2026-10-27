# Independent documentation workspace — SEP3 cutover

This project provides isolated dependencies, output paths and mechanical
input-provenance checks. Rendering, human sources and documentation tests now live here; product structural tests and canonical design/evidence remain outside. ADR 0035 was adopted 2026-10-26; publication/deployment remain separately authorized.
The existing explicit staging/publication allowlist and rendering conventions in
`documentation/tools/build_docs_site.py` remain the only implementation; no duplicate MkDocs
configuration, renderer or editable ADR source is introduced here.

For the documented product-to-documentation workflow, first establish the
verified product interpreter from the repository root, then create the separate
documentation environment using that interpreter:

```sh
./scripts/setup-local-python.sh
env -u UV_PROJECT_ENVIRONMENT uv sync --locked --project documentation --python .venv/bin/python
```

This creates `documentation/.venv` separately; it does not install rendering
dependencies into the product environment. For documentation-only work without
product validation, the independently selected environment Python may instead
be supplied explicitly. From the `documentation/` directory:

```sh
uv sync --locked --python /path/to/environment/python
.venv/bin/python -m pytest -q
.venv/bin/ruff check tools tests
.venv/bin/ruff format --check tools tests
```

The nested uv project is not a root workspace member. Its environment is `.venv/`,
inputs/staging/provenance belong under `.build/`, and rendered output is
`site/`. These paths are documentation-local and ignored; no shared output is
removed or overwritten. The lock pins documentation dependencies independently;
Documentation-only dependencies are separate from the product environment;
release obligations remain in force.

Documentation verification also requires Node.js (the hosted workflow uses Node
22). Its pytest suite runs the six PWA icon safety tests through Node's test
runner; a missing Node executable or a failed test fails verification. From the
`documentation/` directory, run them directly with
`node --test tests/test_generate_pwa_icons.mjs` for a separate direct run; it is already included in the full documentation pytest suite.
From that same directory, the optional generator is `node tools/generate_pwa_icons.js`; it
requires Puppeteer and a compatible browser in the local environment. Those are
not needed for the stubbed safety tests and are not product dependencies.

## Provenance scaffold

`tools/provenance.py` accepts an externally produced complete neutral IR and a
producer manifest. The manifest must contain schema_version1, exact selected
product commit/tree, IR SHA256 and a nonempty map of repository-relative input
paths to SHA256 hashes. Documentation source commit/tree are separate explicit
arguments. It verifies committed Git blob hashes, selected tree and IR digest,
then creates an in-memory documentation input record; CLI output is private build
metadata, never a public staging source. Example:

```sh
.venv/bin/python tools/provenance.py \
  --repository .. --documentation-source FULL_DOC_COMMIT_SHA \
  --product-source FULL_PRODUCT_COMMIT_SHA \
  --producer-manifest .build/inputs/producer.json --ir .build/inputs/inventory.json \
  > .build/input-provenance.json
```

Both source arguments must be explicit full commit IDs. Input blob lookup reads
that revision, not current checkout contents. No schema producer is run by this
consumer; producer execution uses the separately verified product environment.
The scaffold rejects missing/malformed evidence, path traversal, symlink inputs,
changed input/IR hashes and mismatched selected product identity. It checks
consistency only: a self-consistent fabricated IR/manifest is not an independent
execution proof, and a manifest's input map is not proof of input completeness.
The producer records the executed Python closure and checks working bytes before
and after execution against a conservative input inventory. The release verifier
validates the recorded evidence against committed inputs, artifacts and provider
evidence; it does not rerun the producer. Independent local and hosted documentation evidence and product
validation remain required before any complete-release claim. A consistency
record alone never establishes full acceptance.

## Selected product producer and rendering

In a clean, committed selected product checkout, use its verified product environment:

```sh
scripts/local-run.sh python scripts/schema_inventory.py --source FULL_PRODUCT_SHA --output documentation/.build/inputs
uv run --project documentation --no-sync python documentation/tools/schema_viz.py --ir documentation/.build/inputs/inventory.json --check
uv run --project documentation --no-sync python documentation/tools/build_docs_site.py --product-source FULL_PRODUCT_SHA --documentation-source FULL_DOC_SHA --no-mermaid
```

Choose both full SHAs once; do not chase latest HEAD. A different selected product checkout may export its manifest/IR for the documentation checkout to consume. Product CI does not render documentation. Existing Pages owns documentation checks/preview and the unchanged publication allowlist. Product receipts explicitly report `full_acceptance=false` and missing documentation. `verify_documentation.py` executes all documentation obligations and retains private receipts in unique attempt directories; `--preview` receipts cannot establish complete release acceptance. After producing the pinned IR, the repository-root preview command is `documentation/.venv/bin/python documentation/tools/verify_documentation.py --product-source FULL_PRODUCT_SHA --documentation-source FULL_DOC_SHA --preview`. An explicit `scripts/ci_execute.py reconcile-release --documentation-local RECEIPT --documentation-hosted RECEIPT` additionally verifies independent local/hosted documentation receipts, exact node replacements and product/IR provenance, and binds hosted bytes to the successful Pages provider artifact before complete release acceptance is possible. This is a release gap, never product failure or complete acceptance.

## Content ownership and directory inventory

Use [agent instructions](AGENTS.md#content-structure-and-refresh) and the
[canonical records map](../docs/README.md) before editing or moving material.
`docs/` retains ADRs, contracts, machine inputs and historical evidence;
`documentation/` owns derived human guides, site sources, generated schema
presentations, isolated build tools and tests. Source/IR provenance is distinct
from handwritten content review. Untracked `.build/`, `.venv/` and `site/`
are private/generated outputs, not new authority or a publication allowlist.

Run `documentation/.venv/bin/python documentation/tools/inventory_content.py`
to list each tracked file in these directories and relevant root controls with
one role and owning location. It fails on any unregistered tracked path, including nested files, and checks
the two frozen evidence trees against pinned paths, modes and blobs. The checked-in
file-level inventory records status, authority, provenance, consumers and
publication intent; its bounded static reference scan does not prove the absence
of dynamic consumers. Accepted decisions and each record still determine scope.
