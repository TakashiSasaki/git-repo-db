# Context Resource--Repository relations: integrated schema contract

Normative decisions: [ADR 0030](../adr/0030-context-repository-relations-and-selective-exchange.md).
Baseline: PR #103, `1134e200eb4ac9ec45bf3fae3be695e2bb786a8d`.
This is a design document, not packaged SQL, a migration or an executed product
qualification. SQL below is the proposed physical realization; implementers must
verify it with the actual packaged Context schema and supported SQLite runtime.

## 1. Logical entities and dependencies

| Entity | Identity and meaning |
| --- | --- |
| Provider Resource | Existing `(service_instance_uuidv4, resource_kind, provider_resource_id)`; names/URLs are not identity |
| Core Repository | Existing permanent `repository_uuidv4`; Context's `repository_context` is its local registration/FK target, not a replacement identity |
| Resource--Repository report | `(ResourceKey, relation_kind, clock_json, target_json, provenance_json)` |
| Mapping ClaimKey | The preceding full key with `resource_kind='repository'` and `relation_kind='represents_repository'` |
| Mapping DispositionKey | `(ClaimKey, disposition_kind, disposition_clock_json, disposition_provenance_json)` |
| Provider-to-Provider relation | Existing `resource_relations`; kept distinct from a resolved Core correspondence |
| Current mapping evaluation | Derived result over reports and presently available genuine evidence; not another authoritative table |

All diagrammatic K1/D1/R1/G identifiers in this document are abbreviations, not
new persisted row IDs. Core remains readable without Context or Access.

`Resource -> Repository` is not a single ownership column. A PR's base and head
are different roles. A Provider Repository's correspondence to a Core UUID is a
claim by the real mapping issuer, not a UUID supplied by GitHub. A shared OID,
URL, repository name, redirect or successful access is not evidence to merge
identities. Resolve Provider Repository references separately, and preserve the
actual mapping support in derived Core-target reports.

### Six-role matrix (closed vocabulary)

| Role | Subject | Target | Lifetime |
| --- | --- | --- | --- |
| `represents_repository` | `repository` | UUIDv4 only | Immutable positive mapping report; alternatives retained |
| `owning_repository` | `issue` | UUIDv4 or explicitly reported JSON null | Current candidate |
| `base_repository` | `pull_request` | UUIDv4 or explicitly reported JSON null | Current candidate |
| `head_repository` | `pull_request` | UUIDv4 or explicitly reported JSON null | Current candidate |
| `transfer_from_repository` | `comment`, `timeline_event`, parent `issue` | UUIDv4 or explicitly reported JSON null | Immutable real-event endpoint report |
| `transfer_to_repository` | Same | Same | Same |

No `referenced_repository` role, PR `owning_repository` duplication, or automatic
Review/Comment inheritance rows. Query genuine parent relations instead. A
positive mapping report may conflict with another report without making both
UUIDs objectively identical. Do not add UNIQUE(ResourceKey) to mapping claims.

## 2. Values, clocks, provenance and NULL

Canonical JSON uses the existing reversible whole-value convention, not hashes
or receiver-local aliases. SQL examples use deterministic helper contracts:

- `p1_uuid4(x)`: the existing canonical UUIDv4 validator.
- `p1_json(x)`: the existing canonical JSON validator.
- `p1_mapping_target(x)`: proposed helper, true exactly for canonical JSON null
  or a JSON string containing a canonical UUIDv4.
- `p1_mapping_clock(x)`: proposed helper, exactly `{"domain":nonempty-text,
  "at_us":null-or-positive-int64}` with no extra properties. JSON bool, float,
  numeric strings and overflow are rejected before coercion; SQL additionally
  checks the type returned by `json_extract`.
- `p1_mapping_provenance(x)`: proposed helper preserving the existing nonempty
  `source` and non-null `evidence` requirements, plus the optional issuer grammar
  below. It returns 0, not SQL NULL, on invalid input. Bounds/UTF-8/duplicate-key
  checks also apply at the decoder boundary. Helpers are not implemented here.

`clock_json.at_us` is the actual source clock; `observed_at_us` is the original
observation time. Neither is receiver arrival time. Observation/Provider times
are NULL or integer 1..9223372036854775807 under ADR 0028. Native Git time rules
remain different and are not changed by this Context design.

