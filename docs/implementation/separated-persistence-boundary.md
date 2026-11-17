# Separated persistence class mapping

Ordinary CLI composition uses the separated stores. DDL-derived fields/keys are implementation facts. Dedicated row types are generated separately from observed Python inputs/projections; AST presence does not prove row serialization or admission correctness.

Seven responsibility roles do not require seven initialized/open DBs. Operational retains required durable work/recovery state; row kind does not determine durability or authority. No retained DB is read.

Coverage: registered separated product-table definitions; SQLite internals and runtime-created virtual/shadow tables are outside this mapping.

## Core — `p1.core`

Git identity, attributed immutable claims, allowed retained representations and receiver evidence.

Composition: `packages/runtime/src/repo_catalog/adapters/sqlite/p1_schema.py` (repo-catalog-runtime). This is not table-source ownership.

DDL SHA-256: `7b33bbbfb8977f59f3d1db338fd9148d65645f6c75ec8d73bff95c5431290cc6`; format: `repo-catalog/p1-isolated-4`; schema version: `None`.

DDL contributions: `packages/runtime/src/repo_catalog/adapters/sqlite/p1_schema.py` (repo-catalog-runtime); `packages/core/src/repo_catalog/adapters/sqlite/p1_ddl/core.sql` (repo-catalog-core); `packages/contracts/src/repo_catalog/adapters/sqlite/p1_ddl/coverage.sql` (repo-catalog-contracts)

| Persistent class | Kind | Table | Ordered primary key | Generated row type | Python input/projection |
| --- | --- | --- | --- | --- | --- |
| Core.Repository | entity | `repositories` | `(repository_uuidv4)` | `RepositoryRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.GitObject | entity | `git_objects` | `(object_format, object_oid)` | `GitObjectRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.RepositoryClaim | association | `repository_claims` | `(repository_uuidv4, field, value, provenance)` | `RepositoryClaimRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `RepositoryClaim` (packages/core/src/repo_catalog/domain/p1_core.py) |
| Core.ScalarClaim | association | `scalar_claims` | `(object_format, object_oid, field, value, provenance)` | `ScalarClaimRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `ScalarClaim` (packages/core/src/repo_catalog/domain/p1_core.py) |
| Core.RelationGroup | association | `relation_groups` | `(object_format, object_oid, relation, scope, status, membership, provenance)` | `RelationGroupRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `RelationGroup` (packages/core/src/repo_catalog/domain/p1_core.py) |
| Core.GitObservation | entity | `git_observations` | `(capture_origin_uuidv4, capture_uuidv4, repository_uuidv4, kind, scope, value, provenance)` | `GitObservationRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `GitObservation` (packages/core/src/repo_catalog/domain/p1_core.py) |
| Core.RefObservation | entity | `ref_observations` | `(observation_origin_uuidv4, ref_observation_uuidv7)` | `RefObservationRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `RefObservation` (packages/core/src/repo_catalog/domain/ref_observation.py) |
| Core.RefObservationClaim | association | `ref_observation_claims` | `(observation_origin_uuidv4, ref_observation_uuidv7, provenance)` | `RefObservationClaimRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `RefObservationClaim` (packages/core/src/repo_catalog/domain/ref_observation.py) |
| Core.RefEnumerationObservation | entity | `ref_enumeration_observations` | `(observation_origin_uuidv4, enumeration_uuidv7)` | `RefEnumerationObservationRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `RefEnumerationObservation` (packages/core/src/repo_catalog/domain/ref_observation.py) |
| Core.RefEnumerationLink | association | `ref_enumeration_links` | `(enumeration_origin_uuidv4, enumeration_uuidv7, observation_origin_uuidv4, ref_observation_uuidv7, claim_provenance)` | `RefEnumerationLinkRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `RefEnumerationLink` (packages/core/src/repo_catalog/domain/ref_observation.py) |
| Core.NotesMapping | association | `notes_mappings` | `(object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, annotated_object_oid, note_object_oid, mapping_path_json)` | `NotesMappingRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `NotesMapping` (packages/core/src/repo_catalog/domain/ref_observation.py) |
| Core.NotesMappingClaim | association | `notes_mapping_claims` | `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, annotated_object_oid, note_object_oid, mapping_path_json, provenance)` | `NotesMappingClaimRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `NotesMappingClaim` (packages/core/src/repo_catalog/domain/ref_observation.py) |
| Core.NotesMappingGroup | association | `notes_mapping_groups` | `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, group_scope, status, membership, provenance)` | `NotesMappingGroupRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `NotesMappingGroup` (packages/core/src/repo_catalog/domain/ref_observation.py) |
| Core.NotesMappingEvidence | association | `notes_mapping_evidence` | `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, annotated_object_oid, note_object_oid, mapping_path_json, verification_scope, provenance, proof_bundle)` | `NotesMappingEvidenceRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `NotesMappingEvidenceRecord` (packages/core/src/repo_catalog/domain/ref_observation.py) |
| Core.RetainedMetadata | entity | `retained_metadata` | `(object_format, object_oid, physical_copy_uuidv4)` | `RetainedMetadataRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.RetainedNote | entity | `ref_retained_notes` | `(object_format, object_oid, physical_copy_uuidv4)` | `RetainedNoteRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.IntrinsicClaim | association | `intrinsic_claims` | `(object_format, object_oid, field, value, provenance, physical_copy_uuidv4)` | `IntrinsicClaimRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.IntrinsicGroup | association | `intrinsic_groups` | `(object_format, object_oid, relation, scope, status, membership, provenance, physical_copy_uuidv4)` | `IntrinsicGroupRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.CoverageScope | entity | `coverage_scopes` | `(owner_kind, owner_coordinates_json)` | `CoverageScopeRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | row-input: `CoreCoverageScope` (packages/core/src/repo_catalog/domain/p1_core.py) |
| Core.CoverageClaim | association | `coverage_claims` | `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)` | `CoverageClaimRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.CoreCoverageProof | association | `core_coverage_proofs` | `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state, members_json, provenance)` | `CoreCoverageProofRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.RefCoverageProof | association | `ref_coverage_proofs` | `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state, observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, group_scope, group_status, group_membership, group_provenance, verification_provenance)` | `RefCoverageProofRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.StoreIdentity | infrastructure | `store_identity` | `(store_role)` | `StoreIdentityRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.RepositoryIdentityAssertion | association | `repository_identity_assertions` | `(relation_uuidv4, record_json, provenance)` | `RepositoryIdentityAssertionRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |
| Core.RepositoryIdentityCancellation | association | `repository_identity_cancellations` | `(cancellation_uuidv4, relation_uuidv4, record_json, provenance)` | `RepositoryIdentityCancellationRow` (packages/core/src/repo_catalog/adapters/sqlite/core_rows.py) | no Python input/projection recorded |

### Row details and same-file physical FKs

- **Core.Repository**: Stable repository UUID identity; claims and observations are separate rows. Fields: `repository_uuidv4 TEXT`.
- **Core.GitObject**: Nominal object identity is the ordered object-format/OID pair, independent of retained bytes. Fields: `object_format TEXT, object_oid TEXT`.
- **Core.RepositoryClaim**: Attributed repository field assertion; not a mutable repository property. Fields: `repository_uuidv4 TEXT, field TEXT, value TEXT, provenance TEXT`.
  - physical FK: `(repository_uuidv4)` → Core.Repository `(repository_uuidv4)`.
- **Core.ScalarClaim**: Attributed scalar assertion about a nominal Git object. Fields: `object_format TEXT, object_oid TEXT, field TEXT, value TEXT, provenance TEXT`.
  - physical FK: `(object_format, object_oid)` → Core.GitObject `(object_format, object_oid)`.
- **Core.RelationGroup**: Atomic scoped relation membership assertion; nested members encode into one membership value. Fields: `object_format TEXT, object_oid TEXT, relation TEXT, scope TEXT, status TEXT, membership TEXT, provenance TEXT`.
  - physical FK: `(object_format, object_oid)` → Core.GitObject `(object_format, object_oid)`.
- **Core.GitObservation**: Attributed capture occurrence with repository, kind, scope, value and provenance. Fields: `capture_origin_uuidv4 TEXT, capture_uuidv4 TEXT, repository_uuidv4 TEXT, kind TEXT, scope TEXT, value TEXT, provenance TEXT`.
  - physical FK: `(repository_uuidv4)` → Core.Repository `(repository_uuidv4)`.
