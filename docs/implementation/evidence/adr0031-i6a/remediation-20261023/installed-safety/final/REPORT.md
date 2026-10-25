# Final-source installed I6-A safety verification

Both direct-wheel and independently rebuilt sdist-wheel lanes freshly build,
install and execute source `93d9927ae801d5402aab0aa0c7c270eeab2809e6`, tree
`0c8a50e7cc23b98c6e7e2d1e6066077cbe8d203a`, with 551 PASS each, process exit 0,
zero failure/error/skip/xfail/xpass, and exact collection/JUnit/journal/phase
reconciliation. Each selected set equals the entire historical 551-node set;
no historical identity is omitted or replaced. Separate earlier 423e345 receipts
under `../after/` remain unchanged and are not used as a final-source rerun claim.

The adapted `safety-driver.py.txt` is archived here. It uses the frozen clean
checkout's helper, an external test directory and explicit pytest configuration.
The pytest process itself checks installed product module origins and every
Python/SQL/JSON file hash at session start/finish, as well as effective config
and test-support origins. Both wheels contain no test/harness tree. All product
imports resolve to the relevant new venv, and source/wheel/installed maps agree.
Dependency installation is offline against the verified locked wheelhouse.
Only the copied network guard appears on `PYTHONPATH`, with no product source.

Each lane measures Python 3.12.14 and actual environment SQLite 3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Exact Context schema, original SQL Transfer fence definitions (both present),
fingerprint, empty foreign-key check and `integrity_check=ok` pass. No SQLite
replacement or version matrix was prepared. Normal Transfer stays staged.

The wheel and sdist-derived wheel each have 777887 bytes, SHA-256
`53f628499da0f47f72d8236e433bd0f02093202a638dbb1f657e3301891ec359`.
The fresh source sdist has 92582574 bytes, SHA-256
`1ab614a13cf92b583050af614c9600740ae6a42c7edd5211595dee906cb774e3`.
The independently built CI-equivalent runner artifacts have the same hashes.
Complete frozen tracked-source and sdist-member manifests are included; full
artifacts, build trees and venvs remain external. Compression indexes bind every
original and gzip byte count/SHA-256.

The 551-node cohort includes I4/I5 and overlaps their separate final installed
217/29 runs. It does not include or turn the separate original Access smoke's
intentional I6-C export refusal into a PASS. See
[the installed harness report](../../installed-harness/REPORT.md) for those
failures and unexecuted downstream assertions. Concurrent ordinary-suite work
excludes sequential performance comparisons. This is supporting Author
verification, not independent acceptance or complete release qualification.

The execution used these environment bindings with the selected environment's
already prepared locked venv: `I6A_HARNESS_ROOT=/workspace/i6a-final`,
`I6A_SOURCE_COMMIT=93d9927ae801d5402aab0aa0c7c270eeab2809e6`, and
`I6A_ARTIFACT_OUTPUT=/workspace/i6a-runs/safety-installed-final`. Replays must
choose a new empty artifact directory and an exact frozen checkout with its own
venv. Do not reuse an old output directory or substitute source product imports.
