# Phase 2 independent adversarial review

Status: independent adversarial review. The integrated proposal remains
**Proposed / Pending Owner Decision**. Prototype success is not production
acceptance; exact integrated-implementation acceptance is the lead's separate
responsibility.

## Reviewed boundary and method

This reviewer used the separate `review/p2-adversarial-20261010` worktree at
`20e0f8d78b77c6c8d37826fd6d639819631e166b`, read the current `AGENTS.md`, the
accepted transport-independent-core ADR and Phase 1 retirement decision, and
traced the packaged schema and actual SQLite, collector, job and Exchange
readers. No authenticated collection, retained catalog changes, owner-level
policy decision, production edit, push or merge was performed.

The review separates constraints already accepted by the owner from choices
still pending. Replacing a legacy parser result does not automatically authorize
a new domain lifecycle, clock or Exchange trust policy. Each counterexample below
is an implementation requirement for a chosen model or an explicit decision to
resolve; it is not an implied approval of that model.

## Independent falsifiers

| ID | Failure severity if implemented | Concrete counterexample and required result | Actual code boundary / existing test evidence |
| --- | --- | --- | --- |
| IR-01 | High | Repository R1 and R2 each have a valid PR and publication. A collection owned by R1 references R2's publication through a nullable compound FK. The row must fail ownership admission even when one FK coordinate is NULL; publication, observation, fragment and child owner checks cannot rely solely on a NULL-skipped SQLite FK. | `catalog3.sql` `fetch_scope_insert`, `membership_owner_insert`, typed result/CR FKs; `test_catalog3_coverage_ownership.py`. |
| IR-02 | High | A Source-wide inventory publication is given the same local identifier as a repository publication. It cannot become repository-owned proof or one-repository Exchange closure. Source registration identity stays independent of Source display name and local Source ID. | `ApiFacts.source_input`, `inventory_observations`, `Graph.original_root`; `test_catalog3_exchange_integrity_audit.py::test_source_derived_name_never_leaks_source_wide_evidence_or_dangles`. |
| IR-03 | High | A valid member X arrives, followed by an unparseable member Y. X may remain a committed admitted resource if existing transaction boundaries permit it, but the fragment must not assert that its entire provider member set was admitted or complete. Fully rejected bytes stay transient. | `current_collection`, `partial_rest_collection`, `ApiFacts.publish`; `test_phase1_retirement.py`. |
| IR-04 | High | Collection C has one accepted, terminal, empty fragment at time 0. It proves an empty enumeration. C with no fragments does not prove the same fact. Unknown time stays NULL and time 0 is valid. | `CurrentCollectionProof.evidence`, `current_collection_completion_valid`; `test_catalog3_coverage.py` signed epoch probes. |
| IR-05 | High | C contains fragment ordinals 0 and 2, two occurrences of ordinal 1, or a nonterminal final fragment. No count-only test may establish completion. Require exact contiguous ordered fragments, unique identities and an explicit terminal boundary. | `CurrentCollectionProof.evidence`, `current_collection_completion_valid`. |
| IR-06 | High | Fragment 0 ends with continuation token A; fragment 1 was actually fetched using token B from another root. Matching ordinals and terminal flags alone do not establish an exact continuation chain or scope. If the selected model proves continuation consistency, persist a normalized chain binding or validate a sealed equivalent without retaining the HTTP envelope. | `ApiFacts.scope`, `current_incremental_url`, `_thread_children`; current receipts are an example, not a universal GraphQL schema. |
| IR-07 | High | C has members X and Y; digest H was computed only over X. A receiver obtains X, terminal evidence and the asserted H. Complete proof must fail or remain staged until exact required membership is available and checked. Membership count, terminal status or advisory `requires` alone cannot certify the omitted Y. | `Graph.proof_requirements`, `Graph.aggregate_proof`; `test_catalog3_selective_exchange.py::test_collection_and_explicit_fetch_subset_exact_proof`. |
| IR-08 | High | A receipt at time 100 witnesses mutable Issue X with body A; X now has body B at time 200. The old receipt must remain valid without falsely saying B was observed at 100. The accepted latest-state Issue/review lifecycle cannot silently be converted into all-values history by requiring A in every portable closure. Explicitly distinguish witnessed state digest, retained historical values and present identity eligibility. | `current_collection_pages.members`, `Graph.current_page_requirements`, current resource lifecycle in `AGENTS.md`. |
| IR-09 | High | Complete Coverage at 100 and partial Coverage at 200 must derive partial at 200. A retry observed at 150 cannot borrow the failed attempt's time 200 to emit complete. Equal-time complete and partial at 200 derive conflict. A later valid complete at 300 may supersede both. | `coverage_claims` five columns, `current_coverage`, `admit_claim`; `test_phase1_retirement.py::test_rejected_graphql_child_retries_its_safe_cursor_without_original`, `test_catalog3_coverage.py`. |
| IR-10 | High | A GraphQL root terminally lists T1 and T2. T1 comments are complete, T2 comments are incomplete. The root's thread enumeration and usable T1/T2 resources may be valid, but thread/comment aggregate completeness is partial. A required child cannot be omitted by deleting the edge before sealing. | `threads`, `_thread_children`, `completion_markers.evidence.current_page_collections`, `Graph.proof_requirements`. |
| IR-11 | High | An accepted partial GraphQL root at 200 contains errors and usable domain facts; no complete child boundary exists. Restart must reuse only the durable admitted prefix/domain continuation evidence selected by policy. It cannot replay saved response originals or discard the actual partial observation clock to manufacture complete Coverage. | `threads`, `_thread_children`, `partial_rest_collection`; `test_phase1_retirement.py` partial GraphQL and stale retry cases. |
| IR-12 | High | Publication P is sealed with outputs A and B. A late INSERT attaches output C or moves B under P. A reader must not see a changed sealed publication. Output count and digest are checked against typed output membership in one write transaction; conflict does not become a winner by receipt order. | `parsed_result_publications`, result-sealed triggers, `ApiFacts.publish`, `ParserModel.publish_result`. |
| IR-13 | High | Two PR observations report `head=H1` and `head=H2` without comparable clocks. Replacing parser/fact selection DAGs with maximum UUID, insertion ID, parser version, parsing time or observation receipt order fabricates a domain winner. Retain and expose conflict or use an explicitly accepted provider clock/selection rule. | `active_fact_selections`, `CurrentResources._clock_order`, transport-independent ADR clock invariants. |
| IR-14 | High | A sparse response omits body, another supplies explicit NULL, and a third supplies empty UTF-8 text. Each has distinct semantic state and provenance. An unchanged field inherits its earlier module/version/capture/clock; row-level module metadata cannot overwrite its origin. | `current_parser`, `CurrentResources._merge_fields`, `field_evidence_json`; `test_current_conflict_boundaries.py::test_sparse_freshness_does_not_certify_omitted_body`. |
| IR-15 | High | Issue I transfers R1 to R2. Its current membership changes, but existing field evidence and inherited child capture retain the original Source, endpoint, repository scope and observation time. Destination-only Exchange must preserve genuine competing variants and permit detached capture identifiers under the existing checks; requiring original Source registration indiscriminately changes that accepted contract. | `CurrentResources._project_child_membership`, `identity_relations.validate_acquisition_scope`; `test_current_conflict_boundaries.py` transfer probes. |
| IR-16 | High | A sender exports `last_checked_at_us=300`. Import must not confirm that the receiver checked the resource at 300. A receiver's live request may update its check only with the pre-request revision, exact scope and current job-attempt fence still valid. | `CurrentResources._admit`, `ApiFacts.fence`, `Graph.record`; `test_current_conflict_boundaries.py::test_exchange_omits_checks_from_current_and_staged_candidates`. |
| IR-17 | High | PR head/base are H1/B1 while commits/files are acquired; a final observation is H2/B1. Earlier listing and verified Git bytes remain honest facts, but no complete current code target for H2 may be inferred. Exact target identity includes object format and head/base and all required roles. | `GitHubCollector.code`, `Graph.code_proof`, `code_observations` context guards. |
| IR-18 | High | A 304 is obtained using an ETag from another Source, principal, endpoint, field projection, parser contract or target. No normalized/cache reuse is justified merely because the resource number or URL matches. A missing, evicted or corrupt cache requires an actual response or explicit unresolved result. Conditional reuse policy itself remains an owner decision. | `ApiFacts.scope`, `validators`, `incremental_scans`, `Graph.proof_requirements` 304 branch; `test_catalog3_exchange_integrity_audit.py` 304 owner/missing-original cases. |
| IR-19 | High | Receiver gets a complete publication before its owner, one member before terminal evidence, then duplicates in reverse order. It stages genuine missing dependencies and eventually converges without choosing a first-arriving immutable variant. A partial selective export does not carry a complete claim unless it closes the exact full proof. | `Graph.receive`, `Graph._admit`, `Graph._promote`; `test_catalog3_selective_exchange.py::test_f0_f1_f2_arrival_reopen_repeat_and_full_convergence`. |
| IR-20 | High | A normalized-looking arbitrary JSON column contains the entire API object, or a replacement publication includes original-byte digest registrations only to support replay. Neither is domain modeling or authorized Phase 2 work. R1–R7 remain retired even if a proposal renames their tables or wire records. | Phase 1 retirement ADR; `test_phase1_retirement.py`, `test_phase1_exchange_retirement.py`. |
| IR-21 | High | SHA-1 and SHA-256 objects use the same raw content but different Git identities. Verify actual `type + size + NUL + raw` identities and physical SHA-256, preserve format-qualified OIDs and required bytes, and never infer a Git object from a syntactically valid descriptor. | `git_object.py`, `stage_verified_payload`, `payload_admission_staging` fail-closed UDF trigger; `test_catalog3_cas_integrity.py`. |
| IR-22 | High | API proof and Git content share physical digest D. Removing API logical ownership must neither delete the Git bytes nor treat API-only bytes as Git repair authority. API-only quarantine disposition cannot be assumed by dropping a logical label. | `payloads`, `stored_bytes`, `payload_quarantine`; `test_catalog3_cas_integrity.py::test_repair_accepts_real_git_content_even_when_api_proof_shares_its_bytes`. |
| IR-23 | High | Source and copied backup disagree on active physical quarantine count. Restore must reject a mismatching, missing, boolean or malformed manifest count before diagnosing the copied content; diagnostics may not silently make the manifest agree. Retired logical API rows do not authorize automatic physical deletion. | `MaintenanceService.backup/restore`, CAS-41; `test_catalog3_cas_integrity.py` backup/restore probes. |
| IR-24 | Medium | One selected repository with 10 domain members coexists with 100,000 unrelated receipts or Git objects. Exact closure must visit selected dependencies and scoped indexes, not scan every unrelated repository or repeatedly expand nested trees. Scope lookup is by typed identity, never display name. | `Graph.local_original_context`, `Graph.original_intake_context`, grouped `_promote`; `test_phase1_exchange_scaling.py`. |
| IR-25 | High | A crash after durable fragment/resource admission but before progress update can lose the prefix, double-publish it or advance the watermark incorrectly. Domain fragment, admitted memberships and restart token must commit atomically where the selected restart policy requires durable prefixes; publication sealing and safe watermark update must check the valid job-attempt fence. | `current_collection`, `_thread_children`, `ApiFacts.publish/fence`, `JobService.resume`, frozen `job_plans`. |

