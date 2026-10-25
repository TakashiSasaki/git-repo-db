# Independent v5 wire and original-report review

**Scoped result: FAIL for I6B-IR-M02 (Medium, open).** The required v5 checksum
contract is not fulfilled. The separate source probes for strict Context syntax,
identity/original preservation and Source/Coverage give 157 PASS; thirty required
checksum-refusal counterexamples fail at the call assertion because no refusal
occurs. These are separate invocations, not a synthesized passing total.

## Frozen source and procedure

Reviewed publication HEAD `ef787a5ff8b13f118d6bf5107c7338f43fde56dc`, tree
`a3ed2628a98db134bdc65d13da905f5ddf25e972`. Comparison source is #149
`ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00`, separately exported by `git archive`
into `/workspace/i6b-wire-baseline`; actual module paths and hashes are recorded
in `contract-base149.json`. No Author fixture or Author classifier is imported.
New fixtures use different UUIDs, nested Unicode identifiers, reversed transport
order and independent observation coordinates. No product/existing test/ADR,
Transfer fence, permission fixture or historical evidence is edited.

AGENTS.md, the ADR index, Accepted ADR0001/0031/0032, the I6 wire/admission,
vectors/tests and change-map/handoff contracts, the I6-B implementation description,
Author REPORT/MATRIX and #149 independent REPORT were read alongside the actual
codec, row/identity authorities, typed originals and selective Context validators.
The local efficient-repository-investigation and ci-final-tree-verification
procedures were applied; older exact-SQLite recipes are superseded by ADR0032.