- **Core.RefObservation**: Origin-qualified ref observation occurrence; name/source/visibility belong to its payload. Fields: `observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT, repository_uuidv4 TEXT, ref_name_bytes BLOB, source_attribution TEXT, visibility_scope TEXT, observed_at_us INTEGER`.
  - physical FK: `(repository_uuidv4)` → Core.Repository `(repository_uuidv4)`.
- **Core.RefObservationClaim**: Attributed presence/absence/ref-form result for one ref observation. Fields: `observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT, provenance TEXT, presence_state TEXT, ref_form TEXT, direct_format TEXT, direct_target_object_oid TEXT, symbolic_target_ref_name BLOB, resolved_format TEXT, resolved_target_object_oid TEXT, peeled_format TEXT, peeled_target_object_oid TEXT, root_format TEXT, root_object_oid TEXT, absence_evidence TEXT`.
  - physical FK: `(root_format, root_object_oid)` → Core.GitObject `(object_format, object_oid)`.
  - physical FK: `(peeled_format, peeled_target_object_oid)` → Core.GitObject `(object_format, object_oid)`.
  - physical FK: `(resolved_format, resolved_target_object_oid)` → Core.GitObject `(object_format, object_oid)`.
  - physical FK: `(direct_format, direct_target_object_oid)` → Core.GitObject `(object_format, object_oid)`.
  - physical FK: `(observation_origin_uuidv4, ref_observation_uuidv7)` → Core.RefObservation `(observation_origin_uuidv4, ref_observation_uuidv7)`.
- **Core.RefEnumerationObservation**: Scoped enumeration event; its completion and link count do not replace the member links. Fields: `observation_origin_uuidv4 TEXT, enumeration_uuidv7 TEXT, repository_uuidv4 TEXT, source_attribution TEXT, visibility_scope TEXT, enumeration_scope_json TEXT, enumeration_state TEXT, completion_coordinate TEXT, observed_at_us INTEGER, byte_limit INTEGER, ref_limit INTEGER, link_count INTEGER`.
  - physical FK: `(repository_uuidv4)` → Core.Repository `(repository_uuidv4)`.
- **Core.RefEnumerationLink**: Ordered link between an enumeration and an attributed ref result. Fields: `enumeration_origin_uuidv4 TEXT, enumeration_uuidv7 TEXT, observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT, claim_provenance TEXT, derivation TEXT, position INTEGER`.
  - physical FK: `(observation_origin_uuidv4, ref_observation_uuidv7, claim_provenance)` → Core.RefObservationClaim `(observation_origin_uuidv4, ref_observation_uuidv7, provenance)`.
  - physical FK: `(enumeration_origin_uuidv4, enumeration_uuidv7)` → Core.RefEnumerationObservation `(observation_origin_uuidv4, enumeration_uuidv7)`.
- **Core.NotesMapping**: Shared interpretation of a captured root/target/note/path; not repository membership or file-body permission. Fields: `object_format TEXT, root_object_oid TEXT, interpretation_kind TEXT, interpretation_version TEXT, interpretation_scope TEXT, annotated_object_oid TEXT, note_object_oid TEXT, mapping_path_json TEXT`.
  - physical FK: `(object_format, note_object_oid)` → Core.GitObject `(object_format, object_oid)`.
  - physical FK: `(object_format, annotated_object_oid)` → Core.GitObject `(object_format, object_oid)`.
  - physical FK: `(object_format, root_object_oid)` → Core.GitObject `(object_format, object_oid)`.
- **Core.NotesMappingClaim**: Attribution connecting an exact ref claim and a shared mapping. Fields: `observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT, ref_claim_provenance TEXT, object_format TEXT, root_object_oid TEXT, interpretation_kind TEXT, interpretation_version TEXT, interpretation_scope TEXT, annotated_object_oid TEXT, note_object_oid TEXT, mapping_path_json TEXT, provenance TEXT`.
  - physical FK: `(object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, annotated_object_oid, note_object_oid, mapping_path_json)` → Core.NotesMapping `(object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, annotated_object_oid, note_object_oid, mapping_path_json)`.
  - physical FK: `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid)` → Core.RefObservationClaim `(observation_origin_uuidv4, ref_observation_uuidv7, provenance, root_format, root_object_oid)`.
- **Core.NotesMappingGroup**: Atomic scoped mapping membership assertion for an exact ref claim. Fields: `observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT, ref_claim_provenance TEXT, object_format TEXT, root_object_oid TEXT, interpretation_kind TEXT, interpretation_version TEXT, interpretation_scope TEXT, group_scope TEXT, status TEXT, membership TEXT, provenance TEXT`.
  - physical FK: `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid)` → Core.RefObservationClaim `(observation_origin_uuidv4, ref_observation_uuidv7, provenance, root_format, root_object_oid)`.
- **Core.NotesMappingEvidence**: Receiver evidence for one attributed mapping; evidence is separate from a source assertion. Fields: `observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT, ref_claim_provenance TEXT, object_format TEXT, root_object_oid TEXT, interpretation_kind TEXT, interpretation_version TEXT, interpretation_scope TEXT, annotated_object_oid TEXT, note_object_oid TEXT, mapping_path_json TEXT, verification_scope TEXT, provenance TEXT, proof_bundle TEXT`.
  - physical FK: `(object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, annotated_object_oid, note_object_oid, mapping_path_json)` → Core.NotesMapping `(object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, annotated_object_oid, note_object_oid, mapping_path_json)`.
  - physical FK: `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid)` → Core.RefObservationClaim `(observation_origin_uuidv4, ref_observation_uuidv7, provenance, root_format, root_object_oid)`.
- **Core.RetainedMetadata**: Permitted Git metadata representation and its physical-copy identity; this is domain data, not store infrastructure. Fields: `object_format TEXT, object_oid TEXT, physical_copy_uuidv4 TEXT, native_type TEXT, body BLOB, size INTEGER, digest_sha256 TEXT`.
  - physical FK: `(object_format, object_oid)` → Core.GitObject `(object_format, object_oid)`.
- **Core.RetainedNote**: Allowed note body representation with a physical-copy identity; no ordinary file-body archive. Fields: `object_format TEXT, object_oid TEXT, physical_copy_uuidv4 TEXT, body BLOB, size INTEGER, digest_sha256 TEXT, observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT, ref_claim_provenance TEXT, role_format TEXT, root_object_oid TEXT, interpretation_kind TEXT, interpretation_version TEXT, interpretation_scope TEXT, annotated_object_oid TEXT, note_object_oid TEXT, mapping_path_json TEXT, verification_scope TEXT, role_provenance TEXT, proof_bundle TEXT`.
  - physical FK: `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, role_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, annotated_object_oid, note_object_oid, mapping_path_json, verification_scope, role_provenance, proof_bundle)` → Core.NotesMappingEvidence `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, annotated_object_oid, note_object_oid, mapping_path_json, verification_scope, provenance, proof_bundle)`.
- **Core.IntrinsicClaim**: Receiver-derived scalar evidence qualified by the physical copy used. Fields: `object_format TEXT, object_oid TEXT, field TEXT, value TEXT, provenance TEXT, physical_copy_uuidv4 TEXT`.
  - physical FK: `(object_format, object_oid, physical_copy_uuidv4)` → Core.RetainedMetadata `(object_format, object_oid, physical_copy_uuidv4)`.
  - physical FK: `(object_format, object_oid, field, value, provenance)` → Core.ScalarClaim `(object_format, object_oid, field, value, provenance)`.
- **Core.IntrinsicGroup**: Receiver-derived relation evidence qualified by the physical copy used. Fields: `object_format TEXT, object_oid TEXT, relation TEXT, scope TEXT, status TEXT, membership TEXT, provenance TEXT, physical_copy_uuidv4 TEXT`.
  - physical FK: `(object_format, object_oid, physical_copy_uuidv4)` → Core.RetainedMetadata `(object_format, object_oid, physical_copy_uuidv4)`.
  - physical FK: `(object_format, object_oid, relation, scope, status, membership, provenance)` → Core.RelationGroup `(object_format, object_oid, relation, scope, status, membership, provenance)`.
