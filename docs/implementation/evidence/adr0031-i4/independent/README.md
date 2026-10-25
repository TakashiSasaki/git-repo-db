# ADR 0031 I4 independent review publication

**限定I4独立レビューPASS**, limited to the SQL implementation reviewed in
[PR #127](https://github.com/TakashiSasaki/git-repo-db/pull/127). Product findings:
**0**. Unresolved review findings: **one Low evidence-scope issue, I4-E1**.
Whole-product and whole-ADR acceptance remain NOT READY.

Read the [frozen independent report](REPORT.md), [machine summary](summary.json),
[all-79 comparison](failure-classification.json),
[raw-message differences](raw-message-differences.json),
[I4-E1 reproduction](finding-i4-e1.json) and
[sdist input-scope evidence](sdist-input-scope.json).

The report and ZIP were completed before the owner's separate instruction to
submit a review PR. They are copied byte-for-byte, preserving their historical
read-only review scope. Publication is now owner-authorized on a new branch;
neither PR #127 nor its implementation branch is modified. No product/test,
accepted ADR, original Author evidence or earlier report is changed.

## Execution and publication identity

- Base #126: `614ccaac3512a0df4291653fc83901df211f00f6`, tree
  `0e35eccffd996c5b7ed175a53adebf2ac76b16cb`.
- Reviewed public product and independent execution:
  `a9d4c3585806622b66d3c41132c2a9f8ab5c6f9e`, tree
  `3dd1e39e06d347883a6fb493e7b9b06fb6dbfb62`.
- This new review PR is based on that exact #127 HEAD and adds only this evidence
  directory. Its body records the separate publication commit/tree after commit.
  No new product execution is claimed for this evidence-only publication.

The [publication binding](publication-binding.json) records source/copy hashes.
The reviewed runtime/wheel inputs are unchanged. Full sdist/source archives gain
these review files and therefore acquire new input sets; do not claim complete
sdist-input identity for this publication. I4-E1 remains open in the Author
packet and is not silently resolved by this separate review.

## Independently executed results

Both actual SQLite 3.51.3 and 3.53.1 ran 153/153 reviewer-designed SQL/API cases,
217/217 I4 cases, 65/65 existing I3 cases within broad regression, and 301/301
existing SQL diagnostic groups. Each broad run has 3,108 starts: 3,029 pass,
59 call failures and 20 setup errors, exit 1. The final I3 baseline's 79
non-success node/phase/refusal positions remain; zero added and zero resolved.
No later assertion behind refusal or 2,541 unexecuted ordinary nodes is counted
as PASS. The original eight corruption nodes and guard-restoration observations
are preserved and independently checked.

Fresh direct and sdist-derived wheels, installed outside checkout on both
engines, pass 217/217 I4 and 153/153 independent cases in all four combinations.
The original Access smoke still exits 1 at Transfer preflight in all four;
distribution orchestration exits 1. Both product Transfer fences remain active.

## Portable evidence

- [Evidence ZIP](independent-evidence.zip): **12,376,614 bytes**, SHA-256
  `7dacbc506fd0ab6cc681008752b5e95608299a085c09aceb5cbc748822e86c88`.
- [Payload index](artifact-index.json): 649 indexed payload entries plus the
  embedded index, 650 ZIP members. Every length/hash was reverified for publication.
- [Artifact binding](artifacts.json) preserves the original workspace artifact
  basename `i4-independent-evidence.zip`; the repository copy is named
  `independent-evidence.zip` with identical bytes.
- Frozen report SHA-256:
  `5ee7210741baa47843cba118543889530861ab06524485fd9136ff54e07af830`.

The ZIP contains exact reviewer scripts, SQL/expectations/results, runtime/source
measurements, raw pytest/XML/journals, 301 diagnostic receipts, installed-wheel
logs and build/exit evidence. Excluded bulky source/sdist/virtual-environment
directories are explicitly indexed as omitted; no omitted artifact is represented
as included. Reproduction commands are in the report and archived scripts.

I5 semantics, original pre-affinity types, permissions, dependencies, complete-unit
rollback/replay and all routing must be independently accepted before replacing
both Transfer fences. I6 Wire remains separate. **Task G Medium G-R1 remains an
unresolved mandatory I7 obligation.** I8 Query/Search and final V1/V2 remain
separate. This review PR authorizes no merge, release, deployment, P8 or real
Provider/catalog operation.
