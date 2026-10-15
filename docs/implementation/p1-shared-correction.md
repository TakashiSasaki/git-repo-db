# Shared P1 correction required by production implementation review

P2/P3 independent review demonstrated a High enforcement defect on unchanged
P1 `67e8be65c3061b494c2c7373e2fd151398435f62` (tree
`1d9b73e363e5b8a2bfe252fdcb87c7571d012e37`). Through the supported coordinator
callback, inserting an intrinsic link to an earlier **reported** scalar or whole
group changed that original alternative's projection from unchecked to checked.
Matching native bytes validated the value but did not justify relabeling its
original provenance. The accepted contract already prohibits that promotion.

This is one common corrective dependency for both production siblings, based
on P1. It changes no domain identity, port, physical ownership, Coverage column,
coordination protocol or accepted ADR. No public initializer, runtime, workflow
or publication allowlist changes. There is no merge/deployment authorization.

## Executable counterexample and correction

Admit a reported `type=tree` claim (or reported known-empty tree group), then
retain matching exact native empty-tree bytes through `Core.admit_metadata`.
The original report correctly remains unchecked beside separate receiver
evidence. In `PairCoordinator.admit`, issue an `INSERT INTO intrinsic_claims`
(or `intrinsic_groups`) using that **original report key** and retained copy.
Before correction it commits and promotes the original report. Four regression
cases (scalar/group × SHA-1/SHA-256) failed at the intended missing refusal on
unchanged P1; all pass with the correction.

Both physical intrinsic guards now require the existing provenance qualifier
`receiver_intrinsic` in addition to their existing exact native-value/group
checks. Rejected incoming links roll back atomically, leave earlier reports and
canonical values unchanged, and do not falsely stop a healthy catalog. Genuine
receiver evidence and its exact replay still succeed. The Core DDL fingerprint
and generated disposition/schema evidence were regenerated; Context,
Operational and Search fingerprints remain unchanged. No data migration or
backward-compatibility path is introduced for this fresh isolated format.

The separate audit correction explicitly identifies the six optional P2/P3
modules as isolated from the historical Schema 21 lexical call-site inventory.
It preserves the existing P1 module existence checks and strengthens the public
runtime import guard: absolute, relative and `from` imports of **any** isolated
P1/P2/P3 module are rejected. Seven adversarial forms exercise that boundary.
Neither sibling needs to contain the other implementation. P8 must deliberately
remove isolation when the coherent public runtime is activated.

## Exact verification and independent review

Guard source: `2e8618428bea482ececef580045066cd49552455`, tree
`9f50e3be6bdf92cfc33ccb490b04a369f74e1609`.
Reviewed executable source including the initial audit correction:
`fe925cc61ad6cf09c826b36dec0854ad44bd8e27`, tree
`010e09014f860cf012c13346b9dc19d419affb76`.

The clean final run selected, executed and reconciled **390 passing nodes**:
260 P1 contracts, 128 architecture-spike/audit tests and two isolated installed
wheel/sdist-wheel variants. Zero failures/skips. The earlier guard-only run
passed 384; these are separate runs, not additive coverage. Ruff lint/format,
schema fingerprints, complete disposition and baseline call-site audit pass.
Python 3.12.14, SQLite 3.53.1, Git 2.52.0, uv 0.12.19. Exact commands, node IDs
and artifact hashes are in [the receipt](p1-shared-correction-evidence.json).

Independent Git reviewer reproduced the defect on exact original P1, then
executed all four correction cases and confirmed the original counterexample
fails at its intended INSERT. Independent cross-domain reviewer passed 125
Context/Coverage/coordination/derivative and new guard cases at guard source,
and inspected unchanged identity/schema/interface boundaries. Independent
integration preflight passed 108 Core/notes/guard cases on a committed effective
tree containing #71/#70/#72 and the guard correction. Independent Git reviewer
also passed all 16 disposition tests at final audit source using its own worktree
environment. These are task-specific read-only reviews, not GitHub approvals or
full release acceptance. Subsequent evidence-only commits do not claim repeated
runtime execution.

The final extension-port audit follow-up is
`bc6c2c18e05b0c77c0d928626f28518727318a52`, tree
`180f34e68df72d19a443982ad8dca03eece175dd`. It adds the exact optional
`domain/ports/production_context.py` path and seventh import form. It changes no
production source or DDL. Root passed all 21 disposition/guard tests, Ruff and
the call-site audit; the independent cross-domain reviewer passed all 17
disposition tests and approved the narrow diff. The 390-node receipt above
remains bound to its original source; it is not relabeled as a 391-node run.

## Dependency and integration boundary

Keep one correction commit history and common dependency branch; never create
separate P2/P3 schema variants. Both production branches incorporate this exact
dependency by merge commit and remain siblings. Their PRs target the common
correction branch while P1 remains unmerged. This adjusts the original P1-only
stack because of an executable shared defect, under the owner's explicit
shared-correction provision.

Original #72 alone remains **CHANGES REQUIRED**. The corrected integration plan
is #71 → #70 → #72 → this separately reviewed correction, with merge commits
preserving original history. After each dependency reaches main, recheck and
retarget its related child as necessary; do not execute this plan without owner
authorization. Documentation changes mean this correction's eventual main
merge also triggers the existing Pages workflow. No auto-merge, main update,
merge, Pages publication, production migration or real-catalog operation occurred.

Owner-level architectural blockers remain **0**: the defect contradicted an
implementation guarantee, not two accepted architectural requirements.