### Optional claimed issuer (engineering wire grammar)

```
provenance = {
  "source": <original nonempty source description>,
  "evidence": <genuine non-null original evidence>,
  "claimed_issuer": <omitted | null | {"namespace": <text>, "id": <text>}>
}
```

When `claimed_issuer` is an object, both strings are nonempty and no additional
issuer members are interpreted. Namespace must distinguish the genuine issuer
system/instance; the word `local` alone is not a portable principal namespace.
Preserve Provider-supplied identifier values and their namespace. Canonical JSON
escaping does not authorize changing the decoded identifier, trimming case,
normalizing Unicode, or decoding an opaque GraphQL ID. Positive decimal IDs may
use the existing explicitly typed lossless decimal encoding. Supporting another
ID namespace requires an explicit adapter contract, not guessing from syntax.

Omitted issuer means not supplied. JSON null means explicitly reported unknown.
An issuer object is a **claimed** issuer, not authenticated identity. Do not fill
missing issuer from Provider owner, Source registration, Access Scope, sender
Catalog or receiver account. Do not add an issuer table/FK as an admission gate.
If an identity Resource is actually known, any link is separately qualified.
The new optional grammar does not make an issuer mandatory across Context, nor
replace existing Core `Provenance` formats with Context JSON.

`provenance_json` is part of ClaimKey; the Disposition's own provenance is part of
DispositionKey. Never edit it after admission or add relay/check metadata as key
salt. Genuine later reports may be distinct; re-reading/forwarding is not a new
issuer action. Registration `configuration_json`/`attributes_json` remain their
own finite domain contracts, not automatically provenance objects.

| Condition | Stored meaning |
| --- | --- |
| No Repository field reported | No candidate row |
| Actual Repository field explicitly null | `target_json='null'` where allowed |
| Provider Repository ID known, Core mapping unknown | Preserve Provider relation; no resolved Core-target row, no invented null |
| Several incompatible mapping targets | Separate immutable reports; explicit conflict |
| No verifiable issuer/operation evidence | Retain admissible Disposition, effect unconfirmed |

## 3. Physical design: relation table

Eight stored columns and five generated columns are proposed. Resource FK uses
existing identity; target FK is within Context. No FK crosses into the Core file.
The conditional event FK is in addition to the unconditional Resource FK: its
NULL bypass for non-event rows must not permit nonexistent subjects.

