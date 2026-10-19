# Independent Review R2: ADR 0029 & ADR 0030 Semantic Consistency Audit

- **Reviewer:** R2 (Independent ADR 0029 & ADR 0030 Semantic Consistency Auditor)
- **Subagent Conversation ID:** `d20a6a6f-34a0-4682-9db7-fb3fd17d073d`
- **Target Worktree:** `/home/ubuntu/github/git-repo-db/docs/accept-adr-0029-retire-0003-20261019`
- **Inspected HEAD Commit:** `af6b5ecca3c9ece3200db85da4c99d35bdbf5cbb` (tree `8b63a857cd8948d73b136016674d27ec55263983`) and verified unchanged across `7c675b8d455aeb51d3c98c250925bff1b45eaf12` (tree `e250754017c1db116979b5ed58f048df56561bfb`)
- **Mode:** Strictly READ-ONLY semantic audit
- **Audit Verdict:** **PASS (`0 Blocking`, `0 Major`, `0 Minor`, `0 Deferred` defects)**

---

## 1. Scope of Audited Documents

- `docs/adr/0029-independent-access-store.md`
- `docs/adr/0030-context-repository-relations-and-selective-exchange.md`
- `docs/architecture/access-store-design.md`
- `docs/architecture/context-repository-relations.md`
- `docs/architecture/selective-exchange-contract.md`
- `docs/implementation/context-exchange-design-handoff.md`
- `docs/implementation/adr-0029-accepted-retirement-20261019.md`
- `docs/implementation/adr-0029-replacement-readiness-20261019.md`
- `docs/phase2/decision-register.md`
- `docs/phase2/documentation-status-audit.md`

---

## 2. Detailed Point-by-Point Verification & Citations

### 2.1 Five-Store Responsibility Boundaries and Lifetime Guarantees

| Store | Verified Responsibility & Authority | Verified Lifetime & Recovery Boundary | Citations |
| --- | --- | --- | --- |
| **Git Core** | Permanent `repository_uuidv4` identities, attributed Git facts, captures, checked structure, allowed retained metadata/notes, Core Coverage, and self-contained historical observation provenance (`repository_claims`, `git_observations`, `captures`). | Application-level strictly `INSERT`-only domain authority; no `UPDATE`/`DELETE`/`REPLACE`, no admitted-fact GC, readable offline without Context or Access. | `docs/adr/0029-independent-access-store.md:50-66,189-203,296-297,354-362,380-385`; `docs/implementation/adr-0029-accepted-retirement-20261019.md:19-25,62` |
| **Context** | Provider/Source identities, known-positive `source_repositories` memberships, current PR/Issue/review/text, typed Resource–Repository relations (`resource_repository_relations`), immutable mapping Dispositions (`repository_mapping_dispositions`), and contextual evidence. | Independently durable domain authority; permitted current-state mutation (with atomic dominance pruning only on the three current-candidate roles); conservative future manual text GC (`GC-01`/`GC-02`) is Context-only. | `docs/adr/0029-independent-access-store.md:54,204-218,359-360,365`; `docs/adr/0030-context-repository-relations-and-selective-exchange.md:31-38,49-72`; `docs/phase2/decision-register.md:122-124`; `docs/phase2/documentation-status-audit.md:3` |
| **Access** | Canonical `scope_uuidv4` identities, same-table `scope_locators` registration history, current repository-locator bindings, connection configurations, external credential references, and local approvals. | Durable configuration with immutable registration facts (`scope_locators`) and separately mutable control state; not a cache and not reconstructible from Core/Context. Backed up separately or in an optional environment bundle; excluded from ordinary domain Exchange. | `docs/adr/0029-independent-access-store.md:55,60-66,109-123,249-277`; `docs/architecture/access-store-design.md:58-81,286-310` |
| **Operational** | Attempts, finite cumulative work accounting, continuation/retry state, frozen request plans, cache locations, and Exchange `PackageKey` (`(sender_catalog_instance_uuidv4, package_id)`) receipt bindings/checkpoints. | Reconstructible execution state; loss does not erase Core/Context/Access truth, never resets consumed cumulative budget to zero, and requires explicit reinitialization (`Q-E10=B`) before new Exchange reception. | `docs/adr/0029-independent-access-store.md:56,278-292,364`; `docs/adr/0030-context-repository-relations-and-selective-exchange.md:83-86`; `docs/architecture/selective-exchange-contract.md:151-176` |
| **Search** | Derivatives of the requested Core/Context domain. | Rebuildable, non-authoritative; explicit creation/rebuild and direct correct-authority scan fallback with diagnostics (`PF-P14`–`PF-P17`). Access is never a search authority. | `docs/adr/0029-independent-access-store.md:57,364-365`; `docs/architecture/access-store-design.md:292`; `docs/phase2/documentation-status-audit.md:68-71` |

### 2.2 Separation of Scope UUIDv4, Scope Locator, Repository Locator, Connection Configuration, and Q-S Namespaces

