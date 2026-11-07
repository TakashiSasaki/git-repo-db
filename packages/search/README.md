# Optional authority-verified Search

Install `repo-catalog-search` with Core or Context. Use
`CoreSearchService(..., mode="core_only")` from `repo_catalog.application.core_search`
or `ContextSearchService(..., mode="context_only")` from
`repo_catalog.application.context_search`. Each minimum needs only its selected
concrete authority plus Search/runtime/contracts. Paired Search additionally
requires the existing paired Query integration; rich entry points remain composed.

The existing opt-in Query CLI adds `search` and `search-rebuild` only when Search
is installed. Reads verify against pinned authority and use scan fallback for
absent/stale/incomplete/corrupt indexes without creating or repairing them.
Only explicit rebuild creates/replaces derivative state. Ordinary Schema21,
authority admission/recovery and Transfer activation are unchanged.
