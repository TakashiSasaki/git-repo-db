# Independent archive boundary audit of frozen PR #142

Independent reviewer scope: counterexample design, checker code review, and author test review for AR-001, AR-002 and AR-003. No material additional defect was found in this scope. This is supporting evidence for the parent independent re-review, not whole-PR acceptance, release validation, or a claim that inherited failures pass.

Reviewed HEAD `59307c40ea65554736e131cedd00f04c9906551b`, tree `5ea93707d62b542c84632515392ac6a35c36cd65`. Product, checker, tests, configuration, old evidence and skills were not modified. All new files are confined to this `independent-audit/` directory. No commit, push, merge, release, deployment, external write, extraction, build or installation occurred.

Read repository AGENTS, ADR index/0033 and implementation design, the original independent archive findings/reproducer, PR #142 author report, current checker, hardening test module, and relevant final-tree/lessons skill procedures. The selected Python is 3.12.14; all probes are stdlib-only and do not import product code or obtain/replace SQLite.

## Results

`probe_independent.py` completed with exit **0**: **66 expected results** and **18 expected standalone CLI exit/receipt outcomes**. These are standalone cases, not pytest nodes. All seven retained original attack specimens reject, including their CLI executions producing exit 1 and failed receipts.

Independent cases cover local/global/GNU/unknown tar types, base-256 and octal giant sizes, negative size, body-bearing directories, regular members with link targets, prefix traversal, invalid UTF-8 names, missing SQL/JSON/GraphQL resources, one/two end-block distinctions, hidden second tar after zero records, body/end alignment padding, truncated framing, additional empty/nonempty gzip streams, reserved gzip flags, optional gzip fields and header CRC, trailer CRC/ISIZE, and metadata cardinality/case/folding/syntax. Valid plain USTAR, minimal two-block ending, supported gzip optional fields, CRLF metadata and no-description metadata remain passing controls.

`probe_bounded_memory.py` completed with exit **0**. Two separate sequential children streamed valid gzip envelopes with **16 MiB** and **64 MiB** opaque PAX bodies. Each produced exactly **8,922,625 bytes** (`MAX_TAR_STREAM + 1`) through decoder calls, with maximum output chunk **65,536 bytes**, and **zero `TarInfo.frombuf` calls**. Each refused with `ValueError: decompressed tar stream budget exceeded`, before source inventory or tar materialization. Linux maximum RSS was 23,468 and 23,580 KiB (each child's pre-validation maximum: 14,464 KiB). The input generator itself streams 64 KiB chunks. These measurements support bounded materialization; they are not portable exact RSS guarantees or performance benchmarks.

## Finding disposition

| Finding | Independent conclusion and checked mechanism |
| --- | --- |
| AR-001 | Addressed in the reviewed scope. `read_sdist_stream` bounds inflation before `check_tar_structure`; raw fixed headers reject PAX/GNU/special types before `TarFile.next` can materialize extensions. Original hidden 10 MiB PAX specimen rejects. Both independent larger PAX envelopes hit the stream bound before even fixed-header parsing. The empty extension allowlist is consistent with the recorded locked-backend calibration; this audit did not rebuild the backend artifact. |
| AR-002 | Addressed in the reviewed scope. The decoder requires one complete gzip member with trailer validation and no trailing bytes; physical tar validation requires aligned records, two end blocks, zero-only end padding, and zero member padding. Independent malformed framing/header cases and original CRC/trailer/concatenated specimens reject. Valid gzip optional headers including FHCRC pass; corrupted FHCRC rejects. |
| AR-003 | Addressed in the reviewed identity scope. Case-insensitive singleton cardinality, supported Metadata-Version, Name/version syntax and exact project matching are checked. Independent duplicate/folded/malformed identities and retained original metadata examples reject. Integrated `compare_wheels` still independently requires exact PKG-INFO/METADATA bytes; this audit did not execute that build lane. |

No claim is made that every nonidentity core-metadata field has standalone semantic validation. That was not the original identity finding; complete metadata byte equality remains the integrated build obligation.

## Preserved initial probe mismatch

The first 63-case run exited **1** because an independent expected-rejection case used `Name: repo-catalog\rInjected: yes`. `BytesParser` treats bare CR as a line separator, leaving Name exactly `repo-catalog` and creating an unrelated header. The required singleton identities remain correct. No applicable identity requirement was found that makes this a material defect; integrated metadata byte equality remains additional validation. The expectation was corrected to accepted, three missing-resource cases were added, and the final 66-case run completed. The original `initial-results.json`, stdout/stderr and exit 1 are preserved without alteration. This is an explicit harness-expectation correction, not a product fix or deletion of a failed execution.

## Reproduction and limits

From the frozen repository root:

```bash
python docs/implementation/evidence/adr0033-hardening-rereview-20261023/independent-audit/probe_independent.py
python docs/implementation/evidence/adr0033-hardening-rereview-20261023/independent-audit/probe_bounded_memory.py
```

The scripts reconstruct disposable synthetic archives, write only their own new evidence results, and preserve child commands/exits/stdout/stderr in JSON. CLI temporary paths are recorded as actually executed; the rerun reconstructs equivalent fresh paths. `probe.exit` and `bounded-memory.exit` retain the actual top-level outcomes. JSON includes the checker SHA-256 and runtime identity. `evidence-index.json` binds the final snapshot, excluding itself.

No pytest, full source cohort, installed-product behavior, direct/sdist wheel build, hosted CI, source/wheel metadata equality execution, backend calibration rebuild, release qualification, receipt emitter limit, or integration with #139/#143 was attempted in this independent supporting audit. Those remain parent review lanes, not hidden success claims. RSS does not prove a universal allocation ceiling; observed decoder byte counts and parser ordering are the deterministic boundary evidence. No action was denied or blocked.

Skills were read as review procedures only; no skill changes were authorized. Existing bounded-archive guidance already captures the relevant implementation lesson. No additional verified generalizable defect/fix was found that warrants a new skill.