## Review limits

These checks do not decide historical retention, permanent publication identity,
collection schema, 304 policy, checkpoint lifetime/placement, new Exchange trust
or physical retention. They identify what an accepted alternative must preserve.
No table is declared safely deletable merely because the target excludes it.

## Executed baseline characterization

At baseline HEAD `20e0f8d78b77c6c8d37826fd6d639819631e166b`, tree
`003d276a6aeb6a1479232a1d0a1857db371cb623`, the independent reviewer executed
the complete Coverage and owner modules, selective Exchange and integrity audit,
CAS integrity/backup/restore, current Exchange followup and current conflict
boundaries: **301 passed, zero failures/errors/skips, 121.571 seconds**. No parser
bootstrap environment override was used. Python was 3.12.14 and SQLite 3.53.1.
The exact command, production fingerprints and node IDs are recorded in
[the baseline receipt](independent-baseline-receipt.json). This characterizes the
unchanged baseline; it is not the final code-bearing PR acceptance receipt.
Concurrent other work means elapsed time is not a comparative benchmark.

Independent dependency-audit execution reproduced 103 product tables, 665
columns, 226 FK clauses, 48 views, 498 triggers and 106 explicit indexes, with
DDL SHA-256 `16110944d4b6a0942657644fe80383394210af1218a3e7111e331a1651fa211e`.
All 48 views and 309 triggered mutation preparations compiled; FK/integrity
checks and generated JSON equality passed. The four unprepared literal SQL
statements were intentional negative/derived-table tests, not production SQL.
The audit's initial environment-dependent import resolution could mix one
checkout's AST/revision with another's installed schema; review prompted
explicit `ROOT/src` import precedence. AST and SQLite authorizer/EXPLAIN evidence
remain static access evidence, never proof of live reachability.

