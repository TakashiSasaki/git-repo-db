# Independent exact-tree review: first I3 candidate

Reviewer: read-only subagent `/root/i3_invariants` (no production authorship).
Target HEAD `b7f40fa7e1c556a73d63242aaef5abf5a39b1960`, tree
`736adc54aa7ff85aef71c6361f97183ec7302c87`, committed and pushed.
Verdict: **CHANGES REQUIRED**. Reviewer independently ran 29 I3 tests successfully,
then executed two additional blocking counterexamples:

1. Changing a Source Coverage proof's `members_json` to `[]` and recomputing the
   package digest was accepted; import reconstructed the original proof rather
   than rejecting contradictory wire evidence. Collection proofs shared the
   clock-prefix matching hazard.
2. Mutating caller-owned `package.core` at `after_preflight` admitted the new OID
   while binding the old digest, because the package/dictionary still aliased the
   receiver's input until after validation.

Corrections: compare the full immutable terminal FK and original Coverage claim
before binding; associate proofs with full terminal keys at admission; retain
competing terminal sets as whole budget/selection units; bound and privately copy
caller-owned Package/dictionary input before digest/domain validation. New
regressions exercise Source and collection member/state/provenance contradictions,
caller Package/dictionary mutation, and selection hiding a competing inventory.

The final independent verdict targets the subsequent committed/pushed HEAD and
is recorded with its exact tree in PR #108. This historical CHANGES REQUIRED
record is retained; it is not an approval of either candidate.