- **Core.CoverageScope**: Typed coverage owner coordinate in Core; independent of the identically named Context table. Fields: `owner_kind TEXT, owner_coordinates_json TEXT, repository_uuidv4 TEXT, observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT, object_format TEXT, object_oid TEXT, field TEXT, coverage_kind TEXT`.
  - physical FK: `(object_format, object_oid)` → Core.GitObject `(object_format, object_oid)`.
  - physical FK: `(repository_uuidv4)` → Core.Repository `(repository_uuidv4)`.
  - physical FK: `(observation_origin_uuidv4, ref_observation_uuidv7)` → Core.RefObservation `(observation_origin_uuidv4, ref_observation_uuidv7)`.
- **Core.CoverageClaim**: One attributed coverage state/time coordinate; shared Contracts values are not a dedicated Core row type. Fields: `owner_kind TEXT, owner_coordinates_json TEXT, observed_at_us INTEGER, coverage_state TEXT, details_json TEXT`.
  - physical FK: `(owner_kind, owner_coordinates_json)` → Core.CoverageScope `(owner_kind, owner_coordinates_json)`.
- **Core.CoreCoverageProof**: Core-specific evidence for an exact coverage claim; not an infrastructure health marker. Fields: `owner_kind TEXT, owner_coordinates_json TEXT, observed_at_us INTEGER, coverage_state TEXT, members_json TEXT, provenance TEXT`.
  - physical FK: `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)` → Core.CoverageClaim `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)`.
- **Core.RefCoverageProof**: Evidence connecting exact ref/mapping group coordinates to an exact coverage claim. Fields: `owner_kind TEXT, owner_coordinates_json TEXT, observed_at_us INTEGER, coverage_state TEXT, observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT, ref_claim_provenance TEXT, object_format TEXT, root_object_oid TEXT, interpretation_kind TEXT, interpretation_version TEXT, interpretation_scope TEXT, group_scope TEXT, group_status TEXT, group_membership TEXT, group_provenance TEXT, verification_provenance TEXT, structures_json TEXT`.
  - physical FK: `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, group_scope, group_status, group_membership, group_provenance)` → Core.NotesMappingGroup `(observation_origin_uuidv4, ref_observation_uuidv7, ref_claim_provenance, object_format, root_object_oid, interpretation_kind, interpretation_version, interpretation_scope, group_scope, status, membership, provenance)`.
  - physical FK: `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)` → Core.CoverageClaim `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)`.
- **Core.StoreIdentity**: Core format/instance metadata; row role says nothing about mutability or recovery policy. Fields: `store_role TEXT, repository_uuidv4 TEXT, catalog_instance_uuidv4 TEXT`.
- **Core.RepositoryIdentityAssertion**: Reported repository identity assertion occurrence with exact original canonical payload/provenance; cancellations may precede assertions and status never physically merges identities or establishes authenticity. Fields: `relation_uuidv4 TEXT, record_json TEXT, provenance TEXT`.
- **Core.RepositoryIdentityCancellation**: Reported repository identity cancellation occurrence with exact original canonical payload/provenance; cancellations may precede assertions and status never physically merges identities or establishes authenticity. Fields: `cancellation_uuidv4 TEXT, relation_uuidv4 TEXT, record_json TEXT, provenance TEXT`.

## Context — `p1.context`

Service/source registrations, generalized resources, attributed relations/text and Context coverage evidence.

Composition: `packages/runtime/src/repo_catalog/adapters/sqlite/p1_schema.py` (repo-catalog-runtime). This is not table-source ownership.

DDL SHA-256: `8009b078694df2127bb9c9799119216b8e187f225219bba62ff2b82153d352f0`; format: `repo-catalog/p1-isolated-4`; schema version: `None`.

DDL contributions: `packages/runtime/src/repo_catalog/adapters/sqlite/p1_schema.py` (repo-catalog-runtime); `packages/context/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql` (repo-catalog-context); `packages/contracts/src/repo_catalog/adapters/sqlite/p1_ddl/coverage.sql` (repo-catalog-contracts)

| Persistent class | Kind | Table | Ordered primary key | Generated row type | Python input/projection |
| --- | --- | --- | --- | --- | --- |
| Context.ServiceInstance | entity | `providers` | `(service_instance_uuidv4)` | `ServiceInstanceRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.SourceRegistration | entity | `sources` | `(source_registration_uuidv4)` | `SourceRegistrationRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.Resource | entity | `resources` | `(service_instance_uuidv4, resource_kind, provider_resource_id)` | `ResourceRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.FieldCandidate | association | `field_candidates` | `(service_instance_uuidv4, resource_kind, provider_resource_id, field_name, clock_json, value_json, provenance_json)` | `FieldCandidateRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | row-input: `FieldCandidate` (packages/context/src/repo_catalog/domain/p1_context.py) |
| Context.TextBody | entity | `text_bodies` | `(sha256)` | `TextBodyRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.ResourceRelation | association | `resource_relations` | `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, members_json, provenance_json, scope_json)` | `ResourceRelationRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | row-input: `ResourceRelation` (packages/context/src/repo_catalog/domain/production_context.py) |
| Context.ResourceRepositoryRelation | association | `resource_repository_relations` | `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, clock_json, target_json, provenance_json)` | `ResourceRepositoryRelationRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | row-input: `ResourceRepositoryRelation` (packages/context/src/repo_catalog/domain/p1_context.py) |
| Context.RepositoryMappingDisposition | association | `repository_mapping_dispositions` | `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, claim_clock_json, claim_target_json, claim_provenance_json, disposition_kind, disposition_clock_json, disposition_provenance_json)` | `RepositoryMappingDispositionRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | row-input: `MappingDisposition` (packages/context/src/repo_catalog/domain/p1_context.py) |
| Context.RepositoryContext | entity | `repository_context` | `(repository_uuidv4)` | `RepositoryContextRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.SourceRepository | association | `source_repositories` | `(source_registration_uuidv4, repository_uuidv4)` | `SourceRepositoryRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.SourceInventoryEvidence | association | `source_inventory_evidence` | `(source_registration_uuidv4, scope_json, observed_at_us, coverage_state, terminal, members_json, provenance_json, provider_repositories_json)` | `SourceInventoryEvidenceRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.Collection | entity | `collections` | `(service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, provenance_json)` | `CollectionRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.CollectionTerminal | association | `collection_terminals` | `(service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, provenance_json, observed_at_us, terminal_state, members_json)` | `CollectionTerminalRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.CoreReference | association | `core_references` | `(service_instance_uuidv4, resource_kind, provider_resource_id, role, object_format, object_oid, provenance_json)` | `CoreReferenceRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | row-input: `CoreReference` (packages/context/src/repo_catalog/domain/production_context.py) |
| Context.CoverageScope | entity | `coverage_scopes` | `(owner_kind, owner_coordinates_json)` | `CoverageScopeRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | row-input: `CoverageScope` (packages/context/src/repo_catalog/domain/p1_context.py) |
| Context.CoverageClaim | association | `coverage_claims` | `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)` | `CoverageClaimRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.CoverageProof | association | `coverage_proofs` | `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state, service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, provenance_json, terminal_observed_at_us, terminal_state, members_json)` | `CoverageProofRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.SourceCoverageProof | association | `source_coverage_proofs` | `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state, source_registration_uuidv4, scope_json, inventory_observed_at_us, inventory_state, terminal, members_json, provenance_json, provider_repositories_json)` | `SourceCoverageProofRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.StoreIdentity | infrastructure | `store_identity` | `(store_role)` | `StoreIdentityRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.ServiceIdentityAssertion | association | `service_identity_assertions` | `(relation_uuidv4, record_json, provenance)` | `ServiceIdentityAssertionRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |
| Context.ServiceIdentityCancellation | association | `service_identity_cancellations` | `(cancellation_uuidv4, relation_uuidv4, record_json, provenance)` | `ServiceIdentityCancellationRow` (packages/context/src/repo_catalog/adapters/sqlite/context_rows.py) | no Python input/projection recorded |

### Row details and same-file physical FKs

