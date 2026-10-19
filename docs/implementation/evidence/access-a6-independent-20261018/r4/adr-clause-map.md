# R4 ADR0003 to proposed ADR0029 preservation review

Fixed source: `f4d0d448fca5925bfbe4f8cb8345c3bd0df7de60`, tree `a7b4521fb7fa6562c8e0bf67e2766743e0b82c5b`.

No material loss of a still-binding ADR0003 clause identified in the proposed successor, after applying already accepted ADR0004/0014/0026/0028 scoped refinements. This is preservation review, not owner acceptance of the whole replacement or permission to retire ADR0003.

All numeric source/successor coordinates refer to the respective ADR files in this frozen tree. The prospective successor explicitly makes its carry-forward table operative at0029:357; this is more than a link to text that would be deleted.

| ADR0003 lines | Clause | ADR0029 lines | Disposition |
| --- | --- | --- | --- |
| 3 | Post-corruption override | 264, 268, 345, 351, 354 | Preserved with existing ADR0026: ordinary stop, read-only source, fresh verified baseline, admissible merge; no quarantine/count resurrection. |
| 5-12 | Accepted target/baseline and scoped metadata-only verifier ownership | 24, 26, 310, 331, 345, 358 | Preserve historical decision date/baseline as provenance; successor is proposed until whole replacement approval. ADR0004/0008 remain active; no new acceptance date is invented. |
| 16-22 | Domain-based partition, local Git subject, historical truth distinct from default runtime | 47, 48, 53, 55, 182, 197, 342 | Partition by described domain; immutable Provider observations remain Context. Current Catalog3 Schema21 is still the default. |
| 28 | Core authority and INSERT-only | 47, 184, 189, 289, 344 | No application UPDATE/DELETE/REPLACE, destructive correction, mutable progress/revision or GC. |
| 29 | Durable mutable-authoritative Context, exact text/evidence | 48, 197, 202, 347, 348 | Not disposable; preserve latest-state/conflicts and separately governed text GC. |
| 30 | Operational execution responsibility and retained PF guarantees | 50, 275, 280, 352, 354 | Reconstructible work/attempts/cache; no authoritative truth or zero-cost resumed request after loss. |
| 31 | Derivative Search, explicit rebuild | 51, 352, 353 | Correct-authority scan fallback with diagnostics; explicit Search create/rebuild; Access is not domain Search authority. |
| 33 | Four physical/logical stores; Git-only Context independence | 43, 47, 53, 55, 67, 349 | The explicit four-store count is the substantive change to five responsibility classes. Offline Git-only use still does not require initializing Context or Access. No automatic runtime switch. |
| 37 | Core rule1 metadata-only and precise checked-byte admission | 343, 345, 358, 360 | Qualified metadata without bytes/rehash/Context; checked bytes still require identity/type/size and atomic intrinsic structure; unknown child is not verified closure. |
| 38 | Core rule2 actual observations, original time/provenance and ref change retention | 84, 184, 189, 279, 343, 350 | No URL/configuration rewrite of facts, no fabricated old observations, prior captures and ref history remain. |
| 39 | Core rule3 unreachable retention and no admitted-content GC | 289, 343, 350 | Nonacquisition is distinct from deleting admitted evidence/bytes; apply ADR0014 retained-body scope. |
| 40 | Core rule4 technical rows, exact replay, no replacement loopholes | 289, 344 | Explicit application-visible INSERT-only includes technical rows; full replay comparison; no REPLACE/upsert/drop-recreate loopholes. |
| 41 | Core rule5 remodel prior mutable columns/revision | 289, 344 | No mutable verified/completion/progress/revision pointer in Core; implementation inventory remains engineering work. |
| 42 | Core rule6 decoder provenance, no generic winner, integrity/no in-place repair | 345, 358 | Preserve precise decoder/local checks and atomic structure; ADR0026 replaces obsolete quarantine/count/in-place post-fault mechanisms. |
| 43 | Core rule7 permanent repository UUID and minimal provenance | 62, 67, 84, 184, 189, 346 | Minimal actual Core evidence stays understandable without Provider/Source/Access foreign rows; names/endpoints are not entity identity. |
| 47 | Context rule1 current-state/field-clock/Source/children/head-base semantics | 48, 202, 206, 347 | Q01-Q04, missing/null, alternatives, real clocks, required children, actual role/head/base and no hidden full edit-history archive remain. |
| 48 | Context rule2 association ownership and dependency direction | 53, 67, 347, 349 | PR-Git association is Context; underlying Git capture is independently valid in Core; portable typed references only; no reverse required row. |
| 49 | Context rule3 split mixed tables by meaning | 199, 202, 348 | Classify fields, not whole-table rename/move; a PR trigger does not move a Git fact to Context. |
| 50 | Context rule4 Provider text, exact UTF8/SHA256 and lifetime | 48, 348, 353 | Exact text and digest collision checks belong in Context; future Context GC policy stays distinct. |
| 51 | Context rule5 no Publication/general history/winner | 255, 294, 348 | No universal bundle/seal/eligibility owner, API full edit log, parser winner or domain publication gate. |
| 55 | Git-only init/local input/query/export/backup independence | 53, 55, 56, 349 | Offline Core operations do not require Context/Access/credentials/network; metadata-only remains valid; retained-byte output remains separate. |
| 56 | Cross-file references and typed dependency validation | 65, 67, 349, 350 | No assumed SQLite cross-file FK. Application validation and conservative absent/stale/conflicting dependencies remain required. |
| 57 | Cross-store write truth and idempotent failure recovery | 284, 349, 353 | Core first remains valid if later Context fails; no fabricated closure, no extension of disposable PF-P07 relaxation to two authorities. |
| 58 | Pinned Core or coherent paired read snapshots | 273, 349, 350 | No mixing versions and claiming coverage; freeze Access settings before external work, not new cross-authority validity owner. |
| 59 | Retention/cascade and known-positive boundaries | 206, 208, 289, 343, 350 | Context/Provider/Source/Access changes never cascade to admitted Git facts; no fake absence from inventory loss. |
| 60 | Git-only versus paired full backup; formats/hashes/pairing/no overwrite | 242, 250, 255, 351, 354 | Preserved under current ADR0026; old CAS41 counter is historical, actual checks and atomic no-overwrite remain. No whole-repository restorability claim. |
| 61 | Search correct-source fallback and no implicit hydration | 51, 352, 353 | Explicit correct-authority scan fallback with diagnostics and rebuild/creation. Metadata-only does not require raw-body fetch. |
| 62 | Operational loss cannot invalidate authoritative data | 50, 275, 280, 352 | Disposable execution/cache state is not Context and cannot erase domain authority or silently replenish old budget. |
| 70 | PF-P06 placement replacement | 43, 47, 353 | Five responsibility classes; preserve durable truth versus disposable execution/search separation. |
| 71 | PF-P08 full catalog backup | 250, 351, 353 | Core+Context paired domain backup and truthful Git-only scope stay valid without Access; Access backup is separate. |
| 72 | PF-P05 no current GC; future Context GC01/02; GC03/04 open | 353, 354 | No current domain-text GC; future conservative Context-only GC; no extension to Core. |
| 73 | PF-P14/15 correct-authority Search | 352, 353 | Core/Context-specific direct fallback and truthful completeness. |
| 74 | PF-P07 relaxed disposable atomicity not authoritative pairing | 284, 349, 353 | No excuse for inconsistent Core/Context writes, snapshots or backups. |
| 76 | Not reopened UUID/Q01-Q04/Coverage/trust/time/PF/ADR0001 | 262, 285, 301, 347, 354, 355 | Apply current0014/0026/0028 scopes; preserve classified microseconds, original Capture pair, finite cumulative work, five-column Coverage and Source positive evidence. |
| 80-82 | Non-goals, no table-count guess, constrained engineering work | 26, 301, 312, 355, 376 | Prose alone is not implementation, migration, GC, merge or runtime activation. Names/DDL/fences are engineering work within settled decisions. |
| 83 | Deferred DS-R01/R03-R08 and source-unclear CAS IDs | 354, 355 | Deferred scope is preserved. Use explicit original list in retirement writeup; DS-R02 future Context textGC has its own PF-P05 constraints and is not a new architecture question. |
| 89 | Acceptance1 independent Git-only + zero-body roundtrip | 343, 349, 351, 355 | Local actual capture/query plus backup/restore and metadata-only support remain acceptance requirements, not prose PASS. |
| 90 | Acceptance2 append-only attacks and ref rewrite retention | 343, 344, 350, 355 | No UPDATE/DELETE/REPLACE including recovery/hydration/administration; prior actual refs/objects remain. |
| 91 | Acceptance3 Provider/current-state outside Core and no false full restore | 348, 351, 355 | Context current-value behavior/conflicts remain; missing Context cannot become full restoration success. |
| 92 | Acceptance4 PR-triggered independent Core and honest partial writes | 349, 350, 355 | No false closure/coverage after partial writes; unverified metadata is not inherently failed bytes. |
| 93 | Acceptance5 retained bytes/digest/identity/scope/fallback | 351, 352, 354, 355 | Actual domain/retained-byte validation and classified trust apply, not old quarantine counters or archive promise. |
| 94 | Acceptance6 exact effective tree, independent review, dev/release distinction | 301, 335, 355 | Review and execution require exact source; owner approval, merge and release qualification remain distinct. |
| 96 | Boundary freeze is not evidence that implementation passed | 24, 26, 301, 355 | No self-certification by documentation. |

## Acceptance-time work, still unauthorized in this task

1. Obtain an explicit whole-record replacement approval and its actual date/reference; accepted Scope choices alone do not supply this.
2. In one coherent reviewed change, set0029 accepted/date, retire only0003, update current authority wording/links/index, and close only this policy migration-debt entry.
3. Retain prior-decision metadata and historical receipts as history; never rewrite past package membership/hashes. No duplicate active ADR archive is needed.
4. Check exact final parent diff and complete live inbound links/navigation after the authorized change; keep default Schema21/P8, public site allowlist, release and merge gates separate.

No ADR status, date, file, link or source tree was changed by R4.
