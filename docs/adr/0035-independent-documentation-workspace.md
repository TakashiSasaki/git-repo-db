---
status: proposed
date: null
replaces: []
refines: ["0001", "0034"]
---

# ADR 0035: Independent documentation workspace

- **Decision & Context (proposed):** Human-facing derived documentation belongs in an isolated `documentation/` project with its own lock, environment and outputs, outside the root uv workspace. Documentation follows a selected product source SHA/tree and input hashes; product work never waits for documentation to catch up. Extract neutral schema introspection before moving renderers. Preserve current IR/output semantics, implemented three-store coverage, composite foreign keys, generated columns, partial uniqueness and DDL fingerprints. Canonical ADRs, contracts, machine inputs and historical evidence remain in place; generated copies are read-only staging, never competing editable authority.
- **Constraints / Do NOT:** No product semantics, Transfer fences, SQLite policy, minimal distribution boundary or source/config/build-context cache validation changes. No blanket `docs/**`, root-input or unknown-path exclusions. Preserve every existing test obligation through an exact one-to-many node map. Product verification excludes rendering dependencies; full release evidence must separately account for both product and documentation obligations and may not claim complete acceptance when either required scope is unverified. Reuse Pages and its publication allowlist; this proposal authorizes no publication, required-check changes or main merge.
- **Reason & Ref:** Current product setup installs the docs group and Access builds MkDocs. The product boundary audit imports introspection from the renderer module (which itself does not import MkDocs). Separate these concrete dependencies without weakening safety gates. See the [bounded plan](../implementation/documentation-separation-plan.md) and [file/node ledger](../implementation/documentation-separation-ledger.json). Level 2: workflow/dependency-boundary refinement, no accepted product decision reopened. The owner approved SEP0–SEP4 design, implementation and independent verification on 2026-10-26, explicitly excluding main merge, publication and required-check settings. That permission is not adoption of this ADR. Explicit owner adoption of this proposed workflow and its release-accounting contract remains necessary before cutover is treated as accepted policy.