The corrected audit was executed with a deliberately wrong `PYTHONPATH` pointing
to the fields worktree. Its explicit checkout import precedence still reproduced
the investigated baseline. Two final generations were byte-identical with output
SHA-256 `a2f8c13e31ef0533bc4aff0524e1ecc0c3254feaab5a05aeeca235ba45c16892`;
the tested script SHA-256 was
`116445b9095f3d3dc0d3fa53e6df484442a16417afce50e9a0c17cc594c6ff8c`.
Four independent audit unit cases also passed without bootstrap. These checks
cover generation/import isolation and classified access evidence, not runtime
reachability of every AST match.

## Prototype falsifiers and corrections

The independent
[counterexample script](prototypes/independent_counterexamples.py) reproduced
three narrow-fixture limits. Different observation identifiers make digests
differ even after an intentionally collapsed missing/null status; comparison
must keep identity fixed. Owner equality alone admits a thread member under a
PR-list scope and an unrelated PR-list child for thread T1. These are omissions
in the deliberately generic disposable fixture, not inferred production defects.
See [the executed receipt](independent-counterexample-receipt.json).

The completeness author strengthened the status test to differ only in status,
added a real temporary SQLite file close/reopen to its prefix continuation probe,
and documents the generic fixture's lack of full family, natural parent, UUID,
immutability and provider authenticity enforcement. An integrated implementation
must provide those typed checks independently.