```sql
CREATE UNIQUE INDEX resources_typed_event_fk
ON resources (
    service_instance_uuidv4, resource_kind, provider_resource_id,
    document_kind, parent_resource_kind
);

CREATE TABLE resource_repository_relations (
    service_instance_uuidv4 TEXT NOT NULL,
    resource_kind TEXT NOT NULL,
    provider_resource_id TEXT NOT NULL,
    relation_kind TEXT NOT NULL,
    target_json TEXT NOT NULL CHECK (p1_mapping_target(target_json) = 1),
    clock_json TEXT NOT NULL CHECK (p1_mapping_clock(clock_json) = 1),
    provenance_json TEXT NOT NULL CHECK (p1_mapping_provenance(provenance_json) = 1),
    observed_at_us INTEGER CHECK (
        observed_at_us IS NULL OR
        (typeof(observed_at_us) = 'integer' AND observed_at_us > 0)
    ),
    repository_uuidv4 TEXT GENERATED ALWAYS AS (
        CASE WHEN json_type(target_json) = 'text'
             THEN json_extract(target_json, '$') END
    ) VIRTUAL REFERENCES repository_context(repository_uuidv4),
    clock_domain TEXT GENERATED ALWAYS AS (
        json_extract(clock_json, '$.domain')
    ) VIRTUAL,
    source_clock_us INTEGER GENERATED ALWAYS AS (
        json_extract(clock_json, '$.at_us')
    ) VIRTUAL,
    event_document_kind TEXT GENERATED ALWAYS AS (
        CASE WHEN relation_kind IN (
            'transfer_from_repository', 'transfer_to_repository'
        ) THEN 'timeline_event' END
    ) VIRTUAL,
    event_parent_resource_kind TEXT GENERATED ALWAYS AS (
        CASE WHEN relation_kind IN (
            'transfer_from_repository', 'transfer_to_repository'
        ) THEN 'issue' END
    ) VIRTUAL,
    CHECK (typeof(source_clock_us) IN ('integer', 'null')),
    CHECK (
        (relation_kind = 'represents_repository' AND resource_kind = 'repository')
        OR (relation_kind = 'owning_repository' AND resource_kind = 'issue')
        OR (relation_kind IN ('base_repository', 'head_repository')
            AND resource_kind = 'pull_request')
        OR (relation_kind IN ('transfer_from_repository', 'transfer_to_repository')
            AND resource_kind = 'comment')
    ),
    CHECK (relation_kind != 'represents_repository' OR json_type(target_json) = 'text'),
    PRIMARY KEY (
        service_instance_uuidv4, resource_kind, provider_resource_id,
        relation_kind, clock_json, target_json, provenance_json
    ),
    FOREIGN KEY (service_instance_uuidv4, resource_kind, provider_resource_id)
        REFERENCES resources(service_instance_uuidv4, resource_kind, provider_resource_id),
    FOREIGN KEY (
        service_instance_uuidv4, resource_kind, provider_resource_id,
        event_document_kind, event_parent_resource_kind
    ) REFERENCES resources (
        service_instance_uuidv4, resource_kind, provider_resource_id,
        document_kind, parent_resource_kind
    )
) STRICT, WITHOUT ROWID;

CREATE INDEX rrr_by_repository ON resource_repository_relations (
    repository_uuidv4, relation_kind,
    service_instance_uuidv4, resource_kind, provider_resource_id
) WHERE repository_uuidv4 IS NOT NULL;
CREATE INDEX rrr_current_clock ON resource_repository_relations (
    service_instance_uuidv4, resource_kind, provider_resource_id,
    relation_kind, clock_domain, source_clock_us DESC
) WHERE relation_kind IN ('owning_repository', 'base_repository', 'head_repository')
    AND source_clock_us IS NOT NULL;
CREATE INDEX rrr_event_report ON resource_repository_relations (
    service_instance_uuidv4, resource_kind, provider_resource_id,
    clock_json, provenance_json, relation_kind
) WHERE relation_kind IN ('transfer_from_repository', 'transfer_to_repository');
```

### Required mutation guards

`rrr_no_update` rejects every UPDATE. Before INSERT, `rrr_no_rebind` compares any
exact existing seven-column key's `observed_at_us` using null-safe equality and
rejects changes. An exact repeat is otherwise an idempotent no-op through typed
admission. Do not rely on `ON CONFLICT DO NOTHING` without the payload check.
`rrr_event_report_time` requires equal original observation time for every
from/to row in one EventReportKey, without combining distinct reports.

A stale current candidate is an ordinary typed `stale` admission outcome, not a
corrupt database and not an invalid whole Exchange package. A BEFORE INSERT
backstop can reject a candidate dominated by an existing strictly later clock;
the API must map only that specific condition correctly. It must not swallow an
unrelated constraint/rebinding failure. Exact replay checks precede stale logic.

Q-S7=B requires the following atomic pruning behavior. Both guards apply only
to the three current roles; mapping claims and event endpoints are never pruned.

```sql
CREATE TRIGGER rrr_delete_guard
BEFORE DELETE ON resource_repository_relations
WHEN OLD.relation_kind NOT IN ('owning_repository', 'base_repository', 'head_repository')
 OR OLD.source_clock_us IS NULL
 OR NOT EXISTS (
    SELECT 1 FROM resource_repository_relations AS later
    WHERE later.service_instance_uuidv4 = OLD.service_instance_uuidv4
      AND later.resource_kind = OLD.resource_kind
      AND later.provider_resource_id = OLD.provider_resource_id
      AND later.relation_kind = OLD.relation_kind
      AND later.clock_domain = OLD.clock_domain
      AND later.source_clock_us > OLD.source_clock_us
 )
BEGIN
    SELECT RAISE(ABORT, 'only dominated current candidates may be deleted');
END;

CREATE TRIGGER rrr_prune_dominated
AFTER INSERT ON resource_repository_relations
WHEN NEW.relation_kind IN ('owning_repository', 'base_repository', 'head_repository')
 AND NEW.source_clock_us IS NOT NULL
BEGIN
    DELETE FROM resource_repository_relations
    WHERE service_instance_uuidv4 = NEW.service_instance_uuidv4
      AND resource_kind = NEW.resource_kind
      AND provider_resource_id = NEW.provider_resource_id
      AND relation_kind = NEW.relation_kind
      AND clock_domain = NEW.clock_domain
      AND source_clock_us IS NOT NULL
      AND source_clock_us < NEW.source_clock_us;
END;
```

