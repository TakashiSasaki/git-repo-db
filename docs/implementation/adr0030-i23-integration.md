# ADR 0030 I2 + I3 integration and I4 handoff

This branch integrates I2 PR #109 and I3 PR #108 without changing either parent.
It starts at I2 `9b8a6ad9b761bf23b45eda9f84d639569cee56ef` and merges I3
`5c5b816998f7051703ca400e8cfeab377254c435` with both histories preserved.
The actual merge-base is I1 `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7`.
The two-parent merge is `6dccd3c3bc4919975117a9cea80818936f2b9a5e`, tree
`269c3eec3598e8eb1cf63a70b80a67ce2eb26104`; Git reported no text conflicts.
The earlier temporary tree `ae6287b8cf91d1b8efa772fb46763bcbd9325076` is
prior evidence only. This task tests its own committed inputs.

## Integration changes

The original five `tests/integration/p5/test_exchange.py` nodes are preserved.
Full preservation/reverse/onward tests explicitly select all intended domain
facts. The selective Core test independently selects R and O with empty C;
the Context dependency test selects all Context but no OIDs. Reception explicitly
requires Operational initialization, original Repository UUID permissions and
proper request issuance/continuation. Exact resend uses the original request;
a separate request cannot rebind an existing PackageKey to another digest.

Tampering uses complete v4 row envelopes, new package IDs, and recomputed valid
canonical checksums so native integrity, text digest and excluded ordinary blob
checks are actually reached. These tests assert their specific refusal codes,
not merely an earlier selection/checksum failure. No compatibility path, skip,
xfail or test removal is introduced.

`tests/integration/i23/test_provider_exchange.py` supplies actual native Provider
payloads to I2 and passes the committed normalized domain through I3 into a
separately seeded Catalog. It covers current Issue ownership, PR base/head,
original decimal/Node namespaces, exact MappingClaimKey support, conflicting
mappings, receiver-local Disposition re-evaluation, original EventReportKey and
whole Transfer endpoints, missing/null/unresolved/selection omissions, clocks,
provenance, Source/Coverage, Core OIDs, Capture and Notes. A real independently
configured Access store with a local approval stays byte-identical at both ends;
its configuration/credential-reference canaries do not enter the wire.

The installed distribution smoke now also chains actual I2 intake through I3,
including a Node-ID Transfer endpoint, into a different seed. It runs in both
direct-wheel and sdist-derived-wheel environments outside the source tree.

The minimum-SQLite CI cohort is extended with i23; all former targets remain.
Packaging, audits and node reconciliation run even when pytest reports existing
P6 failures. The pytest failure still fails the job; no continue-on-error,
expected-failure allowlist or green-acceptance substitution is used.

## Fixed I4 interfaces and limitations

Use the I2 `Context.provider_repository_roles(resource, evidence=...)` result for
**current** ownership/base/head. Materialized `repository_relations()` can retain
an old Core-target observation after a newer unresolved Provider owner arrives.
The integration counterexample asserts both facts together: the old Core-target
row remains evidence, while the current Provider role is unresolved with its
new original clock/provenance. Never fall back to the old row as current truth.

Preserve I1 `ResourceRepositoryRelation`, `MappingClaimKey`,
`MappingDisposition`, `ProviderRepositoryScope`, `TransferEventReport` and
`EventReportKey`. Current qualified effect needs genuinely available receiver
`MappingOperationEvidence`; a sender evaluation is not receiver evidence. Do not
add Witness storage, fabricate NULL, rewrite keys or choose a conflict winner.

I3 exposes `ExchangeSelectionScope`, `ExchangePackage`, `ExchangeImportReport`
and the matching `ExchangePort`. R/O/C are independent, `()` is explicit empty,
and omitted selection requires explicit all-selection intent. The sender seed
never replaces receiver store identity. Permissions cannot expand through FKs.
Package binding lives only in Operational; domain commits and checkpoints are
separate stages, and crash retry inspects real facts. Operational loss cannot
resume an old request or bypass P7 Stop. Checksums do not authenticate origin.

I4 owns Query/Search projection and backup integration of these qualified reads.
The known 27 P6 legacy `Context.admit_repository()` failures must be fixed there,
without reviving the retired API or weakening Core/Context/Access invariants.
The integration evidence records the actual remaining failures rather than
claiming full runtime/release acceptance.

## Review and verification

See [the integration evidence](evidence/adr0030-i23/README.md) for exact source
bindings, selected/executed nodes, actual SQLite versions, full failure inventory,
CI URLs, build/install receipts and the independent read-only review. Historical
I1/I2/I3 receipts are unchanged and do not substitute for these runs.

Recommended dependency order: I1 #107, I2 #109, then this integration PR. I3 #108
is a second history parent already contained here; merging this PR preserves its
commits. If #108 is merged separately after I1, recheck effective trees before
merging I2/integration. Do not squash away the second-parent history without an
explicit new plan. I4 should start on this reviewed integration HEAD. No merge,
release, P8 activation or real-catalog operation is performed by this task.
