# Independent owner-decision design review

Reviewed commit: `7d2e736f6fd4aa5e30417fb99fa72d27f93ea270`.
Tree: `a490216b849c59e050814e12d02e4d524bde0163`.
Reviewer had no production/test/design edit ownership.

Read ADR0028 and changed AGENTS/index/technical-contract/three-store-invariants
skill against owner task, ADR governance/index, ADR0001/0003/0011 and relevant
scope/key/origin/recovery contracts. The new record accurately distinguishes
owner acceptance from unmerged PR approval and future implementation/test results.
The earlier universal time convention was in agent/implementation summaries;
the new semantic input restrictions preserve generic signed conversion and native
Git meaning without claiming to retire unrelated old ADR clauses. Optional/null
observations and required positive Coverage/terminal coordinates are separated.
SHA-256 comparison is required, with no origin authentication or HMAC claim.
Public Schema21 remains unchanged; shared corrections are one identical ancestor
of independent P5/P6 siblings.

Executed read-only commands from `/workspace/work/design`:

- `git status --short` — clean.
- `git rev-parse HEAD` and `git rev-parse HEAD^{tree}` — identities above.
- `git diff --check HEAD^ HEAD` — exit 0.
- `git diff --name-only HEAD^ HEAD` — five intended design/policy/skill files.
- Full content review of ADR0028 and exact changed documents.

No substantive design blocker. Follow-up tracked: replace the historical v1
wire starting point with the precise corrected wire definition; replace the
contract's temporary-integration-branch-only description with the formal
tests-only PR route when the integrated tests are submitted. This is a review of
the owner decision record, not runtime verification or release acceptance.