Test the complete guard set together, including raw SQL against disposable DBs.
Supported connections must enable/verify `foreign_keys` and `recursive_triggers`
and forbid arbitrary changes through public SQL. Ban `INSERT OR REPLACE` and
`ON CONFLICT DO UPDATE`; SQLite REPLACE may delete an existing row without firing
DELETE triggers when recursive triggers are disabled. No trigger scheme protects
against a privileged actor replacing the database or its schema. Generated FK
columns need indexed/UNIQUE parent columns and explicit typed revalidation.

Historical current candidates may be pruned by design. Do not promise perpetual
replay/rebinding detection for source coordinates no longer retained, and do not
add a hidden all-candidate history ledger to manufacture such a guarantee.

## 4. Physical design: Dispositions

A Disposition describes an action **reported about a particular mapping claim**.
`dispute` is not proof of falsity. `withdraw` is not effective revocation merely
because a row exists. `correct` references another existing claim and does not
reassign its issuer or prove that replacement true. Both claims remain immutable.

```sql
CREATE TABLE repository_mapping_dispositions (
    service_instance_uuidv4 TEXT NOT NULL,
    resource_kind TEXT NOT NULL CHECK (resource_kind = 'repository'),
    provider_resource_id TEXT NOT NULL,
    relation_kind TEXT NOT NULL CHECK (relation_kind = 'represents_repository'),
    claim_clock_json TEXT NOT NULL,
    claim_target_json TEXT NOT NULL,
    claim_provenance_json TEXT NOT NULL,
    disposition_kind TEXT NOT NULL CHECK (
        disposition_kind IN ('withdraw', 'correct', 'dispute')
    ),
    disposition_clock_json TEXT NOT NULL CHECK (
        p1_mapping_clock(disposition_clock_json) = 1
    ),
    disposition_provenance_json TEXT NOT NULL CHECK (
        p1_mapping_provenance(disposition_provenance_json) = 1
    ),
    observed_at_us INTEGER CHECK (
        observed_at_us IS NULL OR
        (typeof(observed_at_us) = 'integer' AND observed_at_us > 0)
    ),
    replacement_clock_json TEXT,
    replacement_target_json TEXT,
    replacement_provenance_json TEXT,
    CHECK (
        (disposition_kind = 'correct'
            AND replacement_clock_json IS NOT NULL
            AND replacement_target_json IS NOT NULL
            AND replacement_provenance_json IS NOT NULL)
        OR (disposition_kind != 'correct'
            AND replacement_clock_json IS NULL
            AND replacement_target_json IS NULL
            AND replacement_provenance_json IS NULL)
    ),
    CHECK (disposition_kind != 'correct'
        OR replacement_clock_json != claim_clock_json
        OR replacement_target_json != claim_target_json
        OR replacement_provenance_json != claim_provenance_json),
    PRIMARY KEY (
        service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind,
        claim_clock_json, claim_target_json, claim_provenance_json,
        disposition_kind, disposition_clock_json, disposition_provenance_json
    ),
    FOREIGN KEY (
        service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind,
        claim_clock_json, claim_target_json, claim_provenance_json
    ) REFERENCES resource_repository_relations (
        service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind,
        clock_json, target_json, provenance_json
    ) ON DELETE RESTRICT,
    FOREIGN KEY (
        service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind,
        replacement_clock_json, replacement_target_json, replacement_provenance_json
    ) REFERENCES resource_repository_relations (
        service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind,
        clock_json, target_json, provenance_json
    ) ON DELETE RESTRICT
) STRICT, WITHOUT ROWID;

CREATE INDEX rmd_by_provider_target ON repository_mapping_dispositions (
    service_instance_uuidv4, resource_kind, provider_resource_id,
    claim_target_json, disposition_kind
);
CREATE INDEX rmd_by_replacement ON repository_mapping_dispositions (
    service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind,
    replacement_clock_json, replacement_target_json, replacement_provenance_json
) WHERE replacement_target_json IS NOT NULL;
CREATE TRIGGER rmd_no_update BEFORE UPDATE ON repository_mapping_dispositions
BEGIN SELECT RAISE(ABORT, 'immutable mapping disposition'); END;
CREATE TRIGGER rmd_no_delete BEFORE DELETE ON repository_mapping_dispositions
BEGIN SELECT RAISE(ABORT, 'immutable mapping disposition'); END;
```

