# I6-B Author validation

This directory records the new generalized v5 codec and pure finite Context
planner implementation, stacked directly on #149 at
`ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00` /
`e7ca7e361b8b766f1976a12fc84d5cc50ac32232`.

The [requirement/test matrix](MATRIX.md) maps R02–R09 and V01–V09 to the
I6-B allocation of T01–T27. [Exact synthetic vectors](vectors/manifest.json)
record their actual bytes and SHA-256, including a deliberately rechecksummed
invalid V08. Initial GitHub/base/duplicate checks and environment setup attempts
are under [initial](initial/attempts.json).

Author implementation and exploratory tests precede a frozen execution commit.
Run-specific source, full regression, installed-form, command/exit, JUnit/journal,
input-inventory and comparison receipts are added after that freeze. Unbound
exploratory logs are retained as diagnostics, not frozen-source acceptance.

No independent I6-B review, full hosted Release acceptance, I6-C/I7/I8
implementation, normal Transfer activation, merge, release or deployment is
claimed. Both exact Transfer SQL fences and service-bound current authority
checks remain required. The parent requests the independent review separately.
