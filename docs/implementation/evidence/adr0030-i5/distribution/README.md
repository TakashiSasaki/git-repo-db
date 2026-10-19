# I5 independent distribution and static audit

Reviewed implementation: commit `a54cb218226e3c91c44e979ee0df0543ea459502`,
tree `cc2eafaaeb8e3305270c17e74ae69edc42c0a50b`.
This receipt describes an independent execution, not historical evidence updates,
merge approval, activation or a release.

## Runtime and commands

`/workspace/i5-runtime/python` runs Python 3.13.5 with
`LD_LIBRARY_PATH=/workspace/i5-runtime`; the dynamically loaded actual SQLite is
3.51.3, source ID
`2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
No SQLite version override, real credentials, real-user Catalog or network
acquisition was used. Local synthetic Git fixtures were created in temporary
folders. Official SQLite release download and package installation were setup,
not product network acquisition.

Reproduction entry points retained here:

- `/workspace/i5-runtime/python run_distribution.py`
- `/workspace/i5-runtime/python run_static.py`
- `/workspace/i5-runtime/python run_access11.py`
- `/workspace/i5-runtime/python -m pytest -q test_access11_cross_seed.py`

The runners currently name the execution checkout/output directories explicitly;
when reproducing elsewhere update those two path constants. `commands.json`
retains every build/install/smoke argv and working directory. Source checkout was
editable-installed by the locked environment. Artifact probes ran `python -I`
from outside the checkout, imported only their wheel's site-packages, and
intentionally installed `--no-deps` to verify offline surfaces do not import the
HTTP client. The source locked environment has the declared `httpx` dependency;
`uv pip check` verified all 49 installed packages compatible. Minimal artifact
environments intentionally omit that declared HTTP dependency and do not claim
to test Provider network transports.

## Distribution result

Three scenario executions passed: source checkout, independently installed direct
wheel, and independently installed sdist-derived wheel. These are executable
assertion-based probes, not pytest nodes, and are counted separately from pytest.
Both wheels have equal member sets, equal payload bytes and identical whole-file
SHA-256. Source and both installs agree on all four composed P1 DDL fingerprints,
Access DDL fingerprint, 19 Context tables, six typed Repository relation roles and
Exchange v4. Their actual import origins, interpreters and hashes are in
`distribution.json`.

The probes execute existing production APIs for Access registration/history,
approval invalidation, local Git acquisition into a non-seed Repository, Access
backup/reapproval/fork, Context registration rejection, typed Exchange v4,
I2 Provider intake (decimal versus Node IDs and genuine transfer), different-seed
selective I3 import, qualified Mapping Dispositions, I4 Query/Search fallback and
rebuild, and fresh paired Core+Context restore. They verify domain restore creates
neither Operational nor Access and restores Mapping/Transfer facts. These smoke
probes complement the row-set and corruption tests; they do not replace them.

Artifacts (retained externally rather than adding binary packages to the PR):

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| direct wheel | 745869 | `2ec7c49a81734088ef6f15564c548448f7e79b1786ef86d12bf828c1dd3969cc` |
| sdist | 29443179 | `30b729520dea7e10295f4f8710b662c85e068e6c2d4a8de1e5bfbf79ea921195` |
| sdist-derived wheel | 745869 | `2ec7c49a81734088ef6f15564c548448f7e79b1786ef86d12bf828c1dd3969cc` |

Composed DDL SHA-256:

| Store | SHA-256 |
| --- | --- |
| Core | `3f9f828ad0aff5fae1039f30a3baa29165dbabe6decc5a4f204e78e674b940fe` |
| Context | `fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434` |
| Operational | `76598c5a630d4044c5a123587911a62411d55946072ba071109dd7db52f029a5` |
| Search | `a1bce192ebf67bc3846f47a5bc63ba2927a97bddf65eb62706ec2e9f9fc5d303` |

## Static result

All eight commands in `static-audits.json` exited 0:
Ruff 0.16.10 lint and format on the complete `src tests scripts` trees;
`build_p1_schema.py --check`; `audit_p1_schema.py --check`;
`audit_callsite_dependencies.py --check`;
`audit_implementation_boundary.py --check`;
`audit_context_registration.py`; `audit_access_acceptance.py`.
Checks were read-only, did not regenerate authoritative source and ran with a
bounded three-worker pool. Parallel timings are not sequential benchmark data.
All generated/static/lexical audits retain their documented limitations and
cannot substitute for executable invariant tests or independent review.

Ruff also passes for all four newly authored external runners/probes.
No implementation defect was found by this distribution/static audit.
