# P5 installed-test fixture correction

The broad, previously omitted cohort exposed four failures in the unchanged
`test_p5_installed_acquisition_and_exchange` nodes (SHA-1/SHA-256 × direct
wheel/sdist-derived wheel). Independent reproduction failed before Provider
admission because the fixture supplied the deliberately retired
`ProviderPullRequestIntake(repository_uuidv4=...)` argument. The corresponding
main baseline passed with its historical API. This is stale test integration,
not evidence for restoring that API or a production implementation defect.

Before editing, `original-four-counterexamples.json`, the independent
`p5-installed-repro.log`/XML and original test source were preserved here. The
full complementary cohort's original failure inventory and reconciliation are
also retained. Historical acceptance receipts remain unchanged.

Only `tests/packaging/test_p5_distribution.py` is corrected. The fixture now
reports actual Provider Repository IDs separately for PR base/head and supplies
an explicit `represents_repository` Mapping claim. It asserts both typed roles,
the exact original MappingClaimKey support, target UUID and complete
sender/receiver role/relation equality. Existing Git acquisition, Provider
resource admission, Exchange section/admission and received Core metadata
assertions are preserved. Exchange requests explicit all-selection intent and
receiver Repository permission with a new RequestIdentity; Operational remains
explicitly initialized. No production code, skip, xfail or test removal changes.

`corrected.log`/XML record 4 collected, 4 executed, 4 passed, 0 failures/errors,
0 skips/xfail. Each isolated installed environment was independently inspected:
Python 3.13.5 and actual SQLite 3.51.3. Builds, venv creation and installs use
offline mode. `correction-receipt.json` records the exact command, SQLite source
ID, parent commit/tree, pending test file digest and artifact SHA-256 values.
The final commit must separately bind this pending correction before review.
Direct and sdist-derived wheels have identical SHA-256, also identical to the
original product wheels; this correction changes the source test, not shipped
implementation. Ruff lint and format checks pass.

The first development run reached the new typed assertions but its additional
Mapping round-trip assertion incorrectly compared the facade's
`ResolvedRepositoryRelation` wrapper directly with the domain relation. All
four failed that new assertion, with identical stored sender/receiver rows.
The assertion now unwraps `.relation`; the unsuccessful development log/XML is
retained as `development-wrapper-assertion.*` and is not claimed as acceptance.

Reusable lesson: expanding a CI cohort must reconcile every omitted installed
test against current supported APIs, and preserve its original semantic checks.
Removing a stale call alone can accidentally stop testing Repository identity;
use actual Provider role reports plus explicit Mapping support and compare the
complete received relation keys. The root agent owns any repository skill update.
