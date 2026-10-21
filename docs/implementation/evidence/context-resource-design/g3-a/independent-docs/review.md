# Independent final documentation review: G3=A integration

**No blocking or substantive finding. Documentation is ready for owner design
acceptance, conditional on the separately required independent SQL execution
review and final publication checks.** This is not owner acceptance of ADR 0031,
production implementation approval, release qualification or merge authorization.

## Independence and frozen input

The `independent_docs` reviewer authored none of the revised documents, candidate
SQL, UDFs, author cases or receipts. Review used a detached worktree of commit
`4c07cb8ecc4d744ddfb8c3908deb91d8ad72f6f9`, tree
`e171de9f2459b0ade409bebb40787b850d88ff5e`, without changing the reviewed tree.
The update base was `3e6debe41f8e75f0a75be3a71cb1b12a0b70f0f5`; the actual #113
stack parent was `24f593861327328fa00dab0b83f956cec330a0ac`.

Read sources included root AGENTS.md, ADR index/policy and accepted ADRs
0017/0028/0029/0030, the revised ADR 0031/schema/handoff, current evidence map and
index, new G3 candidate SQL/helper/connection and Admission boundaries, unchanged
main Context schema and Repository-relation contract, F2 executable manifest
`9eeacb28f7e4a426114a9ce40e2324b4da302817` and R2 semantic-gap report
`8ab57eb74068f5ba303b5985a335f0f76be4fdd2`. No accepted ADR was edited.

## Contract assessment

- G3=A is explicitly dated 2026-10-21. Native I7 is E's semantic Issue only for
  Q-S10 Timeline Event/Transfer. Lawful attributed I8 reports remain retained;
  their support for E is permanently ineligible, not awaiting qualification.
  Missing correct-I7 resources/reports remain dependency failures requiring
  original-report re-supply. Matching I7 is necessary and insufficient by itself.
- A3/B3/U1=B/U2=A/U2-E2/U3=C′/U4=B/U5=A remain fixed. ResourceKey, recursive
  String/Array-only canonical Identity, genuine empties and PR coordinates,
  one G2 Parent-ID-TEXT encoding, independent Documents/children, unknown kinds
  and no known-input fallback remain preserved.
- Parent authority remains `resource_relations`. Native metadata and generated
  support projections add no independently writable Parent source. The extra
  native-I7 composite FK retains the existing full ParentReport FK and complete
  EventReport endpoint FKs. General Parent inequality and child-before-Parent
  remain permitted. Obligations 3/4 expressly require direct-SQL I8 rejection.
- SQL FK/CHECK/generated/trigger/UDF guarantees remain distinct from optional
  Admission. The mandatory UDFs are bounded row-local deterministic functions;
  connection settings are explicit. Parent/Event provenance, clocks and original
  observation times can differ; endpoints within one EventReportKey remain
  coherent. SQL does not authenticate Providers, recover original input types,
  enforce arbitrary JSON-member referents or promise arbitrary-SQL whole-unit
  atomicity. Admission owns actual event eligibility, original time types,
  declared members, endpoint completeness and transactional whole-unit rollback.
- Five stores, permanent Repository UUID, Core INSERT-only, Context Mapping
  authority, Access authorization separation, six Repository roles, claims and
  Dispositions, Source positives, five-column Coverage, selection and classified
  times remain preserved. No Witness/Publication/surrogate/new Link store appears.
- D0 is decision integration/SQL proof/independent review, not a new choice.
  I1→I2→I3→I4→I5 is coherent; general I6 depends I1–I3 and its Transfer part
  I4/I5. I7 depends I1–I6 persistence. I8 basic reads can parallelize after I1–I3,
  while Transfer/final integration follows I4–I7. V1 applies stagewise; V2 follows
  all units and requires both installed distribution forms outside checkout.
- Main's PR #112 integration is independently confirmed by the merge commit and
  effective tree. ADR 0031 remains unimplemented. Nineteen Context tables is a
  measured result rather than an absolute new invariant.
- `status: proposed`, `date: null`, `replaces: []` remain intact. G3 selection is
  not a whole-ADR acceptance or invented conversation approval. Old F1/F2/R2
  receipts retain their original meaning; F2's structural I8 success and temporary
  `QualificationRequired` remain historical. Current documents do not reopen A/B.

A nonblocking editorial precision was suggested to the author: label the index's
ADR 0030 lead paragraph as the latest **accepted Context ADR**, since G3=A is a
newer scoped selection recorded in still-proposed ADR 0031. This does not change
or obstruct the current decision ledger.

## Independent checks and evidence inspection

`check_docs.py` / `checks.json` record both diff scopes, unchanged production and
accepted ADR paths, unchanged old reviews/receipts, strict UTF-8/nonempty text,
JSON/fences/frontmatter/index, all fixed ledger choices, 113 local-link occurrences,
14 anchors and 28 fixed Git-blob targets. All passed. These counts describe this
review's scanner and are not added to another review's counts.

All 18 F2 inputs match their manifest at both F2 and R2. All ten new executable
input hashes match the new manifest. Pure SQL-text composition matches
`ee8618874d061b8fc71bf83be94a10b1d009d7d1859ddd145e560c7755c41cd0`; this review
opened no SQLite database and does not call text reconstruction a runtime test.

`author-receipt-checks.json` independently verifies compressed and raw artifact
hashes, author freeze/tree bindings, actual SQLite 3.51.3 and 3.53.1 source IDs,
11 passed groups/292 steps per runtime, and the direct-I8 SQL statement's actual
`SQLITE_CONSTRAINT_FOREIGNKEY` extended code 787 with unchanged before/after
rowsets. This is independent receipt inspection, not independently authored SQL
execution. That separate requirement belongs to `independent_final`.

Production replay/import/recovery, paired Backup/Recovery, Search integration,
packaged DDL/UDF/fingerprint and isolated wheel/sdist-derived-wheel acceptance
remain explicitly unexecuted for the generalized format. Final feature/test-merge
parents/tree and Development CI must be checked at the published HEAD, without
borrowing any earlier green result. Material changes after this freeze require
review; factual result/link additions should be separately bound and rechecked.