The first integrated illustrative DDL review found violations of already
accepted contracts: a different five-column Coverage shape, unknown/complete
ties incorrectly deriving conflict, no empty-scope result, current Issue/comment
identity missing kind, absent binding and PR natural-key uniqueness, nullable
TEXT primary keys, noninteger stored times and an unconditional Gitlink-target
FK. The author corrected the exact claim shape/truth table, typed Issue identity,
natural keys, STRICT table layout and optional retained Git child mapping. Source
was made optional for legitimate direct Git endpoint acquisitions. This change
revealed a separate nullable-FK bypass in repository publication ownership; the
reviewer's SQL attack admitted an absent repository when Source was NULL and
reported it for correction.

[Independent SQL attacks](prototypes/independent_schema_attacks.py) operate below
the application validator so the two enforcement levels cannot be confused.
Code target value/role consistency, exact PR/listing scope, Git acquisition
membership, field-cell origin clocks/capture and immutable sealed membership
need concrete validator checks in addition to DDL shape.

The corrected candidate independently passes the SQL attacks, including the
previously admitted absent-repository/NULL-Source publication. Its executable
validator now rejects tampered normalized retained values, cross-resource field
origins, contradictory field producer metadata, wrong same-repository PR child
scope and wrong captured thread identity. An independent current-review receipt
probe confirms that a later mutable body does not invalidate an old digest
attestation or create an edit-history requirement. The precise tested DDL/validator
fingerprints and distinctions between checks and limitations are recorded in the
[SQL](independent-sql-receipt.json) and
[validator](independent-validator-receipt.json) receipts. The prototype does not implement every production
publication, Source, code, Git interpretation or current-admission rule.

