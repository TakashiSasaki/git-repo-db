# Independent integrated-proposal review — Exchange and identity boundaries

This review read `README.md`, `decision-register.md`, `candidate.sql` and the
candidate validator in `/workspace/p2-design`. Shared files were not edited.
Only new candidate counterexamples were executed; no previously passed production
suite was repeated. Recommendations remain Proposed / Pending Owner Decision.

The reviewed design worktree HEAD was
`c741b5875e94b5a753fa753fc6ea5e618e9108f9`, tree
`f2e9ddf1876cd8216f6a0b666cd75c324a964987`. The integrated proposal files were
uncommitted drafts, so their file hashes, rather than that HEAD alone, identify
the tested material:

| Snapshot | candidate.sql SHA-256 | candidate_probe.py SHA-256 |
| --- | --- | --- |
| Original-cell counterexample | `4a1edcf306d19d14f51320675279721afd80e444369772062dec2fc4d18b22f4` | `8a8e2a5ffa5a0089d167936a9b751c44255dc0d597a141cb892b5014f5e28c08` |
| Corrected field/unknown-identity checks | `2214abb680026043cc02215f5ab7b42787b645d49ef2c0af883d068b3afa1081` | `95bb7f96a77f44a29d511eb9552520392dd8e05bdbacbbd5c7bacce93e6fcb51` |

## Findings and independently verified corrections

1. **Unmodeled response cell admitted by the first candidate validator.** An
   existing PR observation was given a field named `_original_response` containing
   `{http_status:200, headers:{etag:"opaque"}, provider_body:{number:1,
   wire_marker:"unmodeled-response"}}`. Its same-observation producing module and
   version were truthful fixture values. Recomputing the state digest and exact
   member/terminal seals made `validate_collection` accept the collection at 100;
   foreign-key checks were empty. A digest does not establish that a JSON cell is
   an approved domain value. The lead added a closed prototype path/type contract
   and a counterexample. Independent retest of the corrected snapshot rejected
   `_original_response` at its DDL path constraint before it could become proof.
   This small registry models only the prototype's `title`, `head_oid` and `body`
   fields; it does not approve or replace the pending full Q09 field contract.
2. **Unknown identity attributes became mandatory in the first sketch.** The
   `sources.service_uuid NOT NULL` declaration would require a fabricated service
   for ordinary manual Git Sources. Production `MaintenanceService.source_add`
   without `--instance` stores NULL. The sketch also required a provider repository
   ID even though ordinary `repos bind` permits unknown provider identity. The lead
   made both attributes nullable. Independent corrected-snapshot inserts admitted
   a service-less manual Source and a service binding with unknown provider ID;
   FK checks remained empty. Provider inventory still requires the independently
   typed non-NULL Source/service observation edge. This preserves current identity
   responsibility rather than choosing a new lifecycle.
3. **Authority order and proposal tagging.** The draft README placed `AGENTS.md`
   before active owner instructions; its corrected text follows `AGENTS.md`'s
   explicit owner → accepted ADR → current contract → historical evidence order.
   The proposed Source-owned Coverage scope extension was grouped under an `[A]`
   annotation. It is now explicitly `[P Q03/Q05]`, while the exact five-column
   claim/view responsibility remains accepted. There is no automatic extension of
   repository Coverage to Source scan policy.
4. **Natural thread uniqueness absent at the reviewed corrected snapshot.** Two
   `review_threads` rows with different local thread IDs, the same PR, repository
   and provider thread ID were both accepted with FK checks empty. The proposed
   nested proof describes natural thread/PR scope; its surrogate must not permit
   duplicate registrations of the same natural provider thread. The requested
   correction is `UNIQUE(change_request_id,provider_thread_id)` and a negative
   duplicate probe. This was reported to the lead; later artifact checks should
   record the actual corrected SQL fingerprint if the constraint is added.

## Decision and evidence-scope review

Q01–Q12 numbering is consistent. Q10 keeps exact historical normalized values
distinct from immutable current identity/receipt attestation: it does not promise
to recover old Issue/review values from today's mutable row, introduce review edit
history or accept sender digest assertions as complete closure. The proposal keeps
receiver checks local, Source-wide inventory excluded from the current repository
unit, verified Git/text bytes required, and missing/conflicting evidence staged.
No new wire version, signature, sender trust, cache lifetime or deletion policy
was accidentally marked accepted in these reviewed documents.

Some initial “Depends on” lines formed Q05↔Q10 and Q06↔Q12 cycles, as well as
publication/field/lifecycle co-design cycles. The requested documentation correction
distinguishes co-designed choices from implementation prerequisites: collection
semantics constrain later wire validation; child evidence constrains checkpoint
placement. The four approval bundles can then be answered coherently without an
artificial circular implementation gate. Source assessment and historical PR/Git
selection remain genuine pending decisions.

A local-link/heading audit found an invalid Q03 publication fragment and initially
missing planned disposition/review/verification files. The lead corrected the
fragment and added the disposition artifact during review. All other README and
decision-register local file/heading targets resolved at that check. The final
document gate must verify remaining planned review/verification artifacts after
they are written; this mid-assembly check is not final link acceptance.

The executable candidate currently models only PR-list, historical documents,
threads and nested thread-comment collection validation. Its
`review_receipt_members` example requires a captured thread and accepts only a
review-comment, so it is not a generic receipt model for every ordinary review or
Issue collection. Publication, full current-resource, Source, code-target and Git
interpretation validators remain outside this toy validator; the proposal must
continue to state these limits. Source capture principal/visibility context also
needs the Q03/Q09 domain scope contract before scans can be treated as comparable.

These prototype findings and corrections do not certify production acquisition,
Exchange admission or CAS-41 service backup/restore. Their independent production
characterization and the exact integrated runtime acceptance are separate evidence.
