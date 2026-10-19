# Independent exact-tree review: second I3 candidate

Reviewer: read-only subagent `/root/i3_invariants` (no production authorship).
Target HEAD `1cd58cec6fa511a37dcf11ad01d37c22d903d41e`, tree
`5052c06505b860bdac3762f6f44451241e1da750`, committed and pushed.
Verdict: **CHANGES REQUIRED**. Reviewer independently ran 39 I3 tests and four
schema/registration/ownership audits successfully. Both first-review findings
were confirmed fixed. A new executed blocker remained:

A package containing two Resource--Repository relation rows with the same complete
ClaimKey but different original observation timestamps passed preflight, bound its
PackageKey and committed an independent Core OID before Context rejected replay.

Correction: validate complete direct-key/payload consistency across all incoming
row sections before binding, including whole EventReportKey consistency. Compare
existing original relation/field/resource-relation timestamps, MappingDisposition
payloads, Capture/GitObservation identities and complete Transfer endpoint sets
before binding. Provider/Source immutable identity is checked separately from
mutable nonsecret registration configuration. Regressions exercise internal
contradictions and receiver-existing conflicts before independent Core admission;
a shared-OID test preserves two distinct Repository membership reports.

The subsequent exact pushed review and final verdict are recorded in PR #108.
This historical record is retained and does not approve either candidate.
