# ADR 0031 I6-B: generalized v5 wire and finite dependency plans

This implementation follows the accepted [I6 boundary contract](adr0031-i6-wire-admission-exchange.md)
and [stage allocation](adr0031-i6-change-map-and-handoff.md). It is directly
stacked on independent I6-A review #149, frozen at
`ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00`, tree
`e7ca7e361b8b766f1976a12fc84d5cc50ac32232`. That review's scoped PASS closes
ORIGINALS-M1 and I6A-IR-L01; its historical execution evidence is unchanged.

## Public pure interfaces

- `exchange.decode_package` / `encode_package` implement only
  `git-repo-db/adr0031-exchange-v5`. They validate the exact envelope and row
  profiles, canonical Resource identities, strict JSON values and canonical-data
  SHA-256. A parsed package is still untrusted input, requiring typed semantic,
  dependency, selection and current authority checks before admission.
- `ResourceIdentification.to_wire` / `from_wire` preserve all seven named
  Resource columns through the existing identity/identification authority.
  Namespace coordinates register no Parent and create no traversal edge.
- `context_wire.decode_context_v5` / `encode_context_v5` validate a whole Context
  section using those row profiles and the existing typed Context validators.
  The section API has an explicit v5 name; untrusted complete packages first
  require the envelope API to check their version and digest.
- `context_dependencies.plan_context_dependencies` creates an in-memory finite
  selection plan of whole original semantic units and typed omissions. It never
  issues authorization or stores withheld reports. `prior_work` carries actual
  work already spent within the same explicit request; retries must retain it.

Malformed known contracts have no global/opaque fallback. Parent originals are
looked up only by their complete original key; their time is read from that exact
Parent row. Endpoint declarations and full Event references survive unchanged.
No Event clock, provenance, endpoint row subset or transport completion supplies
missing original evidence.

Relation and Collection member order remains significant. Real terminal
alternatives, Source set inventories and Coverage proofs retain their original
coordinates and states. Withholding a required member or terminal alternative
withholds its whole unit and dependent completeness; it never shrinks a complete
report or manufactures an empty terminal. Resource registrations remain
independent of their semantic reports, including lawful cyclic graphs.

## Scope and remaining integration

I6-C owns Provider normalization, application export/import, receiver-local
selection/authorization composition and replay. I7 owns stored/recovery
revalidation and pairing; I8 owns query/Search consumption. Both exact Transfer
SQL fences and the existing service-bound AdmissionContext/current checks remain
mandatory. The ordinary unwired routes remain fail closed. The new pure codec
and planner confer no operational capability and do not activate Transfer.

The Author team validates this implementation; this is not the separate
non-Author I6-B review. The parent will request that later review after verifying
the submitted PR and HEAD. No next stage is started here.

See the [new Author evidence](evidence/adr0031-i6b-author-20261023/README.md),
[requirement/test matrix](evidence/adr0031-i6b-author-20261023/MATRIX.md), and its
run-specific source, command, exit, JUnit/journal and distribution bindings.
Development CI Success is limited to its selected checks; complete Release
acceptance requires separate independent local and hosted validation and is not
claimed by this stage.
