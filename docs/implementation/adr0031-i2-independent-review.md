# ADR 0031 I2 independent SQL review — Task D

The completed independent review of [Task C / PR #120](https://github.com/TakashiSasaki/git-repo-db/pull/120)
is published as review evidence only. **Verdict: NOT READY** for the frozen
I2 SQL proposal and its staged Transfer fence.

Read the [complete original report](evidence/adr0031-i2-independent-review/REPORT.txt),
[reproduction SQL](evidence/adr0031-i2-independent-review/F1-reproduction.sql), and
[evidence guide](evidence/adr0031-i2-independent-review/README.md).

One new High finding, F1, concerns the temporary fence. It blocks Transfer
endpoint rows but permits direct `transfer_event_report` insertion into
`resource_relations`. A Provider-only report with no endpoint rows is returned
by the existing reference reader even when the native I7 Resource and Parent
report are absent. This is a missing staging guard, not a request to reopen
G3=A or implement I4 in I2.

On each independently built actual SQLite 3.51.3 and 3.53.1 runtime:

| Lane | Passed / executed | Failures | Process exit |
| --- | --- | --- | --- |
| Task C's existing cases, rerun in fresh disposable state | 133 / 133 | 0 | 0 |
| Independent cases on the unchanged proposal | 295 / 301 | 6 manifestations of F1 | 1 with the separate control lane |
| Disposable mitigation controls | 7 / 7 | 0 | Included in the independent runner |

The independent runner executes 308 cases in total and exits 1. Mitigation
controls do not count as successful tests of the original proposal. Resource
identity, metadata, BINARY indexes/FKs and immutability passed the tested major
counterexamples; product integration and I3–I8 guarantees remain separate.

The reviewed commit is `9eaa5111c94204c4adf791cd1565b704728493f1`, tree
`d91c73b5caed2601a6b097c69017e0e49e96bc53`. The publication starts from that
exact commit and adds only documentation and frozen evidence. Task B's completed
I1b review is retained as context and was not commissioned or executed again.
No product fix, accepted-ADR change, merge, release or deployment is supplied.
