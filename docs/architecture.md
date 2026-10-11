# Architecture — Catalog3 Schema 20

The active architecture implements the [accepted Publication-independent reconstruction](phase2/publication-free-design.md). The [implementation handoff](phase2/publication-free-implementation.md) distinguishes implementation from independent review and final acceptance. Earlier boundary/audit receipts remain historical evidence; the 69-table proposal is superseded.

The runtime dependency direction is `cli -> application -> domain/ports`. Adapters own SQLite, HTTP, Git and filesystem operations. `adapters/sqlite/schema.py` composes the sole complete packaged DDL. Initialization, reads/writes, Exchange, maintenance and installed distributions share that schema fingerprint; earlier catalogs are rejected without a migration/compatibility layer.

Portable service/repository/Source registration identities and typed resource parents own facts directly. PR metadata, natural-key documents, threads, Issues/reviews and known Source associations retain current accepted values with per-field origins. A sparse response cannot reattribute inherited values; absence differs from null; equal or incomparable contradictions remain visible. No result/profile/certificate/selection/Publication row enables ordinary reads.

SQLite transactions and nested savepoints make values, presence, evidence, conflicts and local revision coherent. Write transactions do not span network requests. Individually committed resources remain usable after a later page fails. Requested collection completeness has its own exact scope, normalized member/terminal and required-child evidence, while Coverage retains its five-column latest-observation candidate contract. Operational job/cursor state does not own resource validity.

Git object identity and canonical raw bytes own intrinsic commit/parent/tree/tag structure. Each object installs atomically; genuine captures, roots, refs and graph closure have domain responsibilities. Missing targets remain actual missing OIDs. Decoder-specific values attach to objects with explicit settings and module/version; disagreeing candidates are not silently ranked. Code assessments retain minimal head/base/role/list context so current head B cannot borrow head A's completeness.

Exchange exports indexed domain closure from one consistent snapshot. It validates typed dependencies, exact text/Git bytes and current-state rules, stages actual missing/conflicting records, and supports reverse/repeated/late arrival and onward export. Delivery/idempotency processing records do not become fact owners. Sender checksums cannot prove provider authenticity or detect coherent external omission.

Search indexes are derived from current API values and legitimate Git/event content. API originals, retrospective replay, opaque provider replicas and full normalized API edit history are removed. Optional supplementary recording is external and nonfatal. Shared unreferenced text can remain until an independently authorized reclamation policy exists.

CAS quarantine/repair, preservation obligations, verified backup, copied quarantine count (CAS-41) and atomic no-overwrite restore protect physical content. Catalog lifecycle and the single receiver-local `local_revision` counter remain mechanical infrastructure. No new retention/GC, cache architecture, negative-membership, provider trust or Git interpretation policy is implied.

See [every durable subject's key/consumer/lifetime](phase2/publication-free-implementation.md#durable-responsibilities), the [complete table/FK/view/trigger map](phase2/publication-free-schema-map.json), [CLI](cli.md), [operations](operations.md) and [verification](testing.md).