- **Context.ServiceInstance**: Service-instance UUID registration, distinct from a local connection or access scope. Fields: `service_instance_uuidv4 TEXT, provider_kind TEXT, configuration_json TEXT`.
- **Context.SourceRegistration**: Source-registration identity and registration payload, independent of source inventory evidence. Fields: `source_registration_uuidv4 TEXT, service_instance_uuidv4 TEXT, configuration_json TEXT`.
  - physical FK: `(service_instance_uuidv4)` → Context.ServiceInstance `(service_instance_uuidv4)`.
- **Context.Resource**: Service-scoped typed resource identity; ResourceKey is a value, not this persistent row. Fields: `service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, identifier_namespace_kind TEXT, identifier_namespace_id TEXT, document_kind TEXT, provider_document_id TEXT, reference_document_kind TEXT`.
  - physical FK: `(service_instance_uuidv4)` → Context.ServiceInstance `(service_instance_uuidv4)`.
- **Context.FieldCandidate**: Attributed field candidate with nested resource/clock values and adapter-derived columns. Fields: `service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, field_name TEXT, value_json TEXT, clock_json TEXT, provenance_json TEXT, observed_at_us INTEGER, clock_domain TEXT, source_clock_us INTEGER, text_body_sha256 TEXT`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id)`.
  - physical FK: `(text_body_sha256)` → Context.TextBody `(sha256)`.
- **Context.TextBody**: Exact Context text bytes indexed by SHA-256; unrelated to ordinary repository-file content retention. Fields: `sha256 TEXT, text_value TEXT`.
- **Context.ResourceRelation**: Scoped resource relation with atomic member representation. Fields: `service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, relation_kind TEXT, members_json TEXT, provenance_json TEXT, scope_json TEXT, observed_at_us INTEGER, parent_service TEXT, parent_kind TEXT, parent_id TEXT, source_document_kind TEXT, report_clock_json TEXT, event_support_members_json TEXT, event_support_provenance_json TEXT, event_support_scope_json TEXT, event_support_service TEXT, event_support_kind TEXT, event_support_id TEXT, event_support_relation_kind TEXT, event_document_kind TEXT`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, event_document_kind, event_support_kind, event_support_id)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id, reference_document_kind, identifier_namespace_kind, identifier_namespace_id)`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, event_support_relation_kind, event_support_members_json, event_support_provenance_json, event_support_scope_json, event_document_kind, event_support_kind)` → Context.ResourceRelation `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, members_json, provenance_json, scope_json, source_document_kind, parent_kind)`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, source_document_kind)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id, reference_document_kind)`.
  - physical FK: `(parent_service, parent_kind, parent_id)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id)`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id)`.
- **Context.ResourceRepositoryRelation**: Attributed typed repository relation; nested claim coordinates are flattened by the adapter. Fields: `service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, relation_kind TEXT, target_json TEXT, clock_json TEXT, provenance_json TEXT, observed_at_us INTEGER, repository_uuidv4 TEXT, clock_domain TEXT, source_clock_us INTEGER, event_report_members_json TEXT, event_report_scope_json TEXT, event_report_kind TEXT, event_document_kind TEXT, event_parent_resource_kind TEXT`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, event_report_kind, event_report_members_json, provenance_json, event_report_scope_json)` → Context.ResourceRelation `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, members_json, provenance_json, scope_json)`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, event_document_kind, event_parent_resource_kind)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id, reference_document_kind, identifier_namespace_kind)`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id)`.
  - physical FK: `(repository_uuidv4)` → Context.RepositoryContext `(repository_uuidv4)`.
- **Context.RepositoryMappingDisposition**: Immutable disposition of an exact mapping claim; not a mutable canonical repository shortcut. Fields: `service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, relation_kind TEXT, claim_clock_json TEXT, claim_target_json TEXT, claim_provenance_json TEXT, disposition_kind TEXT, disposition_clock_json TEXT, disposition_provenance_json TEXT, observed_at_us INTEGER, replacement_clock_json TEXT, replacement_target_json TEXT, replacement_provenance_json TEXT`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, replacement_clock_json, replacement_target_json, replacement_provenance_json)` → Context.ResourceRepositoryRelation `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, clock_json, target_json, provenance_json)`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, claim_clock_json, claim_target_json, claim_provenance_json)` → Context.ResourceRepositoryRelation `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, clock_json, target_json, provenance_json)`.
- **Context.RepositoryContext**: Context-local registration of a repository coordinate; does not own Core repository identity. Fields: `repository_uuidv4 TEXT, configuration_json TEXT`.
- **Context.SourceRepository**: Known positive Source/Repository membership; partial inventories do not delete previous positives. Fields: `source_registration_uuidv4 TEXT, repository_uuidv4 TEXT, attributes_json TEXT`.
  - physical FK: `(repository_uuidv4)` → Context.RepositoryContext `(repository_uuidv4)`.
  - physical FK: `(source_registration_uuidv4)` → Context.SourceRegistration `(source_registration_uuidv4)`.
- **Context.SourceInventoryEvidence**: Attributed scoped source inventory evidence, including honest terminal and member coordinates. Fields: `source_registration_uuidv4 TEXT, scope_json TEXT, observed_at_us INTEGER, coverage_state TEXT, terminal INTEGER, members_json TEXT, provenance_json TEXT, provider_repositories_json TEXT`.
  - physical FK: `(source_registration_uuidv4)` → Context.SourceRegistration `(source_registration_uuidv4)`.
