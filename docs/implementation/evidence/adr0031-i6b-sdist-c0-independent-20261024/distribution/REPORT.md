# Independent distribution and C0 review of published PR155

**Scoped verdict: PASS. No new Critical/High/Medium/Low finding in these measured
distribution and C0 checks.** This does not decide scanner acceptance, I6-C,
ordinary Transfer activation, product-wide acceptance or Release qualification.

The reviewed source is PR155 HEAD
`fee364c6d61a5feebf08dbdd830a5a57ee2d872b`, tree
`ace7e44cd89194d189a30a0aa6cf513a45b3b87c`. All experiments used that published
checkout, disposable synthetic inputs and independent fresh installations. No
Task A workspace or unpublished work was accessed. No product, original tests,
workflow, ADR or historical evidence was edited.

## Independent build and install evidence

The new `reproduce.py` independently inventories tracked product/build files,
builds actual direct wheel and sdist with Hatchling 1.32.4, then checks all archive
members against the independently read source. The published checker is a subject
under test, not the member/content oracle. The derived wheel is rebuilt by the
installed backend in an extracted minimal source tree without `.git`, Git on PATH,
docs, tests, scripts or a preinstalled product package in the backend environment.

| Measurement | Observed |
| --- | ---: |
| Product inputs | 160; 6,025,551 bytes |
| Product suffix counts | 137 Python, 19 SQL, 2 JSON, 2 GraphQL |
| Sdist compressed bytes | 702,494 |
| Sdist regular-file bytes | 6,041,897 |
| Sdist physical/regular members | 164 |
| Sdist whole tar stream | 6,174,720 bytes |
| Each wheel | 791,300 bytes; 164 members |

Sdist SHA256:
`9d228f889f9507cdc5a166b9658e80873fcbd48255c6c958eb90e33954014b54`.
Both wheel SHA256:
`2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8`.
These independently measured values agree with the Author references; they were
not hardcoded acceptance criteria.

Both wheels have identical full archive bytes, every member's bytes and all
inspected ZIP metadata (timestamps, compression, CRC, flags, attributes, extra,
comments, versions, offsets). All RECORD rows are independently recomputed;
PKG-INFO exactly equals METADATA. Each of the 160 product files matches its actual
source bytes. The source/build inventory includes README, pyproject and the
backend-required source-hashed `.gitignore` separately from generated PKG-INFO.

Fresh separate `direct-venv` and `derived-venv` installs were exercised from an
external working directory. `installed_probe.py` verifies actual site-packages
origins of `repo_catalog`, `domain.context_dependencies` and `domain.exchange`, all
160 installed source hashes and every hashed installed RECORD entry, including
installer-generated entries. Console doctor on the direct install and
`python -m repo_catalog ... doctor` on the derived install both exit 0 against
explicit disposable state paths. The I6 subreview's independently written pure
contract probe also runs **58 PASS / 0 FAIL, exit 0 on each installed wheel**;
these overlapping checks are attributed to that subreview and are not added as
distinct ordinary-suite coverage.

The additional `installed_cohorts.py` driver executes the unchanged published
I4/I5 test files with the published external installed-test harness: **217 PASS /
29 PASS on each wheel**, each exit 0 with zero skips/xfails/xpasses. Independent
source-file hashes establish identical copied bytes; only external filenames
differ. Collection, JUnit, journal starts, one setup/call/teardown and finish exits
reconcile. Session-start/session-finish import receipts bind installed hashes and
all loaded product modules. The 246 mapped source-node IDs per artifact are
retained; the I6 subreview combines its selection for exact unrun-node accounting.
`distribution-only-coverage.json` and the two compressed unrun rosters additionally
map these 246 nodes against the fresh duplicate-free ordinary collection of
6,497: **6,251 unrun in this I4/I5 subreview alone per artifact**. That count must
be recomputed after union with the separately executed installed I6 selection.

These are attributed existing tests. Positive isolated I4 fixtures deliberately
drop two named fences only in disposable databases after exact schema checks;
I5 uses its published fresh-memory harness. Passes do not enable or establish
ordinary Transfer. FixturePolicy used by the original smoke grants an explicit
finite provider/repository set. No copied assertion or production installation
is changed by this reviewer driver.

Additional fresh product-only installs preserve the original Access smoke's
httpx-absence assertion. The unchanged original smoke runs against each wheel and
**fails at its first Exchange export with PERMISSION_DENIED, exit 1**. The actual
installed `application/exchange.py:397` refuses that intentionally unconnected
call. A read-only line tracer records **26 assertion statements entered and 28
unentered** in each smoke. Statement entry does not imply all subexpressions or
later assertions ran. Original tracebacks and unentered line rosters remain
visible; they are not classified as a new distribution regression or a success.

Native runtime is Python **3.12.14**, SQLite **3.53.1**, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Actual interpreter/base executable, loaded source, compile options, package
origins and dependency versions are retained per installed form. No SQLite
download, build, installation, replacement, alternate engine or matrix was used.
Dependency preparation used declared package constraints rather than claiming a
hash-locked offline dependency install: httpx 0.28.1, httpcore 1.0.9, h11 0.16.0,
anyio 4.15.1, certifi 2026.10.23, idna 3.20, typing-extensions 4.16.0. This detail
does not change or substitute any product-source comparison.

## Archive boundary evidence

