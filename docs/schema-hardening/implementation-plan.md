# Current catalog3 implementation state

Catalog3 is the sole ordinary runtime. Packaged DDL and the runtime identity module are authoritative; [runtime handoff](runtime-handoff.md) records commands, validation and limits. Historical phase plans and design/export schemas remain snapshots.

This stride starts at main `1ce7fccdb63ab7de74daf6694d2c7187fcddd835` on `refactor/portable-document-observations`. It advances schema identity **4 -> 5**, retaining `repo-catalog/catalog3`, and implements the user's agreed identity/observation decisions rather than another purely mechanical rename.

Implemented scope:

1. Rename service namespace to `service_instance_uuidv4` and kind to `service_kind`; require canonical UUIDv4 and retain CSPRNG generation. Preserve provider-originated identifiers and namespace separation; do not merge by URLs.
2. Replace local document IDs with `(change_request_id, kind, provider_change_request_document_id)` across DDL, collectors, references, queries and diagnostics. Remove the review extension's redundant document-ID alias as well.
3. Make exact-UTF-8 SHA-256 the unique text-body content identity, rejecting inconsistent digests and conflicting body reuse.
4. Remove document versions. Store each observation's direct text-body SHA-256; use a same-document `current_document_observation_id`, preserving actual A->A->B->A history and replay fencing.
5. Adapt guarded v2 salvage to the new target without altering source schema or bytes. Archive old IDs/version facts; map documents to composite keys and current-version assertions only to suitable real observations.
6. Rebuild PR search inputs by content identity while returning distinct observations. Replace obsolete CLI version selectors with explicit observation selectors. Validate normal runtime, preservation, recovery and packaging on disposable synthetic sources.

No v4 migration/compatibility views, separate portable schema, multi-catalog exchange, open-ended providers, real-data activation or release publication is included. Existing real-world reports retain their original commits and scopes.