The independent [validator attack](prototypes/independent_candidate_validation.py)
also reproduces an explicitly declared limitation: inserting a publication seal
with count zero while one PR observation belongs to that publication still makes
the observation visible in the illustrative candidate view. Production admission
must validate and freeze the exact typed output set before a reader treats seal
existence as eligible publication. This is a high-severity implementation
requirement, not a claim that the disposable prototype is a safe replacement.

## Independent review of determined corrections

These changes correct current accepted contracts or their execution cost. They do
not choose a new publication identity, lifecycle, 304 cache or Exchange policy.

| Correction | Independent challenge and outcome | Exact revision / evidence scope |
| --- | --- | --- |
| Sparse author, nested parent and Git target extraction | Empty/present object without selected login/ID/OID must omit the normalized field; explicit source NULL clears; explicit OID NULL clears; NULL canonical parent ID remains invalid. Falsey scalar/list shapes reject. Live/import updates preserve the retained field's original capture/parser evidence, and receiver checks remain local. **176 passed**, without bootstrap. | `c6a54666688b2d72888686efca5f1b10b9efca86` then `835b3309f6eff1c7192376ec7147c63983e7470e`; 70 author, 72 nested and 34 projection/conflict cases. |
| Conflict-free Exchange refresh | Early return is after stale barrier cleanup and pending profile/fact scope barriers, before unneeded whole-catalog dependency materialization. Positive conflict seeds still traverse domain/Coverage dependencies. **40 passed** without bootstrap; two live fixture failures reproduced the changed builtin hash boundary, then those **two passed** with explicit development bootstrap. | `c8180e79acced221f9b7c3f3717388b7fb022721`. This is a focused development receipt, not regenerated-certificate acceptance. |
| Result-led publication indexes | Actual `ParserModel.publish_result` enumerates exact positive output seals. All seven formerly scanning UNION branches now use result-led SEARCH plans. **8 passed**, without bootstrap; independent VM counts reproduce **1,088** steps at both 100 and 2,000 unrelated histories versus **3,329/45,151** after removing only those indexes. | `a94dd50906a7918f84e66f2623dcef977cd93b76`. Seven indexes only; schema version/fingerprint/certificate finalization belongs to integrated acceptance. |
| Rejected current collection observation time | Known current-resource response rejected at 200 remains partial200; older valid retry175 cannot certify complete200; equal-time retry200 produces conflict; valid300 supersedes. Scope mismatch, unrecognized response, other Source900, invalid adapter clocks and stale job attempt cannot lend fabricated evidence. Terminal cancellation resumes locally at original100; incremental watermark stays original start100. **22 new passed without bootstrap**; broader **196 passed** with explicit development bootstrap. | `6edc217ec4f673fbf10056e2e4436507c8a1a5d2`. 22 new cases plus eight current collection and 166 Coverage cases. No retained transport bytes in these probes. |

Historical complete-marker correction was independently challenged with missing,
duplicate and skipped ordinals; early terminal/nonterminal boundaries; injected
unrelated current receipts; mismatched root clocks; raw/current cursor
contradictions; and corrupt, missing or quarantined bytes used to invent a partial
GraphQL retry. The legitimate accepted-error root, with advertised terminal or
nonterminal cursor, survives retry and Exchange. Current-only children and 304
validation need their existing typed proof path rather than a blanket raw sequence
rule. Independent review prompted a final rawless-root restriction: only a typed
thread-comments child with actual current receipts can be rawless within the
historical-marker path. Frozen `b5fa28e42ab04a15a135c651f9dab3fdaaa6f057`
independently passed **24 static cases without bootstrap** (two live cases
deselected), then **54 complete focused cases with explicit development bootstrap**.
No further production-review blocker remains in that correction.