Twenty-three new independent adversarial specimens are rejected by the actual
published checker: corrupt CRC/ISIZE, missing trailer, truncated deflate,
trailing zero, concatenation, malformed second gzip stream, hidden nonzero tar
tail, whole-tar inflation overflow, compressed overflow, local/global PAX,
GNU longname, symlink/hardlink/character device, traversal/absolute/backslash
paths, duplicate member, duplicate metadata Name, malformed metadata version and
wrong package identity. Their bytes/hashes and refusal messages are retained.
The physical-header pass rejects extensions before the later `tarfile.open`
logical-member parsing. The checker itself never extracts, builds or installs.

Eight additional independently constructed budget controls establish finite
boundaries, all with expected results:

| Actual measurement | Result |
| --- | --- |
| Compressed 2,097,152 bytes / 2,097,153 bytes | accept / reject |
| Regular bytes 8,388,608 / 8,388,609 | accept / reject |
| Physical members 512 / 513 | accept / reject |
| Whole tar stream 8,922,624 / 8,923,136 bytes | accept / reject |

The compressed-boundary specimens are real gzip streams with optional FNAME
header padding and unchanged inspected tar content. They are not mocked `stat`
sizes. The regular/member controls use matching disposable source inventories;
the whole-tar controls retain actual zero end-padding. These are bounded tested
cases, not an assertion that every malformed archive has been enumerated.

## C0 actual final ZIP measurements

`c0_boundaries.py` independently runs the actual emitter as a full child CLI in a
fresh disposable synthetic Git repository. A read-only trace saves its actual
`body` only after ZipFile closes; no ZIP writer, length, compression, limit,
production operation or return value is replaced. Input length/seed calibration
is retained separately. Every reported verdict is a complete actual emitter run.

| Actual closed DEFLATED ZIP bytes | Exit | Stdout bytes | Result |
| ---: | ---: | ---: | --- |
| 2,097,151 | 0 | 3,285,724 | accept |
| 2,097,152 | 0 | 3,285,724 | accept |
| 2,097,153 | 1 | 0 | reject |
| 2,323,560 | 1 | 0 | reject |
| 6,660; expanded 6,120,406 | 0 | 10,609 | accept |

Refusal stderr is exactly `CI receipt exceeds 2 MiB compressed; retrieve the
uploaded GitHub Actions artifact` plus newline. A separate uninstrumented real
CLI oversize control also exits 1 with zero stdout and that diagnostic.
All five saved closed ZIPs have valid CRC, DEFLATED members, exact index roster,
member byte/hash equality and actual synthetic Git/run/tree binding. Successful
boundary output strictly verifies BEGIN length/SHA, DATA prefix/chunk length,
strict base64 and END SHA. Actual input bytes are unchanged after observation.
Synthetic fixture Git/run identity is explicitly separate from the reviewed
emitter's Git/source identity; it is not presented as a hosted run.

The published Access workflow has both emitter and subsequent upload-artifact
steps at `if: always()`, retaining `access-registry-verification` and both evidence
paths. The emitter refuses before its first print. Code/configuration inspection
and these local experiments establish the measured fallback behavior; **actual
hosted overflow/upload/download was not run here**. Existing normal hosted
receipts below the limit cannot substitute for that experiment. No Release
dispatch, deploy or workflow alteration occurred.

## Reproduction, evidence and limits

Run with a prepared Hatchling 1.32.4 interpreter and the same native Python:

```sh
python distribution/reproduce.py --root CHECKOUT --out OUTPUT/run1 --build-python BUILD_PYTHON
python distribution/archive_budgets.py --root CHECKOUT --out OUTPUT/budgets
python distribution/c0_boundaries.py --root CHECKOUT --out OUTPUT/c0
```

`archive_budgets.py` expects the preceding `run1` sibling output. C0 requires an
empty output directory for its disposable Git repository. Actual ZIP bytes may
differ on rerun due to real timestamps/Git fixture commit identity; measurements,
payload equality, strict indexes and exact requested closed sizes are rechecked.

`raw-evidence.zip` and `raw-index.json` retain raw build logs/exits, complete source
and wheel inventories, built artifacts, all malformed specimens, budget
specimens, installed receipts, independently invoked I6 outputs, unchanged
installed I4/I5 collection/JUnit/journals/import receipts, both original Access
failures/assertion-entry rosters, C0 calibration, observer, real ZIPs and strict
measurement receipts. Every indexed payload was
read back and hash-checked. Full successful multi-megabyte DATA stdout is measured
and hashed rather than duplicated; the actual corresponding closed ZIP is saved.

Two environment/helper failures were visible before success: uv's default cache
outside writable roots returned read-only (exit 2, no setup performed), then a
task-local cache succeeded; an installed-probe command initially selected a
not-yet-created external working directory and could not start, then ran after
that directory was created. Neither was a service safety denial or counted as
product evidence. No denied product/security action was retried or routed around.

These independent checks do not resolve the 299 inherited ordinary non-successes
or the reproduced Access refusal, establish all I6 behavior, or provide hosted
Release acceptance. Broader I6 scope and the exact installed remainder remain
owned by the other review sections and future checkpoints. No absence of a
distribution finding authorizes merging, releasing, I6-C incorporation or fence
retirement. No blocker remains for publishing this bounded subreview evidence.
