# Independent exact-tree review: third I3 candidate

Reviewer: read-only subagent `/root/i3_invariants` (no production authorship).
Target HEAD `8f7036d1f44bb2725a8744d8db0810babf82158c`, tree
`06552bc384889f3b8a8271eb3777cfb93068bc94`, committed and pushed.
Verdict: **CHANGES REQUIRED**. The previous original relation timestamp finding
was confirmed fixed. Three additional counterexamples were executed:

1. Existing collection identity excludes scope JSON. Rebinding that scope failed
   only during Context admission, after an independent Core OID committed.
2. A comments collection could cite a genuine registered child of another Issue;
   constructor-only preflight missed the writer's modeled parent validation.
3. GitObservation's immutable UNIQUE identity includes Repository, kind, scope
   and provenance, not only the Capture pair. Legitimate reports from the same
   Capture for two Repositories were incorrectly rejected by the narrower map.

A subsequent read-only work-in-progress scan reconciled the other Core UNIQUE
bindings (Repository/Scalar/Relation/Notes assertions), Source/service checks and
protected Notes reads. It executed one further malformed-key counterexample:
Notes role/retained rows could claim another root while proof admission silently
reconstructed the original Capture root. This scan is not labeled an exact-tree
approval; the following pushed revision is the final review target.

Corrections preserve the actual I1 PK/UNIQUE distinctions, check existing immutable
payloads before binding, validate modeled member ownership and Source/service
scopes, and require the wire Notes root to equal the original Capture root.
The protected Notes provenance query is owned by a checked typed GitCore reader.
Coverage details remain advisory/nonsemantic under I1; differing details on
semantic duplicate replay do not become a new immutability policy.

The expanded regression suite includes both invalid internal/existing payloads
and valid shared-Capture/multiple-Repository reports. Final acceptance, including
its exact pushed SHA/tree, is recorded separately in PR #108.