1. **Four-layer Access separation (`ACC-01`, `ACC-02`, `ACC-02A`, `ACC-02B`, `ACC-03`, `ACC-06`):**
   - **Scope Identity (`scope_uuidv4`):** Canonical UUIDv4 identifying a continuing logical locator-resolution environment (`Q-S1=A`, `Q-S2=A`). Display names, hostnames, container names, and URIs/URNs never replace `scope_uuidv4` in PK/FK or cross-DB references (`docs/adr/0029-independent-access-store.md:39-40,69-74,101-107`; `docs/architecture/access-store-design.md:68,89-98`). Confirmed logical continuity retains `scope_uuidv4`, whereas an independently operated fork receives a new `scope_uuidv4` without rewriting old `S1` registration timestamps into `S2` (`Q-S3=A`, `docs/adr/0029-independent-access-store.md:41,149-167`; `docs/architecture/access-store-design.md:168-185`).
   - **Scope Locator (`scope_locators`):** URI locating/discovering the execution environment of a Scope. Stored as append-only timestamped registration facts (`scope_uuidv4`, `scope_locator_uri`, `registered_at_us`) in a single `scope_locators` table without a separate history table or mutable current-URI column (`docs/adr/0029-independent-access-store.md:43,75-81,109-122`; `docs/architecture/access-store-design.md:69,77-80,110-134`). First-choice selection takes the complete maximal `registered_at_us` set without tie-breaking (`LIMIT 1`, lexical, or rowid) and ranks before checking local approval (`docs/adr/0029-independent-access-store.md:44,124-148`; `docs/architecture/access-store-design.md:135-167`).
   - **Repository Locator (`repository_locators`):** Human-readable Git URL/scp/path address interpreted within a Scope (`(scope_uuidv4, locator_text)`), binding at most one current `repository_uuidv4` per Scope without silent upsert or `.git`/case/symlink/scp normalization (`docs/adr/0029-independent-access-store.md:76-78,95-99,169-188`; `docs/architecture/access-store-design.md:70,186-216`).
   - **Connection Configuration (`connection_configurations` & `locator_connections`):** Reusable versioned typed local transport settings and external credential references (never raw secrets), with local reapproval required per `(scope_uuidv4, locator_text, configuration_name, purpose)` assignment (`Q-S4=A`) and bound to the full Scope registration key, repository binding, profile content, and local environment (`docs/adr/0029-independent-access-store.md:42,82-87,219-247`; `docs/architecture/access-store-design.md:71-72,224-255`).
2. **Q-S Namespace Separation between ADR 0029 and ADR 0030:**
   - Explicitly disambiguated in `docs/adr/0030-context-repository-relations-and-selective-exchange.md:42-45`, `docs/adr/README.md:7`, and `docs/implementation/context-exchange-design-handoff.md:36-41`: Access Scope `Q-S1`–`Q-S4` (accepted 2026-10-17 in ADR 0029) and Context Resource–Repository `Q-S2`–`Q-S16` (accepted 2026-10-18 in ADR 0030) occupy distinct conversation namespaces and neither supersedes the other.

### 2.3 Separation of Provider Identity, Core `repository_uuidv4`, Context Dispositions, and Selective Exchange

1. **Identical Locator strings never infer Repository identity equivalence:**
   - Verified in `docs/adr/0029-independent-access-store.md:89-91,98,300` ("URL equality, redirects, common commits, DNS aliases and matching content never merge repository or Scope identities"; "Different Scopes may interpret identical strings differently"), `docs/architecture/access-store-design.md:200,369-370`, and `docs/architecture/context-repository-relations.md:26-28`.
2. **Access configuration changes never rewrite Core or Context historical evidence:**
   - Verified in `docs/adr/0029-independent-access-store.md:91,189-203,290-291,296-297` (`ACC-04`: Core retains genuine historical `repository_claims` for `endpoint`/`git_path` and capture provenance; rebinding or rotating profiles/locators never updates or deletes previously admitted Core or Context facts) and `docs/architecture/access-store-design.md:37-40,367-368,387-388`.
3. **Provider-to-Core mapping claims (`represents_repository`) never grant Access execution authority, credentials, or consent:**
   - Verified in `docs/adr/0030-context-repository-relations-and-selective-exchange.md:96-97` ("A mapping is not execution authority. Domain Exchange must not initialize, populate or activate Access, grant credentials/consent, or transplant approvals"), `docs/adr/0029-independent-access-store.md:209-211` ("An observed Provider URL is descriptive data; using it as an active locator requires an explicit local admission step"), `docs/architecture/context-repository-relations.md:399-403,413`, and `docs/implementation/adr-0029-accepted-retirement-20261019.md:71-75`.
