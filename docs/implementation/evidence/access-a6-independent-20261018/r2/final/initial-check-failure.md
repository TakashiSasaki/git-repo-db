# Initial final-binding helper failure

The first `verify_binding.py` execution exited 1 at an overly broad assertion:

`assert new_tests.startswith(old_tests), "Existing regression assertions changed"`

All 16 production/dependency/skill blob comparisons and the source-change set
check had already passed. Inspection of the actual test diff found one newly
added `GitNotesSource` import near the top, plus appended new tests. That import
invalidated byte-prefix equality without changing any existing test function.

The helper was corrected to compare the AST (including decorators and assertions,
excluding only source positions) of every original top-level function. The
corrected helper passed. No product source, test, or original execution receipt
was edited; this was a binding-helper assumption failure, not a product failure
or a runtime test rerun.
