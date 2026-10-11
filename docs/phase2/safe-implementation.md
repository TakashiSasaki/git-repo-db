# Determined corrective implementation

These changes are a coherent corrective PR stacked on the investigation. They
preserve existing accepted semantics while the proposed replacement architecture
awaits owner decisions. They do not implement the proposed publication, collection,
cache, lifecycle or wire model.

1. **Presence:** selected nested provider fields omitted from a supplied actor,
   review-parent or commit object remain unasserted. Explicit null still has its
   existing meaning. Existing admission preserves the original retained field's
   module/version, capture, clock and receiver-local checks.
2. **Observation truth:** a known, in-scope current-resource response rejected at
   200 contributes partial evidence at 200. Retrying at 175 cannot manufacture
   complete200. Actual committed prefixes, cancellation fences, terminal restart
   and watermark times retain their existing meaning. Custom response adapter
   clocks receive signed-int64 validation.
3. **Completeness truth:** historical complete-marker proof checks contiguous
   unique ordinals, intermediate continuation and final terminal boundaries.
   Existing accepted-error GraphQL retry requires exact raw/current root pairing
   and physically verified, unquarantined error evidence. Only the existing typed
   current-receipt thread-comments child path is allowed to be rawless within this
   historical path. Ordinary current-marker and 304 proof keep their separate
   established contracts. Incomplete or selectively exchanged proof remains
   unavailable while valid facts survive dependency staging and late promotion.
4. **Bounded Exchange work:** after clearing stale barriers and recomputing genuine
   pending selection scopes, conflict-free refresh returns before unnecessary
   repository-wide dependency materialization. Actual conflicts retain their full
   propagation checks. The Phase 1 exact closure and scaling behavior survive.
5. **Indexed publication:** seven result-led indexes make existing historical
   immutable output sealing proportional to the publication's outputs rather
   than all unrelated histories. No identity, output, selection or lifetime changes.

The machine-checkable dependency audit and disposition/field tools live in PR A;
PR B exercises its exact Schema 19 composition separately. Schema 19 is an index
and fingerprint revision of the existing runtime, not adoption of the 69-table
candidate. The built-in certificate is regenerated only while its historical
eligibility consumer remains reachable; its eventual removal remains required.

All production fixes originated in disjoint worktrees and received independent
counterexample review. See [review](independent-review.md) and
[evidence scope](verification.md). Final exact-tree acceptance and hosted status
are recorded in the submitted PRs; focused development receipts are not final
runtime acceptance.