The required BEFORE INSERT replay guard must compare **all payload outside the
DispositionKey**: original `observed_at_us` and all three replacement columns.
A reused D key with another replacement is a rebind error even though both FKs
individually pass. The key deliberately does not allow a conflicting body to
silently replace the same reported Disposition. Distinct genuinely attributable
reports retain distinct original provenance. No extra `disposition_id` is added.

The first FK scopes targets to mapping claims. The second uses the same Provider
Resource columns; corrections cannot silently switch Provider Resource identity.
All-or-none replacement CHECK is essential because a partially NULL composite FK
would otherwise be bypassed. FK inheritance validates referenced claim JSON, but
wire/reader validation must also reject malformed references before SQL.

## 5. Event identity and report boundaries

At the baseline, Timeline Events are `ResourceKey.document` values: e.g.
`(G,'comment','["issue","4815","timeline_event","9017"]')`, with the real parent
Issue and Provider event ID. Keep those parent/document identity columns and FK.
A generic Timeline Event is not automatically a Transfer; typed intake must
verify the actual reported event kind and preserve its original evidence.

For one E17, keep separate rows `(E17,from,C17,R1,Palpha)` and
`(E17,to,C17,R2,Palpha)`. If Pbeta reports R3/R4 for E17, do not form R1/R4 by
joining on E17 alone. EventReportKey includes exact original clock and provenance.
Even within one report, multiple alternatives do not license a Cartesian product
of real events. Preserve the report's actual provided-role scope; no report-header
table is added. The wire/typed unit must distinguish an originally one-sided
report from a two-sided report truncated by selection. No supplied endpoint may
be silently dropped while retaining its complete-report meaning.

Issue affiliation R1 at T1 and R2 at T2 does not manufacture an event, intermediate
time, or Provider event ID. A later current Issue Repository is not evidence of
the destination of an earlier Transfer (there may have been another Transfer).
Event clocks do not overwrite unrelated current-candidate clock domains.

## 6. Qualified reads without Witness persistence

Conceptually, evaluate `mapping(claims, dispositions, available_original_evidence,
receiver_context)`. A report's presence, checksum, claimed issuer, `source=local`
or matching Catalog UUID never supplies the evidence parameter by itself.

| Evidence state | Required output meaning |
| --- | --- |
| One target report | Single reported candidate; not verified identity |
| Different target reports | Conflict with full alternatives and source qualifications |
| Third-party dispute | Reported objection; do not automatically withdraw its target |
| Claimed same-issuer withdrawal, no actual authority evidence | Withdrawal reported, effect unconfirmed |
| Genuine local source/actor/target/action evidence currently supports withdrawal | Qualified local effect for that exact original claim only |
| Evidence unavailable or contradictory | Unconfirmed/contradictory; never silently effective |
| Correct K1 to K2 with another issuer | Do not relabel K2's issuer or certify K2's target |
| Correction cycle or contradictory corrections | Explicit unresolved condition; no arrival/time/count winner |

No writable `is_effective`, current winner pointer, Witness table, Witness
counterevidence table or historical verification ledger is introduced. Pure
rechecking does not create a new Disposition. Genuine new issuer reports can be
stored with genuine independent provenance, not receiver time or relay as salt.

The evidence adapter must return only the actual bounded checks it can perform;
if none is implemented/available, the safe result is unconfirmed, not a fabricated
local authority. Reading may require explicitly available local evidence, but
must not silently execute Access routes, open credentials or make network calls.
Keep the DB snapshot and the actual external-evidence basis/uncertainty explicit;
a database snapshot does not freeze an external audit system.

## 7. Existing columns and integration delta

