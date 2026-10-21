# Pre-freeze harness correction

The first development run reached 8/9 case groups. GA05 expected the substring
`immutable` for endpoint DELETE/REPLACE, but the retained baseline guard correctly
refused it with `only dominated current candidates may be deleted`. The harness
assertion was corrected to require the real SQLite refusal without the wrong
message substring. No SQL constraint was weakened. This receipt preserves its
pre-freeze input hashes and actual failure; it is not authoritative final-run
evidence. Later cases and assertions were added before the executable freeze.
