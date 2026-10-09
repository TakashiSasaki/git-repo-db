# Supplementary transport recording

The HTTP transport records optional investigation material through
`MessageRecorder.record_exchange(context, body)`. The provider parser receives
the ordinary response regardless of whether supplementary capture succeeds.
`MessageArchiveReader.read(reference, max_body_bytes=...)` provides bounded,
read-only access to one explicitly selected recorded exchange. Neither port
accepts a domain datastore.

## Modes and storage

The engineering default is `github.record_messages = false` in `catalog.toml`.
The disabled recorder creates no archive directory. With recording enabled,
`recorder_from_config(config, state_dir)` supplies `LocalFileRecorder` using
`STATE_DIR/transport-archive`. Construction itself does not access the directory;
an unavailable archive therefore does not prevent starting a collector.

Each capture has a random UUIDv4 correlation reference and two private files:
`REFERENCE.body` holds response bytes when available, and `REFERENCE.json` holds
versioned metadata, byte length and SHA-256. A body is written and fsynced before
the metadata publication marker. Exclusive creation and no-overwrite publication
preserve existing entries. Files use mode 0600; a newly created archive directory
uses mode 0700. No archive-management database, retention period or automatic
cleanup is introduced.

These references identify supplementary captures, not provider resources or
immutable domain facts. Domain validity and coverage cannot depend on resolving
them. Normal current Issue/review state, exchange and catalog backup/restore do
not require this directory. Existing required inputs for unaffected PR/Git
historical interpretation remain in the primary catalog; enabling or disabling
supplementary recording does not change those contracts.

## Recorded representation and metadata

`http-content-decoded-v1` means exact bytes produced by `httpx`'s
`Response.iter_bytes()` after HTTP content decoding, before JSON interpretation.
For example, a gzip-compressed response stores the decoded JSON bytes. Original
selected response headers may still describe gzip and its encoded content
length, while the envelope gives the actual stored byte length. This is not a
full wire capture. The adapter omits request bodies, TLS framing, unselected
headers and transport-internal details.

The transport filters context before handing it to any recorder. Request headers
are restricted to Accept, User-Agent, the GitHub API version and conditional
validators. Response headers are restricted to content metadata, validators,
date, GitHub request/API identifiers, rate-limit fields and Retry-After.
Authorization, Cookie and Set-Cookie are excluded. URL user information and
fragments are removed; only page, per_page, state, sort, direction and since
query values are retained. All other query values are explicitly replaced with
`[REDACTED]`.

`metadata_redacted` labels this metadata filtering. Response body bytes are never
redacted or rewritten: source text may itself contain sensitive material, which
is why authenticated synthetic traffic is used for testing and real captures
are never committed. Filtered metadata is not described as byte-identical
request evidence.

The context preserves signed-int64 `observed_at_us`, one-based attempt number,
method, filtered URL, selected request/response headers and response status.
Failed exchanges have a stable failure code, no exception message and no body.
A response interrupted halfway is never presented as a complete captured body.
Optional explicit provider hints are limited to request kind, owner, repository,
PR/Issue number, collection scope and service/repository UUID. Arbitrary keyword
arguments and GraphQL request bodies are not archived.

## Failure behavior and observation context

Expected recorder failures use `RecordingError`. The transport emits a visible
`RuntimeWarning` and retains a bounded diagnostic list containing only error
code, observation time and attempt. Otherwise valid responses continue to the
provider parser. Unexpected exceptions raised by the recorder callback become
the generic `ARCHIVE_FAILURE` diagnostic without exposing exception text.
Cancellation and transport, parsing, catalog persistence and still-required
evidence failures keep their ordinary error behavior. HTTP failures and each network/server retry are recorded when
the recorder is available, without changing retry or rate-limit semantics.

Returned responses expose three transport extension values:

| Extension | Meaning |
|---|---|
| `catalog_observed_at_us` | Original response arrival observation, in epoch microseconds |
| `repo_catalog_archive_ref` | Optional UUIDv4 correlation reference |
| `repo_catalog_recording_diagnostics` | Supplementary capture errors for this response |

Archive inspection does not create a remote observation. Parsing saved bytes
must retain the recorded observation time and must not admit ordinary current
state implicitly. Provider hints supply context for the same provider parsing
code; absent context, unavailable bodies and unsupported response kinds remain
explicit inspection limitations rather than fabricated parents or identities.

## Bounded archive reading

`LocalArchiveReader` accepts a canonical UUIDv4 reference, at most 64 KiB of
metadata and a caller-selected body bound from zero through 32 MiB. It rejects
symlinks and nonregular files without blocking, validates the metadata schema
and exact byte length/SHA-256, and returns `ArchivedExchange(reference, context,
body, body_representation)`. A lower caller bound permits small inspection
operations without allocating the full transport limit.

```python
from pathlib import Path
from repo_catalog.adapters.recording import LocalArchiveReader

# Explicit disposable synthetic state; no network or catalog writes occur.
reader = LocalArchiveReader(Path("/tmp/synthetic-catalog-state/transport-archive"))
message = reader.read(reference, max_body_bytes=1024 * 1024)
original_observation_us = message.context["observed_at_us"]
```

`ARCHIVE_MISSING`, `ARCHIVE_CORRUPT`, `ARCHIVE_IO` and `ARCHIVE_LIMIT` describe
investigation availability. `ARCHIVE_ARGUMENT` rejects unsafe references or
bounds. These failures have no path to invalidating independently admitted
current-state rows. Corruption of a domain text body or required immutable input
remains a catalog integrity failure.

Focused synthetic regression evidence lives in
`tests/unit/test_transport_recording.py`, including disabled/unavailable modes,
decoded-byte identity, credential filtering, retry/failure recording, bounded
reading and corrupt/missing archive behavior.
