# Task C publication and disposable SQL evidence

Read the preserved [implementation plan](I2-IMPLEMENTATION-PLAN.md). It contains
the nine requested deliverables: file-level changes; schema/UDF contracts;
index/FK dependencies; adversarial matrix; staged PR dependencies; independent
review gates; packaging/fingerprint requirements; I3–I5 deferrals; and the
distinction between engineering choices and genuine accepted-ADR conflicts.

The plan is SHA-256
`ed40739a0a634623d37a4db44f26a27cc356675e6705ecd6ec7292f7f4e322ed`.
The [original evidence archive](i2-preparation-evidence.tar.gz) has 75 members and
SHA-256 `a90d56232809577812339ac8531896fce807eada9c54c92334500e81afd68e04`.
Its [original index](artifact-index.json) binds 74 original files; the archive
also includes that index. [Publication binding](publication-binding.json) verifies
all indexed members and the unchanged published copies.

Readable inputs are [Resources SQL](resources.sql), [SQL predicates](resource_udfs.py),
[composer](compose_proposal.py), [133-case probe](probe.py), [runner](run.py),
[actual-product baseline controls](baseline_controls.py) and
[transaction controls](transaction_controls.py). They are external prototype
inputs, never imported by product initialization. The full composed proposal in
the archive has SHA-256
`c8fd84cf5e535d5f4c585d31a2e0ad0e4c791bb9cd7649f243e0bc1c6bfd223e`.

[Summary](summary.json), [runtime provenance](provenance.json),
[exact commands](COMMANDS.md), [minimum command receipt](minimum-command.json),
[newer command receipt](newer-command.json), and
[final source binding](final-binding.json) retain the original observations.
The archive contains full SQL traces, real exceptions/codes, pre/post rowsets,
runtime source IDs/options/pragmas, transactions/reopen evidence, all 3,697
tracked source hashes, the initial failed prototype and intermediate freezes.
Neither the failed attempt nor earlier counts were rewritten as final results.

For reproduction, extract the archive into a fresh disposable workspace and
provide its `repo/` checkout at exact #118
`9ea69ba8804a368802457950601a5a4027174c52`. Prepare the two interpreter/runtime
paths described in COMMANDS and provenance, then run its preserved helpers.
Its `run.py` derives paths from the extracted workspace; invoking the copy in
this documentation directory without that workspace is not a configured run.
The original plan's relative artifact links resolve after extraction; its
`minimum/composed.sql` and full receipts reside in the archive. Choose fresh output
directories for reruns and verify actual source IDs before counting results.

The freeze predates this publication: statements that no PR was opened describe
the original preparation. The owner's later request authorizes this separate
Draft PR. Original reports, product code, accepted ADRs, previous branches and
historical execution records remain unchanged. No merge, release or P8 activation.

The [suggested skill lesson](suggested-skill-lesson.md) remains a recommendation
for a future authorized implementation owner to validate. Publication does not
convert a disposable design proposal into a verified production procedure.
