---
status: accepted
date: 2026-11-17
replaces: ["0041-independent-web-branch.md"]
refines: ["0035-independent-documentation-workspace.md", "0040-scoped-machine-readable-model-validation.md"]
---

# ADR 0042: Asynchronous website refresh from main

- **Decision & Context:** The independent orphan `web` branch follows `main` asynchronously. `product-source.json` names the canonical repository and `ref: main`; maintainers do not update a committed product SHA. Each preparation attempt resolves main once, uses that external checkout throughout the attempt, and automatically records its actual commit/tree and retrieval time for diagnosis. Later main updates require neither a restart nor a matching-current-main check. Website lag, failed refreshes and unfinished explanations never block product work or ordinary main checks/merges. Prefer deterministic extraction/rendering and changed-page review; a routine refresh requires no language-model generation of the site. Scheduling and automatic publication are separate implementation decisions.
- **Constraints / Do NOT:** Preserve independent Node/Python environments, verified environment-loaded SQLite, complete neutral IR semantics and structural validation, the public-input allowlist, historical evidence/citations, private output confinement and same-attempt input integrity. Build records describe the actual inputs and execution scope, not a claim that every explanation reflects one product commit. ADR 0035's complete release conjunction remains dormant unless release validation is explicitly requested; normal refreshes do not require it. Do not turn diagnostic source IDs into maintained pins, demand equality with a moving main tip, silently rewrite historical citations or generate the whole site with an LLM to follow a product update. Production deployment remains a separate manual opt-in.
- **Reason & Ref:** The owner gives website maintenance lower priority than product work and wants inexpensive catch-up without exact version management. On 2026-11-17 the owner explicitly accepted replacing the committed product SHA with main tracking and simplifying strict pin management: “そのように方針を変更します。” Approval annotation: `9e2f0b62-c10c-44c9-acd0-cc7ca9fdf312`. This Level 2 workflow replacement introduces no database/runtime change. It fully succeeds ADR 0041; its initial branch separation was approved in annotation `cb0150ab-b6b9-4020-a9c5-4a39ffe3f245` and integrated by [PR #268](https://github.com/TakashiSasaki/resource-atlas/pull/268).

## Preserved branch and handoff contract

`web` owns editable website sources and its Node/Vite frontend, with at most
1,000 tracked files for Google AI Studio. The frontend runs without product code,
Python, credentials or live catalogs. Product code, canonical ADRs/contracts,
schema production, ownership/frozen-evidence checks and the runtime guide remain
on `main`; transferred website/frontend sources stay absent there. Routine site
work never merges these two trees.

The external product checkout supplies canonical inputs read-only. The verified
product interpreter extracts the complete schema IR in a fresh subprocess;
checked IR/producer metadata and canonical-source manifests enter private build
inputs only. `docs/web-source-policy.json` owns public selection. Derived models
and staged pages never become editable product/design authorities. Current
normal/opt-in/target/historical meanings remain distinct. Existing historical
citations keep their original revisions; automatically recorded build inputs do
not certify handwritten semantic accuracy.

For local/offline investigation, an explicit existing product checkout may supply
its HEAD without contacting a moving remote. Record this override honestly; it
does not establish freshness. Missing/inconsistent inputs fail that web attempt
and leave main's development independent.

The migration ledger and `docs/web-branch-test-map.json` preserve every moved
test obligation. Main owns `docs/content-inventory.json`,
`scripts/content_inventory.py`, `tests/unit/test_content_ownership.py` and
`docs/current-runtime-reference.md`. Frozen historical bodies/receipts remain
unchanged. Retain independent product/documentation execution evidence when
complete release acceptance is explicitly requested; preview results remain
scoped development evidence.

## ADR 0041 clause carry-forward

| Predecessor clause | Successor |
| --- | --- |
| Independent web ownership, main removal, 1,000 files and standalone frontend | Preserved branch and handoff contract, first paragraph |
| Independent environments, full IR, composite/partial/generated semantics, SQLite and structural checks | Constraints and the read-only extraction contract above; ADR 0035 remains applicable |
| Explicit maintained product SHA and intentional pin refresh | Replaced by `ref: main`, one resolution per attempt and automatically recorded actual inputs |
| Distinct source/IR identities, canonical allowlist, private inputs and historical byte checks | Preserved as diagnostic execution/input integrity; no site-wide semantic correspondence claim |
| Ownership/runtime-guide relocation, migration ledger and exact moved-test obligations | Preserved above, including frozen evidence and explicitly requested release accounting |
| Product-first work, separate histories, no routine cross-branch merge | Preserved; web failure or lag cannot gate main |
| Manual opt-in production deployment and unchanged publication boundaries | Preserved; no deployment or settings change is authorized by this replacement |
