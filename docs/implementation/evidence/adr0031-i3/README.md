# ADR 0031 I3 author evidence and review handoff

The [implementation contract](../../adr0031-i3-parent-reports.md) defines the
complete report key and the scope of this implementation. The final author
report, machine summary, indexed raw evidence archive and publication binding
are stored alongside this guide. Counts from overlapping cohorts are separate;
ordinary development CI does not establish whole-product acceptance.

Reproduce with the unchanged `uv.lock` dev/docs groups, a dynamically linked
Python >=3.12, and actual official-source SQLite 3.51.3 and 3.53.1. Build commands,
source URLs/archive hashes and measured source IDs are retained in the raw
runtime receipts. Verify version/source ID in child processes before testing.

```sh
python scripts/verify_i3.py --sqlite 3.51.3 --output /absolute/new-evidence
python scripts/verify_i2_sql_counterexamples.py /absolute/repo 3.51.3 /absolute/new-sql-evidence
python scripts/build_p1_schema.py --check
python scripts/audit_p1_schema.py --check
python scripts/audit_callsite_dependencies.py --check
python scripts/audit_context_registration.py --check
```

Repeat on actual 3.53.1. The broad runner intentionally exits nonzero while the
79 inherited Transfer/Wire staging cases remain non-successes. It records full
ordinary collection, exact selected nodes, phase journals, JUnit and process
exit, plus the dedicated Parent subset and raw SQL traces/full final rowsets.
The dedicated subset overlaps broad regression and is not added to its unique
node count. The active I2 SQL diagnostic retains 301 groups with lawful Parent
fixtures updated to the I3 scope; historical archives are unchanged.

Both direct wheel and sdist-derived wheel must be built from a clean archive of
the executed commit and installed outside checkout on both runtimes. Copy
`scripts/verify_i3_distribution.py` outside checkout before running it; its
`--output` receipt checks import origins, bundled schema/fingerprint, UDF/index/FK,
child-first/resupply/policy/replay, alternatives and direct SQL reference refusal.
The original I2 and Access distribution probes retain their separate results.
No later assertion after an Access Transfer-stage refusal is credited.

A non-author reviewer should independently inspect and execute against the exact
frozen product inputs: DDL/UDF/registration/fingerprint consistency, complete-key
references, NULL subtype absence, conflicts and immutable original times,
permission/selection replay, whole-unit rollback, sole authority and lawful I8
storage. The reviewer must keep I4 native-I7 SQL, I5 typed Transfer admission,
I6 wire, full I7 Recovery/G-R1 and full I8 Search separate. G-R1 is explicitly
open: direct FieldCandidate reads do not establish full Recovery guarantees.
No merge, release, deployment, P8 or live catalog operation is authorized here.

## Published final results

Read the [author report](REPORT.md), [machine summary](summary.json) and
[all-79 failure classification](failure-classification.json). The executed product
HEAD is `61c87ced5245caf3a991592a8eb745eef7126177`, tree
`6f259f7239d7330bea4d1dd1b6e04c316561728f`. Both runtimes execute all 2,891
selected nodes: 2,812 pass, 59 call failures and 20 setup errors. The overlapping
65 Parent tests and separate 301 SQL diagnostic groups pass on each runtime.
The 79 inherited nodes/phases are unchanged; none was deleted/skipped/xfail'd.
They remain I4/I5 Transfer and I6 Wire dependencies; full product acceptance is
not claimed. All four installed I3/I2 probes pass; original Access smokes still
exit 1 at staged Transfer. G-R1 remains open for I7.

The [independent non-Author review](INDEPENDENT-REVIEW.md) concludes **PASS for
bounded I3, unresolved I3 findings 0** on that exact product HEAD/tree. Its
[summary](independent-summary.json) separates its independently executed
206 pytest cases and 37 authored probe groups per runtime, plus all four fresh
installed combinations with 37/37 groups, from author evidence and receipt-only
comparisons. It does not claim a second broad-cohort or G-R1 rerun.

- [Author archive](author-evidence.zip): 4,930,554 bytes; SHA-256
  `e2ea5ab3e366ad9216dc9299c204452ea897dea651b6def7d96c928328ffd2af`.
  All 424 payload members verify against the [index](artifact-index.json).
- [Independent archive](independent-evidence.zip): 82,266 bytes; SHA-256
  `a3d248267de92d28e7a7d682f6b3e8bddb135c366ed3ec03b4330766db6e6815`.
  All 57 payload members verify against the [independent index](independent-artifact-index.json).

Archived summaries retain their original author/prepublication context. This
publication copies the independent report and evidence byte-for-byte. Later
evidence-only commits preserve the executed product inputs; the Draft PR body
records the actual final publication HEAD/tree and the unchanged-input binding.