| Existing surface | Required disposition |
| --- | --- |
| `field_candidates.repository_uuidv4` generated column and special CHECK | Remove in the new format |
| `field_name='repository_uuidv4'` semantic writer/reader path | Remove; prohibit its reintroduction as a second normalized relationship authority |
| `field_candidates.value_json`, clocks/provenance/time, text-body FK | Keep for genuine general fields |
| Provider-observed URLs, numeric/opaque identifiers and source fields | Keep their genuine observed meanings; not executable Access configuration |
| `repository_context` | Keep local Repository registration/FK target; do not delete the table |
| `source_repositories`, known-positive guards | Keep; neither mapping withdrawal nor partial inventory deletes membership |
| `resources` parent/document columns and immutable identity guards | Keep; add typed-FK support index only |
| `resource_relations` | Keep Provider relations; no Witness data hidden here |
| `core_references` | Keep typed OID references; mapping withdrawal does not delete Git facts |
| Coverage scopes, claims, proofs, terminal/inventory evidence | Keep meanings, clocks and five-column claims; audit moved field scope as below |
| Exchange `repository_candidates` | Replace with role-aware relations and mapping Dispositions in a versioned wire contract |
| `ContextStore.admit_repository` / `repository_candidates` | Replace affected generic relationship paths with role-aware APIs |
| `NormalizedContextUnit.repository_uuidv4` | Audit registration preconditions versus actual evidence; do not mechanically rename every use to ownership |
| `DetachedResourceTransfer` | Actual current-affiliation reporting is not proof of a Provider Transfer event; route according to real semantics |

`configuration_json` may contain locally authored domain descriptions while
Provider Repository attributes use field candidates. Do not erase legitimately
different provenance merely because names match. Audit any duplicate mutable
source of the same fact; no unrelated configuration redesign is authorized.

### Implementation proof obligations, not hidden design changes

1. Preserve the exact Provider relation and **the actual mapping ClaimKey support**
   of any resolved Core-target report. A later disputed/withdrawn mapping must
   not make a cached resolved edge silently authoritative. Do not use the mapping
   observation clock as a fabricated PR clock, or edit old source provenance.
   Show the typed dependency representation and qualified reads in the schema/
   intake implementation PR; unresolved support withholds resolution.
2. `resource_relations` has immutable group semantics, whereas some Provider
   relations describe changing current fields. Preserve actual relation scopes
   and original clocks and expose current qualifications without a second winner
   table or blind union. Missing and explicit-null Provider references must remain
   distinct even before Core correspondence is known.
3. Coverage for an old `repository_uuidv4` field cannot simply be relabeled as
   complete coverage of all six roles. Preserve the actually observed scope/proof;
   document exact moved-role scope encoding in the implementation review. No
   sixth authoritative Coverage claim column or fabricated complete claim.
4. Structured event roles and issuer grammar require actual adapter validation.
   SQL FK/CHECK does not establish authorship, actual Transfer type or actor
   entitlement. These limits are accepted; do not add PKI as a follow-up blocker.
5. All source validators, serializers, readers, registry/fingerprint tools and
   installed distributions must agree on the new schema before activation.
   An old coherent schema is an unsupported format, not automatically corruption.

If completing an obligation would change the selected identity, retention or
permission policy, stop that dependent implementation and report the concrete
conflict. None of the illustrative JSON helpers or new field names in this
engineering document authorizes silently changing a selected semantic rule.

## References

- [Baseline Context SQL](https://github.com/TakashiSasaki/git-repo-db/blob/1134e200eb4ac9ec45bf3fae3be695e2bb786a8d/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql)
- [Baseline Context admission](https://github.com/TakashiSasaki/git-repo-db/blob/1134e200eb4ac9ec45bf3fae3be695e2bb786a8d/src/repo_catalog/adapters/sqlite/p1_context.py)
- [Baseline GitHub normalization](https://github.com/TakashiSasaki/git-repo-db/blob/1134e200eb4ac9ec45bf3fae3be695e2bb786a8d/src/repo_catalog/adapters/github/production_intake.py)
- [SQLite generated columns](https://www.sqlite.org/gencol.html),
  [foreign keys](https://www.sqlite.org/foreignkeys.html),
  [REPLACE behavior](https://www.sqlite.org/lang_conflict.html)
- [Selective Exchange](selective-exchange-contract.md)
