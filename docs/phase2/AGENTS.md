# Phase 2 design work: current owner decisions

The repository-root AGENTS.md remains applicable. For the design artifacts in
this directory, read `no-independent-publication-adr.md`, `../adr/0002-three-store-boundary-architecture.md`, and the current
`decision-register.md` before the older proposals or prototypes.

The owner accepted Q01-B, Q02-B, Q03-B, **NO_INDEPENDENT_PUBLICATION** under Q04, and binding decisions **PF-P01–PF-P17** establishing the Three-Store Boundary (Core, Operational, Search).
Use the checked-out sources, current ADRs, and exact-tree receipts to distinguish approved design,
implemented behavior and independently verified behavior. Do not restart the
old design questionnaire or adopt unchosen recommendations. This document does
not itself grant or revoke a task-specific merge authorization.

`proposal-before-no-publication.md` and
`decision-register-before-no-publication.md` are exact preserved snapshots of the
previous proposal. The 69-table candidate, old workstream recommendations,
conditional schema disposition and old probe/review receipts are evidence of that
checkpoint, not current target DDL or proof of this redesign. Update active
narrative/design separately and preserve historical receipts with their hashes.

No independent generic Publication/bundle/member-seal owner or eligibility layer
may be recreated under another name. Local transaction atomicity, domain validity,
collection completeness, current conflicts, Git content/acquisition/targets,
operational fences and receiver validation require separate reasoning. A local
revision counter or domain-specific completion predicate is not automatically a
Publication and must not be deleted by substring matching.

Keep latest-state contracts truthful: do not hide all superseded values inside
necessary evidence; do not infer deletion from incomplete scans; do not use parser
version or receipt order as domain freshness. Preserve already implemented domain
scope/member/terminal/child proof without inventing a new collection-proof policy.
No new cache, checkpoint, Exchange trust or retention/GC policy is selected.
Report genuine unresolved requirements without inventing their answers.

For reproducible Phase 2-specific debugging or review lessons, consult and
update the repository-local `.agents/skills/` where a validated procedure is
reusable. Keep immutable historical review receipts unchanged and link them as
evidence rather than copying whole logs into a skill.
