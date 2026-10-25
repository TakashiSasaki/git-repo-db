# Verified review-harness lessons

The existing efficient-investigation, CI-final-tree-verification and
lessons-to-skills procedures were applied. This read-only review recommends
additions to the existing CI verification skill; it does not mutate the frozen
implementation or introduce another overlapping skill.

1. An isolated Transfer fixture wrapper deliberately expects the unfenced synthetic
   schema. Restoring both exact triggers does not convert that wrapper into a
   normal factory input. To check the normal factory, use a fresh normal connection,
   or the synthetic fixture's raw connection only after restoring **and validating
   the complete** packaged schema. Keep both triggers and all guards intact.
   Three initial facade controls failed at schema validation; the corrected source
   and both installed132-node controls actually reach the normal stage refusal.
2. The existing `verify_i5_offline.nodes()` recognizes repository IDs beginning
   `tests/`. A newly staged root-level test can really collect132 nodes while that
   helper returns0. Stage custom installed tests under an explicit `tests/review_*`
   package or use a separately validated general parser. Require exact node/JUnit/
   journal/phase identity, not a guessed count. The failed installed attempt is
   preserved; the corrected conventional harness passes both artifact forms.
3. Sidecar hooks opening with `x` need different collection and execution targets.
   Set their environment before collection too. Preserve bootstrap failures and
   never reuse the collection sidecar path as an execution destination.

Reproduction: use the indexed `tools/test_task_c_originals.py` and
`tools/run_installed.py` on the frozen #148 tree. Prior failed driver/test versions
are separately indexed under source-extra and installed-v2. These are test-harness
procedures, not policy, permissions, production schema changes or instructions
to remove either Transfer fence from an ordinary catalog.
