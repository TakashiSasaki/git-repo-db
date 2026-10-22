---
status: proposed
date: null
replaces: []
refines: [0001-validation-lifecycle-architecture.md, 0032-environment-sqlite-validation.md]
---

# ADR 0033: Minimal product sdist with distribution equivalence

- **Decision & Context:** Propose a repository-wide **Level 2 Mini-ADR** for a
  reversible build/validation convention. Keep Git-managed design documents and
  historical verification evidence, while making the product sdist contain only
  the project inputs needed to rebuild the product wheel. Prefer
  `[tool.hatch.build.targets.sdist]` with an explicit `only-include` list:
  `src/repo_catalog`, `pyproject.toml`, `README.md`, and any required license or
  other distribution metadata. Include all product package data, including SQL,
  JSON and GraphQL resources. Inventory backend-generated metadata separately;
  permit only explicitly checked generated members such as `PKG-INFO`.

  Validate every sdist member against the allowed source paths and generated
  metadata, check required-file completeness, and measure compressed bytes,
  unpacked regular-file bytes and member counts. Apply reviewed finite size
  limits calibrated in the implementation PR. Build both the direct wheel and a
  wheel from the extracted sdist; require equivalent member contents, metadata,
  isolated installation and actual behavior. The sdist build must work without
  Git, the original checkout, developer documents, tests or validation scripts.
  Test drivers and locked dependencies remain separate validation inputs.

- **Constraints / Do NOT:** Do not delete, rewrite or move historical evidence or
  design documents to reduce an artifact's size: Git preservation and product
  distribution membership have different purposes. `docs/`, `tests/`, `scripts/`,
  verification ZIPs, logs, CI receipts, caches and build outputs are not required
  product-sdist inputs and must not enter through a permissive fallback. Do not
  filter solely by `.py` or drop package data to meet a size limit; the wheel must
  retain its complete runtime inputs. Do not treat a small archive, a successful
  build, equal file counts or matching failures alone as behavioral acceptance.

  Preserve [ADR 0001](0001-validation-lifecycle-architecture.md)'s focused
  development checks and explicit independent full local **and** hosted release
  validation, separate distribution lanes, input/artifact hashes, offline guards,
  exit codes, exact node reconciliation and non-destructive evidence retention.
  Preserve [ADR 0032](0032-environment-sqlite-validation.md): use each environment's
  actual Python-loaded SQLite, retain interpreter identity and all product WAL
  safety/capability checks, and introduce no test-only SQLite setup or version
  matrix. Keep inherited failures visible. A development check is not release
  acceptance. Documentation-site generation continues from a Git checkout using
  its existing publication allowlist; no sdist dependency or site expansion.

- **Reason & Ref:** Default broad source selection can grow whenever unrelated
  tracked documents or frozen evidence are added. A positive inclusion boundary
  prevents that coupling without losing the repository's audit history. A growing
  exclusion list is easier to miss; removing evidence would destroy provenance;
  wheel-only validation would lose the independent sdist rebuild check. The cost
  is maintaining the inclusion contract, generated-metadata exceptions and size
  budgets as legitimate product inputs evolve. The product sdist will not be a
  standalone developer/test/docs checkout; contributors use Git for those tasks.

  The [design and implementation validation plan](../implementation/minimal-sdist-design.md)
  records the inspected paths, planned build/CI routes, acceptance criteria and
  engineering details still to settle. This is an additive distribution-specific
  refinement of ADRs 0001 and 0032, under [ADR 0011](0011-adr-governance.md) and
  [policy](policy.md); no accepted ADR is reversed, edited or retired. No product
  data contract, SQLite safety predicate or existing evidence meaning changes.

  Allocation on 2026-10-22 UTC checked all 69 fetched remote heads, reachable ADR
  filename history including deletions, historical index watermarks and all 19
  open PRs (through #134). Highest prior allocation is 0032; the index's stale
  opening 0031 watermark is corrected to agree with this new 0033 allocation.
  This proposal is stacked directly on [PR #133](https://github.com/TakashiSasaki/git-repo-db/pull/133)
  at `f16e5b1713bde9a2f18263a25397c4b450fd5773`. It remains **proposed**, with
  `date: null`, until explicit owner acceptance. This task delivers design only;
  implementation, merge, release and deployment are not authorized.