4. **Competing `represents_repository` claims preserved as immutable positive attributed claims without silent merge, rekey, or latest-clock winner:**
   - Verified in `docs/adr/0030-context-repository-relations-and-selective-exchange.md:56,65` (`Q-S9=B`: "`represents_repository` is an immutable, positive, attributed mapping claim. Conflicting Core UUID targets coexist; there is no automatic rekey, merge or latest-clock winner"), `docs/architecture/context-repository-relations.md:35,44-46,166,212-247` (`rrr_delete_guard` and `rrr_prune_dominated` strictly exclude `represents_repository`), and `docs/implementation/context-exchange-design-handoff.md:32-33,88-90`.
5. **`repository_mapping_dispositions` (`dispute`, `withdraw`, `correct`) never take effect from self-asserted issuer equality alone:**
   - Verified in `docs/adr/0030-context-repository-relations-and-selective-exchange.md:59-61,98-106` (`Q-S12=B`, `Q-S13=B`: "Claimed issuer equality alone grants no effect. A withdrawal/correction can have qualified local effect only where genuine currently available operation/issuer evidence supports it. An imported report is not receiver-local verification"), `docs/architecture/context-repository-relations.md:72-110,261-354,378-405`, `docs/architecture/selective-exchange-contract.md:185-190`, and `docs/implementation/context-exchange-design-handoff.md:104-107`.
6. **No Witness table (`repository_mapping_local_witnesses`), Witness counterevidence table, or hidden verification-history substitute in JSON:**
   - Verified in `docs/adr/0030-context-repository-relations-and-selective-exchange.md:19-24,34-35,61-63` (`Q-S14` final owner override, `Q-S15=A`, `Q-S16=A`), `docs/architecture/context-repository-relations.md:394-397,417`, `docs/architecture/selective-exchange-contract.md:185-186`, and `docs/implementation/context-exchange-design-handoff.md:25-31,108-109,181-202`. Existing P5 Operational request-issuance witnesses in `src/repo_catalog/adapters/sqlite/acquisition.py` are accurately distinguished and preserved (`docs/adr/0030-context-repository-relations-and-selective-exchange.md:84`; `docs/architecture/selective-exchange-contract.md:152-154`; `docs/implementation/context-exchange-design-handoff.md:61,132`).
7. **Context 19-table target composition (17 baseline + `resource_repository_relations` + `repository_mapping_dispositions`):**
   - Verified in `docs/adr/0030-context-repository-relations-and-selective-exchange.md:31-38`, `docs/adr/README.md:7`, and `docs/implementation/context-exchange-design-handoff.md:50-52`.
8. **Selective Exchange (`Q-E1`..`Q-E10`) invariants and preservation of ADR 0017, ADR 0027, ADR 0028, and `NO_INDEPENDENT_PUBLICATION`:**
   - Independent selections `R` (Repository UUIDs), `O` (typed OIDs), and `C` (Context subjects) with bounded typed closure (`Q-E1=C`, `Q-E3=C`, `Q-E4=C`, `Q-E5=C`): `docs/adr/0030-context-repository-relations-and-selective-exchange.md:75-80`; `docs/architecture/selective-exchange-contract.md:11-39`.
   - Cross-seed exchange permits registering only explicitly permitted unknown Repository UUIDs without replacing receiver `store_identity`, and partial admission never registers an unselected/unpermitted Repository merely to satisfy an FK (`Q-E2=C`, `Q-E6=B`): `docs/adr/0030-context-repository-relations-and-selective-exchange.md:76,81,108`; `docs/architecture/selective-exchange-contract.md:58-60,70-82,113-119`.
   - `PackageKey = (sender_catalog_instance_uuidv4, package_id)` bound to one canonical-content SHA-256 exclusively in Operational before Core/Context commits, with stage checkpoints that never override actual committed domain facts and explicit Operational initialization/reinitialization required (`Q-E7=A`, `Q-E8=A`, `Q-E9=B`, `Q-E10=B`): `docs/adr/0030-context-repository-relations-and-selective-exchange.md:82-86`; `docs/architecture/selective-exchange-contract.md:85-176`.
9. **DS-R05 resolved scope vs. still-deferred extensions across ADR 0029, ADR 0030, `decision-register.md`, and `documentation-status-audit.md`:**
   - Verified across `docs/adr/0029-independent-access-store.md:366,402-407`, `docs/adr/0030-context-repository-relations-and-selective-exchange.md:18-38,49-86,148-174`, `docs/phase2/documentation-status-audit.md:75-84,95,100-104`, and `docs/phase2/decision-register.md:3-8,33,98-102,124,130`.
10. **Unapproved Access physical schema and adapter details clearly marked as engineering proposals, not ratified by ADR 0029's whole-record acceptance:**
    - Verified across `docs/adr/0029-independent-access-store.md:14,29-31,46-48,101-104,119-121,245-246,308,422-425`, `docs/architecture/access-store-design.md:1-11,60-62,67-80,110-121,230-231,253-254,451-460`, `docs/implementation/adr-0029-accepted-retirement-20261019.md:33-40`, `docs/implementation/adr-0029-replacement-readiness-20261019.md:42-67`, and `docs/adr/README.md:29`.
