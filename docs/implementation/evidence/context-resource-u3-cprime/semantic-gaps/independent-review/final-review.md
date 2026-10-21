# Independent review of the semantic-gap follow-up

The reviewer is a separate agent from the candidate and author harness author.
It inspected the accepted decisions, proposed design, previous experiment, and
corrected frozen candidate. It did not edit candidate SQL/Python, author tests,
production source, packaged DDL, accepted ADRs, or default runtime settings.

| Gap | Independent classification |
| --- | --- |
| G1: independently identified Documents | **CLOSED — corrected and independently verified** |
| G2: canonical Parent representation | **CLOSED — corrected and independently verified** |
| G3: I7 identity namespace versus I8 attributed Parent | **OWNER DECISION REQUIRED — actual unresolved architectural conflict** |

G1 and G2 closure is scoped to the executable isolated contracts and genuine
synthetic identity declarations below. G3's temporary withholding behavior is
verified; its permanent semantic rule has not been selected. U3=C′ remains
demonstrated for the earlier experimental subset, extended by G1/G2 evidence.
It is not demonstrated for the whole proposed ADR 0031 acceptance contract.

## Exact reviewed freeze and runtimes

- Corrected executable commit: `9eeacb28f7e4a426114a9ce40e2324b4da302817`.
- Corrected tree: `8f78de68058582327beddbb656207659507d43c6`.
- Composed SQL SHA-256:
  `2892a5fb0bcef8a0e0ea916fc1b71687a0a2afe545849e27dec4f7fd3600171f`.
- Exact input manifest: [frozen manifest](../input-freeze.json). The reviewer
  checked its executable hashes and composed SQL hash in a detached checkout.
- SQLite 3.53.1, source ID
  `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
- SQLite 3.51.3, source ID
  `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.

Runtime receipts include Python, actual SQLite source IDs, compile options,
connection pragmas, exact inputs, SQL traces, actual errors, rowsets, transaction
state and FK/integrity checks. SQLite versions were not mocked or relabeled.

## Executed evidence

Each set below ran on both genuine runtimes. Counts overlap and must not be
summed into a distinct coverage total.

1. [Author rerun](author-rerun/summary.json): all 15 previous grouped scenarios,
   163 recorded steps, and 9 packaged-baseline controls, plus 3 focused groups
   with 46 recorded steps. The frozen driver was run from the detached checkout.
2. [Preserved reviewer scenarios](previous-75-adapted.py): all 75 previous
   observations passed, with an explicit fixture adaptation to canonical Parent
   TEXT. The original reviewer script remains untouched. IR15/IR16 are clearly
   labeled structural-only I8 diagnostics, not qualified Transfer acceptance.
   [3.53.1](previous-75-current.json), [3.51.3](previous-75-minimum.json).
3. [New independent probe](corrected-probe.py): 39 expected observations per
   runtime, including direct SQL and explicitly named admission calls.
   [3.53.1](corrected-current.json), [3.51.3](corrected-minimum.json).
4. [Previous-candidate counterexamples](previous-counterexamples.py): 4
   observations per runtime at `22b58ce7ff59478f1a4c8c8ef89b17d2f0068590`,
   tree `fcc55256de88c711379d27e38b7eed0c63db6c4a`.
   [3.53.1](previous-current.json), [3.51.3](previous-minimum.json).
   They demonstrate global Document rejection, PR-scoped admission without
   Parent, and unqualified I8 Transfer admission. They remain historical results.

No unexpected candidate failure occurred in these independent executions.
An ad hoc receipt-summary command initially assumed every baseline control had a
`steps` field and raised `KeyError`; the corrected summary uses `get('steps', [])`.
That reporting utility error was outside the probes and did not affect their
results or mutate the candidate. Reviewer scripts were then formatted and two
import-order lint findings corrected; all six runtime invocations were rerun.
Their initial script bytes and successful receipts remain in
`development-before-format/`, with matching recorded hashes. Final scripts pass
Ruff checks and format checks.

## G1 assessment

The corrected global Document form preserves the Resource kind and complete
canonical native ID. It has NULL namespace/subtype columns and a required
`provider_document_id` equal to the Resource's full canonical ID. Consequently,
removing all metadata from a PR-shaped input is still rejected by SQL. The
PR-scoped form retains namespace kind, exact canonical namespace ID, document
kind and complete native document coordinate, with consistency enforced by a
row-local CHECK. No additional PK coordinate, surrogate or domain table appears.