The Python is 3.12.14, `.venv/bin/python`, using its real SQLite 3.53.1 and source
ID `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
`RECEIPTS.json` contains actual executable, module/input hashes, options and
capability observations. No SQLite package/build/replacement or matrix is used.
The pure-code probes do not open production catalogs or claim schema/transaction
acceptance from the default in-memory PRAGMA observations.

## Measured lanes

| Invocation | PASS | FAIL | Exit | Complete phases |
| --- | ---: | ---: | ---: | ---: |
| Initial independent wire cases | 128 | 0 | 0 | 384 |
| Final independent wire/Source/Coverage cases | 157 | 0 | 0 | 471 |
| R03 required checksum-refusal counterexamples | 0 | 30 | 1 | 90 |
| Separate V07 resolved Mapping/endpoint alternatives | 4 | 0 | 0 | 12 |
| Current v5 standalone behavior diagnosis | diagnostic | diagnostic | 0 | not pytest |
| #149 v4 standalone behavior diagnosis | diagnostic | diagnostic | 0 | not pytest |

The first and second lanes overlap; the initial test bytes remain separately
saved as `test_independent_wire.initial.py.txt`. The final script adds independent
Source/Coverage vectors and replaces only its origin assertion with an explicit
`WIRE_IMPORT_ROOT` parameter so the unchanged probes can run on installed wheels.
`test_independent_wire.py.txt` and `test_digest_contract.py.txt` retain final bytes.
`test_resolved_wire.py.txt` separately adds four V07 original Mapping/endpoint
alternative controls with 4 PASS, exit0; it does not alter either earlier suite.
`audit_wire_receipts.py.txt` independently reconciles collection, normalized JUnit
identities and journal starts, with exactly one setup/call/teardown per node,
normal finish and matching actual process exit. All four receipts reconcile;
there are no skips, xfails or errors. Raw test logs, JUnit/journals, codes and
refusal types/scopes are retained. The digest lane's thirty call failures are
expected demonstrations of a product defect, not converted into passing tests.

## I6B-IR-M02: checksum verifies normalized selection instead of received content

R03 explicitly hashes the whole canonical package dictionary excluding only
`digest_sha256`. `decode_package` instead constructs `ExchangeSelectionScope`
first (`exchange.py:847`), and checksum recomputation through `_canonical_content`
uses `package.to_dict()` (`exchange.py:334`). Selection serialization sorts and
deduplicates the five set-valued dimensions (`exchange.py:465`). Therefore a
received dictionary can change while its old checksum still passes.

The minimal saved case starts with a valid `repository_uuidv4s=[R,Q]` selection,
then appends R or reverses those entries without changing its digest. Both raw
canonical received hashes differ from the declaration. All five dimensions
(repository UUIDs, Source UUIDs, notes refs, OIDs and ResourceKeys), two mutations
and dict/str/bytes carriers are accepted: thirty failures of the required refusal.
`digest-vectors/` saves each original/received dictionary and both actual digests.
The standalone ten-case current probe also supplies the **actual** mutated raw
digest; all ten are then rejected as `DIGEST_MISMATCH`, showing that normalization
rather than received content determines verification. #149 v4 gives the same ten
stale accepts/ten actual-digest refusals. This is an inherited mechanism that fails
the new v5 R03 contract, not a claim of new privilege escalation or a production
behavior regression relative to #149.

Repair acceptance: hash the actual bounded received dictionary before selection
normalization, or explicitly reject noncanonical selection arrays without silently
repairing them. Every saved stale-digest mutation must be refused across all
carriers, valid canonical-selection positives must remain lossless, and source /
direct-wheel / sdist-derived-wheel results must be independently preserved. No
Provider authenticity or admission authority may be inferred and both SQL fences
must remain in place. This task reports the finding without editing the Author PR.

## Verified wire and original-preservation scope

The 157 new source cases independently establish:

- v5-only intake; missing format; missing/extra envelope/Resource fields; strict
  Resource types; invalid canonical IDs after a correct checksum; outer/embedded
  duplicate JSON keys, nonfinite numbers, malformed UTF-8 and Unicode surrogates;
  decoded cyclic input terminates with a typed refusal.
- All seven Resource identification columns, distinct meaningful empty values,
  scalar/recursive-array identities, composed/decomposed Unicode, global/scoped
  Documents, strict scoped metadata and no invented namespace Resource or Parent.
- Independent Parent clock 607 / Parent observation NULL or 613 / Parent provenance
  versus Event clock 701 / Event observation 709 / Event provenance. Event-first
  and reversed endpoint transport retain the exact original strings; absent exact
  Parent key cannot borrow another provenance. One-sided, two-sided and unresolved
  Provider-only states remain distinct. Dropped/extra/wrong-time/wrong-scope
  endpoints, missing Parent coordinates and wrong declarations refuse.
- Unknown generic relation/member order, known-empty/partial-empty/unknown/no
  terminal and equal-time competing order alternatives remain unchanged. Duplicate
  members and same-key changed original time refuse.
- Source positive pairs, partial inventory, real terminal boolean and set ordering;
  exactly five Coverage claim columns; each proof coordinate must match its actual
  original terminal, claim and scope. Nonterminal evidence creates no proof;
  partial cannot prove complete; cross-service Source evidence and extra sender
  verification fields refuse.

`decode_package` is an untrusted envelope/row-key stage; `decode_context_v5`
additionally runs typed Context semantics. This distinction is respected in all
probes. Eight separately measured wrong Core primitive variants pass the envelope
stage identically on #149/#151 and are all refused at the actual CorePreflight/typed
OID boundary (`contract-*.json`). There is no demonstrated admission bypass; this
inherited parse/semantic split is informational rather than a new Medium finding.
A separate V07 fixture preserves two explicit resolved targets and distinct full
MappingSupport claims for the same Provider endpoint, with original Parent/Event
clocks/times and reversed wire order. Sender verification prose remains only
attributed provenance. Target substitution, missing endpoint and extra field in
the exact support key refuse. Its four passing tests are a separate invocation.
No complete Core admission, current authorization, durable transfer, I6-C/I7/I8,
full regression or Release acceptance is claimed by this subreview. Parent scope
contains the other independent regression/admission/distribution evidence.

## Reproduction

Copy the saved `.py.txt` files to an external directory as `test_independent_wire.py`
and `test_digest_contract.py`, retaining bytes, then use the already selected
Python with repository config and journal registration once:

```sh
.venv/bin/python -m pytest -c pyproject.toml -o addopts= \
  -p scripts.ci_journal /workspace/i6b-wire-probes/test_independent_wire.py -q \
  --junitxml NEW/junit.xml --journal NEW/journal.jsonl
.venv/bin/python -m pytest -c pyproject.toml -o addopts= \
  -p scripts.ci_journal /workspace/i6b-wire-probes/test_digest_contract.py -q \
  --junitxml NEW/digest-junit.xml --journal NEW/digest-journal.jsonl
```

Use a new output directory for every invocation; record exits 0 and 1 separately.
For installed forms use external pytest configuration without checkout pythonpath,
set `WIRE_IMPORT_ROOT` to the actual installed site-packages and independently
assert module origins. The distribution reviewer owns those actual executions.
`diagnose_wire_contract.py.txt` accepts `--import-root` and `--output`, records
actual module hashes and makes no writes other than its diagnostic JSON.

No operation in this subreview is denied, pending approval or uncertain. No skill
mutation is needed in the reviewed tree; the reusable lesson is to compare the
received canonical dictionary checksum before interpreting normalizing domain
serializers, and to keep inherited behavior attribution separate from the new
contract's acceptance result.