- **Context.Collection**: Collection scope/registration for a resource; one CollectionObservation input is not a stand-alone row mirror. Fields: `service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, collection_kind TEXT, provenance_json TEXT, scope_json TEXT`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id)`.
- **Context.CollectionTerminal**: One attributed terminal collection observation, independent of collection registration. Fields: `service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, collection_kind TEXT, provenance_json TEXT, observed_at_us INTEGER, terminal_state TEXT, members_json TEXT`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, provenance_json)` → Context.Collection `(service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, provenance_json)`.
- **Context.CoreReference**: Resource-associated nominal Git object coordinate; cross-domain meaning is not a cross-file physical FK. Fields: `service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, role TEXT, object_format TEXT, object_oid TEXT, provenance_json TEXT`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id)`.
- **Context.CoverageScope**: Context-owned typed coverage coordinate, separate from Core coverage. Fields: `owner_kind TEXT, owner_coordinates_json TEXT, repository_uuidv4 TEXT, source_registration_uuidv4 TEXT, source_scope_json TEXT, service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, collection_kind TEXT, collection_provenance_json TEXT, field_name TEXT, coverage_kind TEXT`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, collection_provenance_json)` → Context.Collection `(service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, provenance_json)`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id)` → Context.Resource `(service_instance_uuidv4, resource_kind, provider_resource_id)`.
  - physical FK: `(source_registration_uuidv4, repository_uuidv4)` → Context.SourceRepository `(source_registration_uuidv4, repository_uuidv4)`.
  - physical FK: `(source_registration_uuidv4)` → Context.SourceRegistration `(source_registration_uuidv4)`.
  - physical FK: `(repository_uuidv4)` → Context.RepositoryContext `(repository_uuidv4)`.
- **Context.CoverageClaim**: One Context coverage claim; shared helper values are not a dedicated row class. Fields: `owner_kind TEXT, owner_coordinates_json TEXT, observed_at_us INTEGER, coverage_state TEXT, details_json TEXT`.
  - physical FK: `(owner_kind, owner_coordinates_json)` → Context.CoverageScope `(owner_kind, owner_coordinates_json)`.
- **Context.CoverageProof**: Evidence connecting exact collection terminal and coverage coordinates. Fields: `owner_kind TEXT, owner_coordinates_json TEXT, observed_at_us INTEGER, coverage_state TEXT, service_instance_uuidv4 TEXT, resource_kind TEXT, provider_resource_id TEXT, collection_kind TEXT, provenance_json TEXT, terminal_observed_at_us INTEGER, terminal_state TEXT, members_json TEXT`.
  - physical FK: `(service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, provenance_json, terminal_observed_at_us, terminal_state, members_json)` → Context.CollectionTerminal `(service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, provenance_json, observed_at_us, terminal_state, members_json)`.
  - physical FK: `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)` → Context.CoverageClaim `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)`.
- **Context.SourceCoverageProof**: Evidence connecting exact source inventory and coverage coordinates. Fields: `owner_kind TEXT, owner_coordinates_json TEXT, observed_at_us INTEGER, coverage_state TEXT, source_registration_uuidv4 TEXT, scope_json TEXT, inventory_observed_at_us INTEGER, inventory_state TEXT, terminal INTEGER, members_json TEXT, provenance_json TEXT, provider_repositories_json TEXT`.
  - physical FK: `(source_registration_uuidv4, scope_json, inventory_observed_at_us, inventory_state, terminal, members_json, provenance_json, provider_repositories_json)` → Context.SourceInventoryEvidence `(source_registration_uuidv4, scope_json, observed_at_us, coverage_state, terminal, members_json, provenance_json, provider_repositories_json)`.
  - physical FK: `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)` → Context.CoverageClaim `(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)`.
- **Context.StoreIdentity**: Context instance/format metadata; independent of the Core store identity. Fields: `store_role TEXT, repository_uuidv4 TEXT, catalog_instance_uuidv4 TEXT`.
- **Context.ServiceIdentityAssertion**: Reported service identity assertion occurrence with exact original canonical payload/provenance; cancellations may precede assertions and status never physically merges identities or establishes authenticity. Fields: `relation_uuidv4 TEXT, record_json TEXT, provenance TEXT`.
- **Context.ServiceIdentityCancellation**: Reported service identity cancellation occurrence with exact original canonical payload/provenance; cancellations may precede assertions and status never physically merges identities or establishes authenticity. Fields: `cancellation_uuidv4 TEXT, relation_uuidv4 TEXT, record_json TEXT, provenance TEXT`.

## Access — `access`

Local connection configuration, locator bindings, scope controls and local approvals.

Composition: `packages/access/src/repo_catalog/adapters/sqlite/access_schema.py` (repo-catalog-access). This is not table-source ownership.

DDL SHA-256: `89bcafeda815150fa4770f5758edf7d2d36d505b76717aa19054f9ad689765da`; format: `repo-catalog/access-2`; schema version: `2`.

DDL contributions: `packages/access/src/repo_catalog/adapters/sqlite/access_schema.py` (repo-catalog-access); `packages/access/src/repo_catalog/adapters/sqlite/access_ddl/registry.sql` (repo-catalog-access); `packages/access/src/repo_catalog/adapters/sqlite/access_ddl/connections.sql` (repo-catalog-access)

| Persistent class | Kind | Table | Ordered primary key | Generated row type | Python input/projection |
| --- | --- | --- | --- | --- | --- |
| Access.AccessScope | entity | `access_scopes` | `(scope_uuidv4)` | `AccessScopeRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | row-input: `AccessScope` (packages/access/src/repo_catalog/domain/access_registry.py) |
| Access.ScopeLocatorRegistration | association | `scope_locators` | `(scope_uuidv4, registered_at_us, scope_locator_uri)` | `ScopeLocatorRegistrationRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | row-input: `ScopeLocatorRegistration` (packages/access/src/repo_catalog/domain/access_registry.py) |
| Access.ScopeLocatorControl | entity | `scope_locator_controls` | `(scope_uuidv4, registered_at_us, scope_locator_uri)` | `ScopeLocatorControlRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | no Python input/projection recorded |
| Access.ScopeExecutionContext | entity | `scope_execution_contexts` | `(scope_uuidv4)` | `ScopeExecutionContextRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | row-input: `ScopeExecutionContext` (packages/access/src/repo_catalog/domain/access_connections.py) |
| Access.ConnectionConfiguration | entity | `connection_configurations` | `(scope_uuidv4, configuration_name)` | `ConnectionConfigurationRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | row-input: `ConnectionConfiguration` (packages/access/src/repo_catalog/domain/access_connections.py) |
| Access.RepositoryBinding | association | `repository_locators` | `(scope_uuidv4, locator_text)` | `RepositoryBindingRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | row-input: `RepositoryBinding` (packages/access/src/repo_catalog/domain/access_connections.py) |
| Access.LocatorConnection | association | `locator_connections` | `(scope_uuidv4, locator_text, configuration_name, purpose)` | `LocatorConnectionRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | row-input: `LocatorConnection` (packages/access/src/repo_catalog/domain/access_connections.py) |
| Access.AccessPreference | association | `repository_access_preferences` | `(repository_uuidv4, scope_uuidv4, purpose)` | `AccessPreferenceRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | row-input: `AccessPreference` (packages/access/src/repo_catalog/domain/access_connections.py) |
| Access.LocalAccessGrant | association | `local_access_grants` | `(scope_uuidv4, locator_text, configuration_name, purpose)` | `LocalAccessGrantRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | row-input: `LocalAccessGrant` (packages/access/src/repo_catalog/domain/access_connections.py) |
| Access.StoreIdentity | infrastructure | `access_identity` | `(store_role)` | `StoreIdentityRow` (packages/access/src/repo_catalog/adapters/sqlite/access_rows.py) | no Python input/projection recorded |

### Row details and same-file physical FKs

- **Access.AccessScope**: Local execution/approval boundary identified by scope UUID. Fields: `scope_uuidv4 TEXT, display_name TEXT`.
- **Access.ScopeLocatorRegistration**: Append registration occurrence keyed by scope, registration time and raw locator URI. Fields: `scope_uuidv4 TEXT, registered_at_us INTEGER, scope_locator_uri TEXT`.
  - physical FK: `(scope_uuidv4)` → Access.AccessScope `(scope_uuidv4)`.
- **Access.ScopeLocatorControl**: Mutable enabled control for an exact registration occurrence; not part of the immutable registration payload. Fields: `scope_uuidv4 TEXT, registered_at_us INTEGER, scope_locator_uri TEXT, enabled INTEGER`.
  - physical FK: `(scope_uuidv4, registered_at_us, scope_locator_uri)` → Access.ScopeLocatorRegistration `(scope_uuidv4, registered_at_us, scope_locator_uri)`.
- **Access.ScopeExecutionContext**: Scope-specific execution configuration; adapter column names need not match Python attribute names. Fields: `scope_uuidv4 TEXT, execution_context_json TEXT, enabled INTEGER`.
  - physical FK: `(scope_uuidv4)` → Access.AccessScope `(scope_uuidv4)`.
- **Access.ConnectionConfiguration**: Named local connection configuration within an Access scope. Fields: `scope_uuidv4 TEXT, configuration_name TEXT, options_json TEXT, enabled INTEGER`.
  - physical FK: `(scope_uuidv4)` → Access.AccessScope `(scope_uuidv4)`.
- **Access.RepositoryBinding**: Local locator/repository binding, not Core repository identity. Fields: `scope_uuidv4 TEXT, locator_text TEXT, repository_uuidv4 TEXT, enabled INTEGER`.
  - physical FK: `(scope_uuidv4)` → Access.AccessScope `(scope_uuidv4)`.
- **Access.LocatorConnection**: Purpose-specific connection assignment to a local locator. Fields: `scope_uuidv4 TEXT, locator_text TEXT, configuration_name TEXT, purpose TEXT, enabled INTEGER`.
  - physical FK: `(scope_uuidv4, configuration_name)` → Access.ConnectionConfiguration `(scope_uuidv4, configuration_name)`.
  - physical FK: `(scope_uuidv4, locator_text)` → Access.RepositoryBinding `(scope_uuidv4, locator_text)`.
- **Access.AccessPreference**: Local preferred locator/connection for a repository, scope and purpose. Fields: `repository_uuidv4 TEXT, scope_uuidv4 TEXT, purpose TEXT, locator_text TEXT, configuration_name TEXT`.
  - physical FK: `(scope_uuidv4, locator_text, repository_uuidv4)` → Access.RepositoryBinding `(scope_uuidv4, locator_text, repository_uuidv4)`.
  - physical FK: `(scope_uuidv4, locator_text, configuration_name, purpose)` → Access.LocatorConnection `(scope_uuidv4, locator_text, configuration_name, purpose)`.
- **Access.LocalAccessGrant**: Local approval bound to a reviewed plan; existence does not grant perpetual approval after configuration changes. Fields: `scope_uuidv4 TEXT, locator_text TEXT, configuration_name TEXT, purpose TEXT, repository_uuidv4 TEXT, registered_at_us INTEGER, scope_locator_uri TEXT, reviewed_options_json TEXT, reviewed_context_json TEXT, approved_at_us INTEGER`.
  - physical FK: `(scope_uuidv4, registered_at_us, scope_locator_uri)` → Access.ScopeLocatorRegistration `(scope_uuidv4, registered_at_us, scope_locator_uri)`.
  - physical FK: `(scope_uuidv4, locator_text, repository_uuidv4)` → Access.RepositoryBinding `(scope_uuidv4, locator_text, repository_uuidv4)`.
  - physical FK: `(scope_uuidv4, locator_text, configuration_name, purpose)` → Access.LocatorConnection `(scope_uuidv4, locator_text, configuration_name, purpose)`.