The explicit `document_input` constructor selects `provider_global` or `pr_scoped`
from the genuine Provider identification contract. Invalid PR input raises; no
exception path retries it as global. Global input cannot discard supplied scoped
coordinates. The selection is admission-layer validation and does not prove an
external Provider's native contract. SQL cannot infer that truth from a scalar or
an array shape; a four-component global array is correctly accepted as global.

The generated `reference_document_kind` uses `''` solely as a non-key absence
projection. Explicit `document_kind: null` in an independently identified
Document's Parent scope maps to that projection, closing the nullable composite
FK escape. A scoped Document's nonempty subtype cannot satisfy that reference;
a global Document cannot claim a PR subtype. Actual direct SQL controls reach FK
errors for absent targets and source-subtype mismatch, and CHECK errors for an
omitted scope member or cross-Provider typed Parent. This empty projection is
neither an identity placeholder nor an invented semantic coordinate.

Scalar, nested-composite, PR-shaped global composite and genuine empty identity
fixtures succeed. Documents acquire later attributed relations without rekeying,
retain independently attributed reports, and parent other Documents. Partial or
changed identifying fields and conflict-ignore/replacement rebinding fail.
General arbitrary member arrays retain their existing application dependency
boundary; this review does not call them SQL-projected FKs.

## G2 assessment

The selected scoped encoding is
`[namespace_kind, canonical_namespace_id_TEXT, document_kind, native_document_id_value]`.
The namespace component is always a string containing canonical JSON, including
when the Parent identity is itself a scalar. The native document coordinate may
use the recursive identity grammar. References preserve exact canonical TEXT.

Both the former nested profile and this profile are injective and reversible
when used separately. They retain the same genuine semantic coordinates and do
not need an extra identity discriminator merely to choose an encoding. The
selection follows proposed #114's explicit Parent-TEXT proposal and does not
silently drop an accepted ADR 0017 coordinate.

Accepting both profiles would yield different keys for the same native Resource
and can alias different native Parents across profiles. The independent probe
stores both an array-native Parent's Document and a literal-canonical-text-native
string Parent's Document as distinct selected-profile keys. It rejects the
alternate nested encoding, and a mixed-profile alias cannot pass conflict-ignore
by rebinding namespace metadata. No compatibility claim is made for the old,
unreleased experimental encoding; its frozen evidence stays separately valid.

## G3 assessment and owner boundary

The candidate retains I8 as a separately attributed Parent report without
asserting it is the correct current Parent. Its real FKs permit an exact typed
I8 support report and endpoint for an Event whose native namespace is I7; the
independent probe explicitly demonstrates this inside a rolled-back diagnostic
transaction with clean FK and integrity checks. SQL validity establishes exact
structural support, not the semantic correctness of that Transfer.

The default `admit` boundary now raises `QualificationRequired` for the mismatch
before any writes. It does so even if a direct SQL diagnostic already inserted
the same unit, so replay does not silently launder qualification. The earlier
helper is explicitly renamed `structural_admit`; its use in old T06 is clearly
structural. The matching I7 case and idempotent replay remain admitted. This
withholding is a temporary unresolved-case boundary, not a new universal rule
that native identity namespace and semantic Parent must always equal.

[Source review](semantic-source-review.md) maps the competing interpretations.
ADR 0030's typed contract was expressed when those coordinates coincided. B3
permits separating them but does not select which now determines the Q-S10 Issue.
The owner must resolve whether I8 is ineligible support for the I7 Event contract,
or whether genuinely qualified I8 support may define the Q-S10 Issue independently
of I7. The latter requires explicit carry-forward analysis and, if a substantive
reversal, the governance amendment process. Neither outcome is implied by these
passing structural probes. This is one specifically scoped new potential blocker,
not reopening the earlier migration scope's zero-blocker conclusion.

## Earlier evidence and limits

The old `e9aba86f4530b2e683c77e23a4fe58bdf02192c5` reviewed executable and its
`c2c325532279f35ba51b36aacbeea30ceda4040e80b5d31512cbb9e19d564dee`
composed SQL retain their previously stated subset verdict. Their known-document
claim did not include genuinely global Documents; their I8 support checks were
structural/evaluation-separated. The wider semantic reading is not retroactively
proven. Original failed and successful receipts and original reviewer scripts
are preserved.

The new evidence supports a precise update to the ADR 0031 author: cite the
corrected G1 contract and chosen G2 representation at this freeze; retain the
Q-S10 semantic gate pending the G3 owner decision. No Product Exchange, paired
backup, Provider adapter, external authenticity, production integration, merge,
deployment or release has been demonstrated or authorized by this review.
