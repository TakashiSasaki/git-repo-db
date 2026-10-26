# Independent documentation workspace — SEP2 preparation

This additive project prepares isolated dependencies, output paths and mechanical
input-provenance checks. Existing rendering, source files, tests and CI remain in
place. ADR0035 is proposed; no adoption, cutover, publication or deployment occurs.
The existing explicit staging/publication allowlist and rendering conventions in
`scripts/build_docs_site.py` remain the only implementation; no duplicate MkDocs
configuration, renderer or editable ADR source is introduced here.

From this directory, use the same available Python selected for this environment:

```sh
uv sync --locked --python /path/to/environment/python
.venv/bin/python -m pytest -q
.venv/bin/ruff check tools tests
.venv/bin/ruff format --check tools tests
```

The nested uv project is not a root workspace member. Its environment is `.venv/`,
inputs/staging/provenance belong under `.build/`, and future rendered output is
`site/`. These paths are documentation-local and ignored; no shared output is
removed or overwritten. The lock pins documentation dependencies independently;
MkDocs/Material versions initially match the existing root lock. Nothing here
removes current product dependencies or release obligations.

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
  --producer-manifest .build/producer.json --ir .build/inventory.json \
  > .build/input-provenance.json
```

Both source arguments must be explicit full commit IDs. Input blob lookup reads
that revision, not current checkout contents. No schema producer is run by this
consumer; producer execution uses the separately verified product environment.
The scaffold rejects missing/malformed evidence, path traversal, symlink inputs,
changed input/IR hashes and mismatched selected product identity. It checks
consistency only: a self-consistent fabricated IR/manifest is not an independent
execution proof, and a manifest's input map is not proof of input completeness.
SEP3/SEP4 must supply and adversarially verify the full producer input contract
and local/hosted execution evidence before any complete-release claim. There is
no full_acceptance success field in these preparation records.
