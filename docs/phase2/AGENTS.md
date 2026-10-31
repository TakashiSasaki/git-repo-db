# Phase 2 design work: current owner decisions

The repository-root AGENTS.md remains applicable. For this directory, read the
current `decision-register.md` and `documentation-status-audit.md`, then
`no-independent-publication-adr.md` and `../adr/0002-three-store-boundary-architecture.md`
for their accepted decisions before consulting older proposals or prototypes. **For the later accepted target**, read the [current ADR index](../adr/README.md) and [Git Core / Context transition plan](../architecture/git-core-context-transition-plan.md). [ADR 0029](../adr/0029-independent-access-store.md) replaces retired ADR 0003 and carries forward its Core/Context guarantees within five store responsibilities; [ADR 0030](../adr/0030-context-repository-relations-and-selective-exchange.md) adds typed Repository relations and selective Exchange without mapping Witness storage. Surviving ADRs 0004–0028 remain binding in their scoped meanings: ADR 0038 fixes recovery without quarantine/count/release, and ADR 0036 carries retired 0027’s unauthenticated external-origin reports without application PKI/signatures. Unaffected Q/PF guarantees remain; target decisions do not certify their implementation. ADR 0037 supplies the
operation-scoped installation contract; ADR 0038 changes Git-only optional-store
initialization without changing paired recovery.

The owner accepted Q01-B, Q02-B, Q03-B, **NO_INDEPENDENT_PUBLICATION**, and binding
**PF-P01–PF-P17**. Publication removal and Three-Store implementation are already
integrated; an old "implementation pending" statement is not current status.
Implementation, independent review evidence and release acceptance are separate.
This document itself grants no merge, release, deployment or data-operation permission.

The old blanket pause on Q05–Q12 is superseded only within the explicit scope of
later accepted decisions. Do not replace it with blanket approval of every old
alternative. The old Core/Operational/Search placement and Core-only full-backup assumption
were settled in ADR 0002 **for the implemented baseline**, but are **superseded as
future target architecture by ADR 0029's carry-forward of historical ADR 0003**. Best-effort resume, transport-owned
HTTP caching, Job retention and explicit Search lifecycle remain settled. Stronger Exchange trust, additional Git interpretation policy, future
manual-GC rules and other residual boundaries are not approved by implication.
Consult the register before calling a question either "resolved" or "unselected".

`proposal-before-no-publication.md`, `decision-register-before-no-publication.md`
and `decision-register-before-status-reconciliation.md` are exact preserved
checkpoints. Their old status words, option letters, 69-table candidate,
recommendations and probe/review receipts are not current target DDL or proof of
later execution. Preserve their bytes and hashes. Read pre-PF-P design work
sequences as historical instructions, not orders to repeat completed work.

No generic Publication/bundle/member-seal owner or eligibility layer may be
recreated under another name. Local transaction atomicity, domain validity,
collection completeness, current conflicts, Git content/acquisition/targets,
operational fences and receiver validation require separate reasoning. Do not
delete meaningful completion markers or local revisions by substring matching.

Keep latest-state contracts truthful: do not hide superseded values as generic
history, infer deletion from incomplete scans, or rank domain values by parser
version or receipt order. Preserve required scope/member/terminal/child evidence.
Current evidence layout does not imply unlimited retention or deletion permission.
Preserve actual retained-byte/domain, database/manifest/identity and required
Core+Context pairing validation. ADR 0038 retires the old CAS-41 active-quarantine
count/order for the new target and requires immediate recovery on authoritative
corruption; do not reintroduce that baseline mechanism through its old ID.
Mutable Core revision updates likewise require the append-only-safe/fenced target
replacement, without a counter-history authority. CAS-76/CAS-77 need original-source
clarification and must not be assigned guessed meanings or marked accepted.

For verified reusable audit/debugging lessons, consult and improve the relevant
repository-local `.agents/skills/`. Keep execution receipts separate from skills;
never invent independent approval or a test run from a documentation status label.