- **Access.StoreIdentity**: Access instance metadata; not a seventh field on an AccessScope. Fields: `store_role TEXT, format_id TEXT, schema_version INTEGER, ddl_sha256 TEXT`.

## Operational — `p1.operational`

Request orchestration and required durable budgets/accounting/checkpoints; reconstructibility is scoped, not domain-wide.

Composition: `packages/runtime/src/repo_catalog/adapters/sqlite/p1_schema.py` (repo-catalog-runtime). This is not table-source ownership.

DDL SHA-256: `76598c5a630d4044c5a123587911a62411d55946072ba071109dd7db52f029a5`; format: `repo-catalog/p1-isolated-4`; schema version: `None`.

DDL contributions: `packages/runtime/src/repo_catalog/adapters/sqlite/p1_schema.py` (repo-catalog-runtime); `packages/operational/src/repo_catalog/adapters/sqlite/p1_ddl/operational.sql` (repo-catalog-operational)

| Persistent class | Kind | Table | Ordered primary key | Generated row type | Python input/projection |
| --- | --- | --- | --- | --- | --- |
| Operational.AcquisitionRequest | entity | `acquisition_requests` | `(request_origin_uuidv4, request_uuidv4)` | `AcquisitionRequestRow` (packages/operational/src/repo_catalog/adapters/sqlite/operational_rows.py) | no Python input/projection recorded |
| Operational.RequestBudget | entity | `request_budgets` | `(request_origin_uuidv4, request_uuidv4, work_kind)` | `RequestBudgetRow` (packages/operational/src/repo_catalog/adapters/sqlite/operational_rows.py) | no Python input/projection recorded |
| Operational.AcquisitionAttempt | entity | `acquisition_attempts` | `(request_origin_uuidv4, request_uuidv4, attempt_uuidv4)` | `AcquisitionAttemptRow` (packages/operational/src/repo_catalog/adapters/sqlite/operational_rows.py) | no Python input/projection recorded |
| Operational.WorkAccounting | association | `work_accounting` | `(request_origin_uuidv4, request_uuidv4, attempt_uuidv4, work_kind, work_coordinate)` | `WorkAccountingRow` (packages/operational/src/repo_catalog/adapters/sqlite/operational_rows.py) | no Python input/projection recorded |
| Operational.RequestContinuation | entity | `request_continuations` | `(request_origin_uuidv4, request_uuidv4, continuation_scope_json)` | `RequestContinuationRow` (packages/operational/src/repo_catalog/adapters/sqlite/operational_rows.py) | no Python input/projection recorded |
| Operational.RetryState | entity | `retry_state` | `(request_origin_uuidv4, request_uuidv4, retry_scope_json)` | `RetryStateRow` (packages/operational/src/repo_catalog/adapters/sqlite/operational_rows.py) | no Python input/projection recorded |
| Operational.CacheLocator | association | `cache_locators` | `(repository_uuidv4, cache_purpose, semantic_coordinate_json)` | `CacheLocatorRow` (packages/operational/src/repo_catalog/adapters/sqlite/operational_rows.py) | no Python input/projection recorded |
| Operational.StoreIdentity | infrastructure | `store_identity` | `(store_role)` | `StoreIdentityRow` (packages/operational/src/repo_catalog/adapters/sqlite/operational_rows.py) | no Python input/projection recorded |

### Row details and same-file physical FKs

- **Operational.AcquisitionRequest**: Explicit durable cumulative work request; retries and continuations do not reset request scope. Fields: `request_origin_uuidv4 TEXT, request_uuidv4 TEXT, request_scope_json TEXT, state TEXT`.
- **Operational.RequestBudget**: Finite request/work-kind budget and cached accounting; actual accounting remains independently checked. Fields: `request_origin_uuidv4 TEXT, request_uuidv4 TEXT, work_kind TEXT, finite_limit INTEGER, spent_or_reserved INTEGER`.
  - physical FK: `(request_origin_uuidv4, request_uuidv4)` → Operational.AcquisitionRequest `(request_origin_uuidv4, request_uuidv4)`.
- **Operational.AcquisitionAttempt**: One execution attempt under an explicit request. Fields: `request_origin_uuidv4 TEXT, request_uuidv4 TEXT, attempt_uuidv4 TEXT, continuation_json TEXT`.
  - physical FK: `(request_origin_uuidv4, request_uuidv4)` → Operational.AcquisitionRequest `(request_origin_uuidv4, request_uuidv4)`.
- **Operational.WorkAccounting**: Durable reservation/actual-work coordinates; failed or replayed work is not free. Fields: `request_origin_uuidv4 TEXT, request_uuidv4 TEXT, attempt_uuidv4 TEXT, work_kind TEXT, work_coordinate TEXT, reserved INTEGER, actual INTEGER`.
  - physical FK: `(request_origin_uuidv4, request_uuidv4, work_kind)` → Operational.RequestBudget `(request_origin_uuidv4, request_uuidv4, work_kind)`.
  - physical FK: `(request_origin_uuidv4, request_uuidv4, attempt_uuidv4)` → Operational.AcquisitionAttempt `(request_origin_uuidv4, request_uuidv4, attempt_uuidv4)`.
- **Operational.RequestContinuation**: Scoped durable cursor/checkpoint, including canonical Exchange package bindings where used. Fields: `request_origin_uuidv4 TEXT, request_uuidv4 TEXT, continuation_scope_json TEXT, cursor_json TEXT`.
  - physical FK: `(request_origin_uuidv4, request_uuidv4)` → Operational.AcquisitionRequest `(request_origin_uuidv4, request_uuidv4)`.
- **Operational.RetryState**: Request-scoped retry schedule/reason; no automatic resume after loss of required Operational state. Fields: `request_origin_uuidv4 TEXT, request_uuidv4 TEXT, retry_scope_json TEXT, not_before_us INTEGER, reason TEXT`.
  - physical FK: `(request_origin_uuidv4, request_uuidv4)` → Operational.AcquisitionRequest `(request_origin_uuidv4, request_uuidv4)`.
- **Operational.CacheLocator**: Locator for reusable metadata/verified-notes cache; reuse never substitutes for required authoritative evidence. Fields: `repository_uuidv4 TEXT, cache_purpose TEXT, semantic_coordinate_json TEXT, locator TEXT`.
- **Operational.StoreIdentity**: Operational instance identity; required request/recovery state is not classified wholesale as disposable. Fields: `store_role TEXT, repository_uuidv4 TEXT, catalog_instance_uuidv4 TEXT`.

## Search — `p1.search`

Rebuildable search projections, separate from authoritative Core/Context facts.

Composition: `packages/runtime/src/repo_catalog/adapters/sqlite/p1_schema.py` (repo-catalog-runtime). This is not table-source ownership.

DDL SHA-256: `a1bce192ebf67bc3846f47a5bc63ba2927a97bddf65eb62706ec2e9f9fc5d303`; format: `repo-catalog/p1-isolated-4`; schema version: `None`.

DDL contributions: `packages/runtime/src/repo_catalog/adapters/sqlite/p1_schema.py` (repo-catalog-runtime); `packages/search/src/repo_catalog/adapters/sqlite/p1_ddl/search.sql` (repo-catalog-search)

| Persistent class | Kind | Table | Ordered primary key | Generated row type | Python input/projection |
| --- | --- | --- | --- | --- | --- |
| Search.SearchProjection | projection | `search_projections` | `(projection_kind, snapshot_token_json)` | `SearchProjectionRow` (packages/search/src/repo_catalog/adapters/sqlite/search_rows.py) | no Python input/projection recorded |
| Search.SearchDocument | projection | `search_documents` | `(projection_kind, snapshot_token_json, document_key_json)` | `SearchDocumentRow` (packages/search/src/repo_catalog/adapters/sqlite/search_rows.py) | no Python input/projection recorded |
| Search.StoreIdentity | infrastructure | `store_identity` | `(store_role)` | `StoreIdentityRow` (packages/search/src/repo_catalog/adapters/sqlite/search_rows.py) | no Python input/projection recorded |

