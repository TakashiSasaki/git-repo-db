"""Kinds outside document-only PR acquisition and query coverage.

Collection names and saved scope names share the same classification. Unknown
kinds stay relevant so newly introduced acquisition work fails conservatively.
"""

CODE_KINDS = frozenset(
    ("pr-git", "pr-code", "code", "commits", "files", "pr-commits", "pr-files")
)
TIMELINE_KINDS = frozenset(("timeline", "pr-timeline"))
NON_DOCUMENT_KINDS = CODE_KINDS | TIMELINE_KINDS


def document_scope_includes(kind):
    return kind not in NON_DOCUMENT_KINDS