Source-bound correction heads/trees, test node IDs, known development failures,
bootstrap flags and production-file fingerprints are recorded in
[the correction review receipt](independent-correction-review.json). The receipt
also records the independently executed actual-publication VM measurements.

No independent run here is represented as the code PR's full ordinary suite,
wheel/sdist installs or hosted CI. Development bootstrap is disclosed wherever
used; final acceptance must run against the frozen integrated definition and
regenerated successful capability artifact without that override. One index-test
setup used a nonexistent module name and collected no tests; it was corrected to
the actual parser-model module before the eight-case successful run. Concurrent
wall times are not clean comparative benchmarks.

## Integrated design review and residual requirements

The recommended separation of provider identity, individual observation,
publication, enumeration/terminal assessment, Coverage, current candidate
selection and operational restart/cache has independent semantic responsibilities.
Typed repository and Source publications avoid the old identity/lifecycle
conflation. Current Issue/review receipts preserve the existing mutable-state
boundary. Raw Git/domain text, real observation clocks, per-field parser origins,
missing dependencies, conflicts and physical quarantine remain explicit.

The following requirements remain implementation gates for the eventual chosen
model, even after the owner approves its architectural alternatives:

1. Recompute/freeze exact typed publication output membership; reject late mutation,
   wrong owner and unvalidated dependency sets. Never substitute an empty parser
   input manifest or dummy fetch identity for domain publication.
2. Validate all family-specific collection/natural parent/target constraints,
   including same-repository different-PR/thread substitutions, exact required
   child sets, changed PR head/base and Git acquisition-object membership. SQL FKs
   alone cannot establish those semantic bindings or historical receipt authenticity.
3. Bind every retained field path to its approved type/presence contract and real
   origin. The narrow PR cells demonstrate the principle; a full writer/reader/
   search/Exchange field contract must cover every approved family and decoder.
4. Preserve accepted current admission, transfer, detached capture and local-check
   behavior across the new wire/physical model. Requiring reconstructible old
   current values would reopen the accepted latest-state boundary.
5. Keep restart cursors and optional cache disposable relative to admitted facts.
   A missing or mismatched cache/refetch cannot validate a complete domain target;
   stale attempts cannot publish or advance the watermark.
6. Carry exact selected closure with indexed bounded work, promote only real missing
   dependencies, retain conflicts, and keep Source-wide/local/quarantine/cache
   records outside the current one-repository Exchange scope.
7. Reuse CAS-41 copied-database validation before diagnosis and required raw Git
   identity checks. Removing API logical consumers never authorizes deletion or
   invented Git repair authority.

A fresh receiver can check declared normalized membership, digest, terminal and
child consistency. It cannot discover a provider member omitted from both the
declaration and all transmitted normalized facts by a coherently rewritten sender.
SHA-256 is content identity, not provider authenticity. Existing-identity conflicts
can be detected when an incumbent variant exists; sender/ingestion attestation
and trust qualification for new normalized Exchange remain a genuine Q10 decision.

The first approval bundle must specify the affected historical lifecycles plus
publication, field and completeness meaning. Publication Q04 alone cannot unblock
all dependent readers. Source and Git work can proceed in parallel after their
own decisions; portable closure and final common DAG/transport retirement depend
on those families. No question should seek renewed approval of settled identity,
time, Coverage, current-resource or CAS responsibilities.

The revised decision register keeps current-family receipts unchanged across Q10
options, states the Q10-T evidence/trust limit, separates Q08-S/G questions and
distinguishes co-design dependencies from implementation prerequisites. The
conditional disposition generator independently verifies all 103 product tables
and their SQL dependent objects against the exact inventory and compressed source
hash. Classification is a semantic responsibility/dependency map, not deletion
authorization or runtime-liveness proof.