### Row details and same-file physical FKs

- **Search.SearchProjection**: Derivative projection generation tied to its exact authority snapshot, not canonical product data. Fields: `projection_kind TEXT, snapshot_token_json TEXT`.
- **Search.SearchDocument**: Searchable derivative document for a qualified projection generation. Fields: `projection_kind TEXT, snapshot_token_json TEXT, document_key_json TEXT, searchable_text TEXT`.
  - physical FK: `(projection_kind, snapshot_token_json)` → Search.SearchProjection `(projection_kind, snapshot_token_json)`.
- **Search.StoreIdentity**: Search store metadata; ordinary authoritative reads need not create a Search DB. Fields: `store_role TEXT, repository_uuidv4 TEXT, catalog_instance_uuidv4 TEXT`.

## Filesystem — `filesystem`

Independent historical filesystem metadata/digests and honest scan outcomes, with raw path identity.

Composition: `packages/filesystem/src/repo_catalog/filesystem/store.py` (repo-catalog-filesystem). This is not table-source ownership.

DDL SHA-256: `6152cccc85d8c5a615abf77a4b69558861446312b4d80699b12f66449bba6332`; format: `None`; schema version: `1`.

DDL contributions: `packages/filesystem/src/repo_catalog/filesystem/store.py` (repo-catalog-filesystem)

| Persistent class | Kind | Table | Ordered primary key | Generated row type | Python input/projection |
| --- | --- | --- | --- | --- | --- |
| Filesystem.CatalogMetadata | infrastructure | `catalog_metadata` | `(key)` | `CatalogMetadataRow` (packages/filesystem/src/repo_catalog/filesystem/rows.py) | no Python input/projection recorded |
| Filesystem.Scan | entity | `scans` | `(namespace_uuid, scan_uuid)` | `ScanRow` (packages/filesystem/src/repo_catalog/filesystem/rows.py) | no Python input/projection recorded |
| Filesystem.Entry | entity | `entries` | `(namespace_uuid, scan_uuid, relative_path)` | `EntryRow` (packages/filesystem/src/repo_catalog/filesystem/rows.py) | no Python input/projection recorded |
| Filesystem.ScanOutcome | entity | `scan_outcomes` | `(namespace_uuid, scan_uuid)` | `ScanOutcomeRow` (packages/filesystem/src/repo_catalog/filesystem/rows.py) | no Python input/projection recorded |

### Row details and same-file physical FKs

- **Filesystem.CatalogMetadata**: Filesystem catalogue namespace/configuration metadata; not a scanned-file entity. Fields: `key TEXT, value TEXT`.
- **Filesystem.Scan**: Namespace-qualified scan occurrence with a root_path value; no separate roots table is implied. Fields: `namespace_uuid TEXT, scan_uuid TEXT, root_path BLOB, started_us INTEGER, exclusions_json TEXT`.
- **Filesystem.Entry**: Raw-path entry within one namespace and scan; all three key components are required. Fields: `namespace_uuid TEXT, scan_uuid TEXT, relative_path BLOB, kind TEXT, size INTEGER, mtime_ns TEXT, birthtime_ns TEXT, ctime_ns TEXT, attributes INTEGER, mode INTEGER, sha256 TEXT, hash_status TEXT, error TEXT, link_target BLOB, observed_us INTEGER`.
  - physical FK: `(namespace_uuid, scan_uuid)` → Filesystem.Scan `(namespace_uuid, scan_uuid)`.
- **Filesystem.ScanOutcome**: Observed termination/partial-result facts for an exact scan; no synthetic completeness. Fields: `namespace_uuid TEXT, scan_uuid TEXT, finished_us INTEGER, status TEXT, entry_count INTEGER, error_count INTEGER`.
  - physical FK: `(namespace_uuid, scan_uuid)` → Filesystem.Scan `(namespace_uuid, scan_uuid)`.

## Worktrees — `worktrees`

Independent Git topology/worktree observations and explicitly optional qualified links.

Composition: `packages/worktrees/src/repo_catalog/worktrees/catalog.py` (repo-catalog-worktrees). This is not table-source ownership.

DDL SHA-256: `095ca80249d0ac885e713e7c01bc015357d21674517ea43984c6a86848359a4e`; format: `repo-catalog/worktrees-1`; schema version: `None`.

DDL contributions: `packages/worktrees/src/repo_catalog/worktrees/catalog.py` (repo-catalog-worktrees)

| Persistent class | Kind | Table | Ordered primary key | Generated row type | Python input/projection |
| --- | --- | --- | --- | --- | --- |
| Worktrees.CatalogIdentity | infrastructure | `catalog_identity` | `(singleton)` | `CatalogIdentityRow` (packages/worktrees/src/repo_catalog/worktrees/rows.py) | no Python input/projection recorded |
| Worktrees.Observation | entity | `observations` | `(observation_uuid)` | `ObservationRow` (packages/worktrees/src/repo_catalog/worktrees/rows.py) | no Python input/projection recorded |
| Worktrees.Worktree | entity | `worktrees` | `(observation_uuid, root_path)` | `WorktreeRow` (packages/worktrees/src/repo_catalog/worktrees/rows.py) | no Python input/projection recorded |
| Worktrees.ScanReference | association | `scan_references` | `(observation_uuid, root_path, filesystem_namespace_uuid, filesystem_scan_uuid)` | `ScanReferenceRow` (packages/worktrees/src/repo_catalog/worktrees/rows.py) | no Python input/projection recorded |
| Worktrees.RepositoryLink | association | `repository_links` | `(common_dir, repository_uuid)` | `RepositoryLinkRow` (packages/worktrees/src/repo_catalog/worktrees/rows.py) | no Python input/projection recorded |

### Row details and same-file physical FKs

- **Worktrees.CatalogIdentity**: Independent worktree catalogue identity; does not turn Local composition into a store. Fields: `singleton INTEGER, format TEXT, namespace_uuid TEXT, path_dialect TEXT, path_encoding TEXT, path_errors TEXT, schema_sha256 TEXT`.
- **Worktrees.Observation**: One worktree/topology observation with its own execution scope. Fields: `observation_uuid TEXT, requested_path BLOB, common_dir BLOB, status TEXT, errors_json TEXT, observed_at_us INTEGER`.
- **Worktrees.Worktree**: Root-path worktree observation keyed with its enclosing observation UUID. Fields: `observation_uuid TEXT, root_path BLOB, git_dir BLOB, common_dir BLOB, head_oid TEXT, branch BLOB, bare INTEGER, locked BLOB, prunable BLOB, error TEXT, object_format TEXT`.
  - physical FK: `(observation_uuid)` → Worktrees.Observation `(observation_uuid)`.
- **Worktrees.ScanReference**: Qualified optional link from a worktree observation to a Filesystem scan; no cross-DB transaction. Fields: `observation_uuid TEXT, root_path BLOB, filesystem_namespace_uuid TEXT, filesystem_scan_uuid TEXT`.
  - physical FK: `(observation_uuid, root_path)` → Worktrees.Worktree `(observation_uuid, root_path)`.
- **Worktrees.RepositoryLink**: Attributed common-dir/Repository association; absence of optional Core data stays unresolved. Fields: `common_dir BLOB, repository_uuid TEXT, linked_at_us INTEGER`.

## Registered optional external references

This section covers the schema catalogue's explicit optional-reference registry, not all domain associations or operation preconditions. Missing optional instance targets remain unresolved. These are not cross-DB physical FKs.

- qualified-external-reference: Worktrees.ScanReference `(filesystem_namespace_uuid, filesystem_scan_uuid)` → Filesystem.Scan (namespace_uuid, scan_uuid); missing target: unresolved.
- external-domain-claim: Worktrees.RepositoryLink `(repository_uuid)` → Core.Repository (domain claim; no target-row verification); missing target: unresolved.

## Nonpersistent types and query derivations

An empty source list denotes a value/abstraction, not a missing table. Source lists describe derivation/use, not FKs or one-to-one row encodings.

- **Core.GitClaim** (abstract): Conceptual shared claim/evidence vocabulary; concrete rows remain separately mapped. Sources/use: Core.ScalarClaim, Core.RelationGroup, Core.IntrinsicClaim, Core.IntrinsicGroup. no Python class claimed.
- **Core.OID** (value): Nominal algorithm/OID value used in many keys; no standalone OID table is required. Sources/use: value/abstraction. value: `OID` (packages/contracts/src/repo_catalog/domain/shared_values.py).
- **Core.Provenance** (value): Shared attributed-source value; its definition is Contracts-owned, not a claim that Core owns the source module. Sources/use: value/abstraction. value: `Provenance` (packages/contracts/src/repo_catalog/domain/shared_values.py).
- **Core.RelationMember** (value): Member value embedded in atomic group membership, not one persistent row per Python object. Sources/use: value/abstraction. value: `RelationMember` (packages/core/src/repo_catalog/domain/p1_core.py).
- **Core.NativeObject** (dto): Validated native object/body input; permitted retention and nominal identity are different row responsibilities. Sources/use: Core.GitObject, Core.RetainedMetadata, Core.RetainedNote. dto: `NativeObject` (packages/core/src/repo_catalog/domain/p1_core.py).
- **Core.GitObjectView** (query): Read projection over claims/evidence; not a class requiring its own table. Sources/use: Core.GitObject, Core.ScalarClaim, Core.RelationGroup, Core.IntrinsicClaim, Core.IntrinsicGroup. query: `GitObjectView` (packages/core/src/repo_catalog/domain/core_query.py).
- **Core.CoverageClaimValue** (value): Shared Contracts claim value is reused across Core and Context; distinct qualified persistent classes own their rows. Sources/use: value/abstraction. value: `CoverageClaim` (packages/contracts/src/repo_catalog/domain/p1_coverage.py).
- **Context.ResourceKey** (value): Composite resource coordinate reused by Context inputs and rows. Sources/use: value/abstraction. value: `ResourceKey` (packages/context/src/repo_catalog/domain/p1_context.py).
- **Context.FieldClock** (value): Clock value embedded in attributed field/relation coordinates. Sources/use: value/abstraction. value: `FieldClock` (packages/context/src/repo_catalog/domain/p1_context.py).
- **Context.ResourceObservation** (dto): Admission aggregate spanning identity and field candidates, not a dedicated resources row mirror. Sources/use: Context.Resource, Context.FieldCandidate. dto: `ResourceObservation` (packages/context/src/repo_catalog/domain/production_context.py).
- **Context.CollectionObservation** (dto): Input spanning collection scope and terminal evidence; adapters must preserve both responsibilities. Sources/use: Context.Collection, Context.CollectionTerminal. dto: `CollectionObservation` (packages/context/src/repo_catalog/domain/production_context.py).
- **Context.SourceInventory** (dto): Scoped evidence and positive repository associations can be produced from this aggregate. Sources/use: Context.SourceInventoryEvidence, Context.SourceRepository. dto: `SourceInventory` (packages/context/src/repo_catalog/domain/production_context.py).
- **Access.AssignmentKey** (value): Nested scope/locator/configuration/purpose coordinate; not another assignment table. Sources/use: value/abstraction. value: `AssignmentKey` (packages/access/src/repo_catalog/domain/access_connections.py).
- **Filesystem.RootPath** (value): Root is currently a raw path value in a scan, with no independent persistent Root class or Python Root class claimed. Sources/use: Filesystem.Scan. no Python class claimed.
- **Filesystem.ScanResult** (dto): API result combines scan identity, counts and outcome; it is not the scans table row type. Sources/use: Filesystem.Scan, Filesystem.ScanOutcome, Filesystem.Entry. dto: `ScanResult` (packages/filesystem/src/repo_catalog/filesystem/models.py).
- **Filesystem.FileEntry** (query): Read payload includes a computed absolute path using scan context; it is not a raw entries row mirror. Sources/use: Filesystem.Entry, Filesystem.Scan. query: `FileEntry` (packages/filesystem/src/repo_catalog/filesystem/models.py).
- **Worktrees.DiscoveryResult** (dto): Discovery result supplies enclosing observation context to its worktree payloads. Sources/use: Worktrees.Observation, Worktrees.Worktree. dto: `DiscoveryResult` (packages/worktrees/src/repo_catalog/worktrees/models.py).
- **Worktrees.WorktreeEntry** (dto): Scoped payload omits observation_uuid, supplied by its DiscoveryResult/adapter context; cannot stand alone as the complete persistent key. Sources/use: Worktrees.Worktree, Worktrees.Observation. dto: `WorktreeEntry` (packages/worktrees/src/repo_catalog/worktrees/models.py).
- **Search.SearchResponse** (query): Query response, including authority fallback, is not the derivative document row class. Sources/use: Search.SearchProjection, Search.SearchDocument. query: `SearchResponse` (packages/search/src/repo_catalog/domain/search_query.py).

## Gaps and redesign candidates

- **normal-versus-separated**: The retired normal Catalog3 format mixes Core/Context/Access and uses different Git object/ref keys. The ordinary CLI now composes separated stores; remaining legacy code/test retirement is explicitly tracked. Repository UUID identity already existed in both. Existing DBs are never converted or overwritten.
- **python-row-bindings**: Every selected persistent class has a dedicated generated row_type. The separate python binding describes observed input/projection classes; null there means no such dedicated input class recorded, not missing SQL functionality or missing generated row type. Domain admission, serialization behavior and capability checks require their own regressions.
- **root-and-scan-aggregate**: Filesystem Root is currently root_path within Scan; ScanResult and FileEntry are result/projection types. Do not invent a roots table to match an aggregate or value type. Decide whether independent Root identity is necessary only with its domain semantics.
- **worktree-context-key**: WorktreeEntry remains a scoped DTO whose enclosing DiscoveryResult supplies observation identity. The dedicated WorktreeRow now explicitly carries observation_uuid plus root_path; adapters preserve the full key without rewriting the DTO into a raw row.
- **coverage-and-website**: Context coverage scopes/claims/proofs are real selected tables even if absent from a website concept group. The web branch semantic-model (seven groups of responsibility domains) and older five-store model are derived explanations with different granularities, not canonical table/class maps; their update is independent and deferred.
- **reference-and-behavior-scope**: Only existing catalogue-registered optional external references and DDL physical FKs are checked/rendered. Context/Core references, paired identity rules, operation preconditions, CHECK/trigger semantics, dynamic virtual tables and retained-instance validity are not fully formalized. Coverage success is not complete operation or semantic conformance.

## Future implementation and retirement sequence

- **1-foundations**: Build on existing independent implementations for Core lifecycle including required recovery, Context reads, paired reads/recovery and Access. Assess remaining separated-format adapter/admission/backup/activation gaps against the module operation contract; do not claim these existing capabilities absent. Preserve Core INSERT-only/typed keys, ADR 0038 stop/preserve/typed salvage/fresh verified restore and paired validation. Carry ADR 0039 independent Filesystem/Worktrees raw paths, partial scans, optional qualified references, EFU and DB-free Local composition; those are outside OP-01..12. Fresh DB start needs no legacy conversion; never mutate/delete retained source DBs.
- **2-orchestration-and-projections**: Assess and complete separated-format Operational request orchestration, Git acquisition with optional Access, Exchange and Search integration using existing APIs. Preserve actual cumulative work, durable reservations/checkpoints, package binding and honest loss behavior. Rebuild derivative Search without enlarging authority. Required recovery correctness remains part of foundations, not an optional late add-on.
- **3-ordinary-cli-cutover**: Only after behavior/adapter tests and recovery prerequisites pass, switch ordinary initialization/CLI composition to fresh separated catalogs. Keep operation-scoped optional initialization: no command must initialize or open all seven DBs simply because the design has seven responsibility roles. This phase is not implemented here.
- **4-legacy-code-retirement**: Remove normal-format factories/adapters and obsolete normal-only tests only after recording each affected test node and its concrete separated-format replacement for the same behavior, including corrupt-source stop, backup/restore, Exchange and accounting failures. Retire tests by obligation, not by coverage counts. No backward-compatibility adapter or old-data migration is required; no authorization to delete user DBs or historical evidence is created.

Structural coverage and symbol checks do not prove SQL CHECK/trigger semantics, admission/recovery correctness, input/projection serialization, instance validity or formal semantic consistency.
