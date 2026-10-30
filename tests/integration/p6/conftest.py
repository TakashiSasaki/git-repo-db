"""Shared test fixtures and builders for P6 production query and Search tests."""

from __future__ import annotations

import hashlib
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import (
    CoverageScope,
    FieldCandidate,
    FieldClock,
    MappingClaimKey,
    ProviderRepositoryRoleScope,
    ProviderRepositoryScope,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_core import (
    OID,
    CoreCoverageScope,
    GitObservation,
    NativeObject,
    Provenance,
    RelationGroup,
    RelationMember,
    RepositoryClaim,
    ScalarClaim,
    native_oid,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.production_context import (
    CollectionObservation,
    CoreReference,
    ResourceObservation,
    ResourceRelation,
    SourceInventory,
)
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from tests.support.context_admission import fixture_context, fixture_service

REPOSITORY = "e82dde21-3201-49db-9273-2e58c9c9beaf"
INSTANCE = "f9976943-6d0c-4b14-879e-30b23591fb53"
SERVICE = "73b05ca2-eceb-460f-8909-84d015e81fc3"
SOURCE = "25695d63-2e0c-4a53-b2fd-0faf166fe2d5"
ORIGIN = "1c02424b-aa1d-4440-aea1-3fdcd37a0810"
CAPTURE_ID = "3f51c7c0-ff7e-4612-9fd8-f70c1242e151"


class UnlimitedTestBudget:
    class Limits:
        note_bytes = 16 * 1024 * 1024

    limits = Limits()

    def require(self, unit: str, amount: int = 1) -> None:
        assert type(amount) is int and amount >= 0

    def charge(self, unit: str, amount: int) -> None:
        assert type(amount) is int and amount >= 0


def admit_provider_role(context, resource, role, clock, provenance, observed):
    provider = ResourceKey.from_native(SERVICE, "repository", "1001")
    context.resource(provider)
    context.admit_repository_relation(
        ResourceRepositoryRelation(
            provider,
            "represents_repository",
            clock,
            canonical(REPOSITORY),
            provenance,
            observed,
        )
    )
    scope = ProviderRepositoryScope(
        {
            role: ProviderRepositoryRoleScope(
                role,
                clock,
                "unresolved_provider_only",
                provider.provider_resource_id,
                observed_at_us=observed,
            )
        }
    )
    context.relation(
        ResourceRelation(
            resource,
            "provider_repository_roles",
            (provider,),
            provenance,
            scope.encoded,
            observed,
        )
    )


def init_catalog(
    directory: Path,
    roles: tuple[str, ...] = ("core", "context", "operational", "search"),
    *,
    repository_uuidv4: str = REPOSITORY,
    catalog_instance_uuidv4: str = INSTANCE,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for role in roles:
        initialize(
            directory / f"{role}.sqlite3",
            role,
            repository_uuidv4,
            catalog_instance_uuidv4,
        )
    return directory


def make_native(fmt: str, kind: str, body: bytes) -> NativeObject:
    oid_hex = native_oid(fmt, kind, body)
    return NativeObject(
        oid=OID(fmt, oid_hex),
        native_type=kind,
        body=body,
        declared_size=len(body),
        digest_sha256=hashlib.sha256(body).hexdigest(),
    )


def make_tree(fmt: str, entries: list[tuple[bytes, bytes, str]]) -> NativeObject:
    """Build a canonical Git tree object from `(mode_bytes, name_bytes, target_hex)`."""
    sorted_entries = sorted(
        entries,
        key=lambda item: item[1] + (b"/" if item[0] == b"40000" else b"\0"),
    )
    chunks = []
    for mode, name, target_hex in sorted_entries:
        chunks.append(mode + b" " + name + b"\0" + bytes.fromhex(target_hex))
    return make_native(fmt, "tree", b"".join(chunks))


def make_commit(
    fmt: str,
    tree_oid: str,
    parents: list[str],
    *,
    author: str = "Alice <alice@example.com> 1700000000 +0000",
    committer: str = "Alice <alice@example.com> 1700000000 +0000",
    message: str = "Initial commit message\n",
) -> NativeObject:
    lines = [f"tree {tree_oid}"]
    for parent in parents:
        lines.append(f"parent {parent}")
    lines.append(f"author {author}")
    lines.append(f"committer {committer}")
    raw = ("\n".join(lines) + "\n\n" + message).encode("utf-8")
    return make_native(fmt, "commit", raw)


def make_tag(
    fmt: str,
    target_oid: str,
    target_type: str = "commit",
    tag_name: str = "v1.0.0",
    *,
    tagger: str = "Bob <bob@example.com> 1700000100 +0000",
    message: str = "Release v1.0.0 tag annotation\n",
) -> NativeObject:
    lines = [
        f"object {target_oid}",
        f"type {target_type}",
        f"tag {tag_name}",
        f"tagger {tagger}",
    ]
    raw = ("\n".join(lines) + "\n\n" + message).encode("utf-8")
    return make_native(fmt, "tag", raw)


def populate_rich_catalog(
    directory: Path,
    fmt: str = "sha1",
    *,
    include_core: bool = True,
    include_context: bool = True,
) -> dict[str, object]:
    """Populate a catalog with rich Core, Notes, and Context fixtures for testing."""
    roles = []
    if include_core:
        roles.append("core")
    if include_context:
        roles.append("context")
    roles.extend(["operational", "search"])
    init_catalog(directory, tuple(roles))

    budget = UnlimitedTestBudget()
    prov_reported = Provenance(
        "remote-git",
        "obs-1",
        "coord-1",
        "git-cli",
        "1",
        "reported",
    )
    prov_alt = Provenance(
        "secondary-mirror",
        "obs-2",
        "coord-2",
        "git-cli",
        "1",
        "reported",
    )

    width = 40 if fmt == "sha1" else 64
    missing_blob_oid = OID(fmt, "1" * width)
    missing_parent_oid = OID(fmt, "2" * width)
    unretained_commit_oid = OID(fmt, "3" * width)

    tree_obj = make_tree(
        fmt,
        [(b"100644", b"README.md", missing_blob_oid.full_oid)],
    )
    commit_obj = make_commit(
        fmt,
        tree_obj.oid.full_oid,
        [missing_parent_oid.full_oid],
        author="Alice Author <alice@example.com> 1700000000 +0000",
        committer="Bob Committer <bob@example.com> 1700000005 +0000",
        message="feat: add p6 production query support\n",
    )
    tag_obj = make_tag(
        fmt,
        commit_obj.oid.full_oid,
        "commit",
        "v1.0.0-p6",
        tagger="Carol Tagger <carol@example.com> 1700000100 +0000",
        message="Signed release tag for p6\n",
    )

    note_body_bytes = b"Reviewed-by: Carol <carol@example.com>\nApproved for P6!\n"
    note_blob = make_native(fmt, "blob", note_body_bytes)
    notes_tree = make_tree(
        fmt,
        [
            (
                b"100644",
                commit_obj.oid.full_oid.encode("ascii"),
                note_blob.oid.full_oid,
            )
        ],
    )
    ref_fixture = {}

    def admit_core(core: GitCore) -> None:
        core.admit_repository(REPOSITORY)
        core.admit_repository_claim(
            RepositoryClaim(REPOSITORY, "name", "git-repo-db", prov_reported)
        )
        core.admit_repository_claim(
            RepositoryClaim(REPOSITORY, "object_format", fmt, prov_reported)
        )
        core.admit_metadata(tree_obj, str(uuid4()), budget)
        core.admit_metadata(commit_obj, str(uuid4()), budget)
        core.admit_metadata(tag_obj, str(uuid4()), budget)

        # Competing reported scalar claim on commit_obj ("message")
        core.admit_claim(
            ScalarClaim(
                commit_obj.oid,
                "message",
                "conflicting reported commit message\n",
                prov_alt,
            )
        )
        # Nominal commit with reported claims only (no retained bytes)
        core.admit_object(unretained_commit_oid)
        core.admit_claim(
            ScalarClaim(unretained_commit_oid, "type", "commit", prov_reported)
        )
        core.admit_claim(
            ScalarClaim(
                unretained_commit_oid,
                "message",
                "metadata-only commit without retained bytes",
                prov_reported,
            )
        )
        core.admit_group(
            RelationGroup(
                unretained_commit_oid,
                "commit_parents",
                "reported-parents",
                "partial",
                (RelationMember(0, commit_obj.oid),),
                prov_reported,
            )
        )

        # Ref observations
        core.admit_observation(
            GitObservation(
                ORIGIN,
                str(uuid4()),
                REPOSITORY,
                "ref",
                ("refs/heads/main",),
                {
                    "ref": "refs/heads/main",
                    "observed_at_us": 1700000200000000,
                    "target": list(commit_obj.oid.key),
                    "target_type": "commit",
                    "ref_kind": "head",
                },
                prov_reported,
            )
        )
        core.admit_observation(
            GitObservation(
                ORIGIN,
                str(uuid4()),
                REPOSITORY,
                "ref",
                ("refs/tags/v1.0.0-p6",),
                {
                    "ref": "refs/tags/v1.0.0-p6",
                    "observed_at_us": 1700000200000000,
                    "target": list(tag_obj.oid.key),
                    "peeled": list(commit_obj.oid.key),
                    "target_type": "tag",
                    "ref_kind": "tag",
                },
                prov_reported,
            )
        )

        alt_note_oid = OID(fmt, "9" * width)
        # Independent modern fixture facts: public Query/Search never infer a
        # RefObservation or receiver proof from the legacy rows above.
        from repo_catalog.domain.ref_observation import (
            NotesMapping,
            NotesMappingClaim,
            NotesMappingEvidence,
            NotesMappingGroup,
            RefObservation,
            RefObservationClaim,
            RefObservationKey,
            new_uuid7,
        )

        key = RefObservationKey(ORIGIN, new_uuid7())
        core.admit_ref_observation(
            RefObservation(
                key, REPOSITORY, b"refs/notes/commits", "local-notes", "visible"
            )
        )
        claim = RefObservationClaim(
            key, prov_reported, "present", root_oid=notes_tree.oid
        )
        core.admit_ref_observation_claim(claim)
        mapping = NotesMapping(
            notes_tree.oid,
            "git-notes",
            "1",
            "native-notes-tree",
            commit_obj.oid,
            note_blob.oid,
            commit_obj.oid.full_oid,
        )
        evidence = NotesMappingEvidence(
            claim,
            mapping,
            "single-path",
            Provenance(
                "local-notes",
                "receiver",
                "checked",
                "native-notes",
                "1",
                "receiver_intrinsic",
            ),
            (notes_tree,),
        )
        core.admit_ref_note(evidence, note_blob, str(uuid4()), budget)
        ref_fixture.update(claim=claim, mapping=mapping)
        core.admit_notes_mapping_claim(
            NotesMappingClaim(
                claim,
                NotesMapping(
                    notes_tree.oid,
                    "git-notes",
                    "1",
                    "native-notes-tree",
                    commit_obj.oid,
                    alt_note_oid,
                    commit_obj.oid.full_oid,
                ),
                prov_alt,
            )
        )
        core.admit_notes_mapping_group(
            NotesMappingGroup(
                claim,
                "git-notes",
                "1",
                "native-notes-tree",
                "reported-subset",
                "partial",
                (
                    (
                        commit_obj.oid.full_oid,
                        note_blob.oid.full_oid,
                        commit_obj.oid.full_oid,
                    ),
                ),
                prov_reported,
            ),
            budget,
        )

        # Core Coverage
        cov_scope = CoreCoverageScope("repository", (REPOSITORY, "refs"))
        core.admit_coverage_scope(cov_scope)
        cov_claim = CoverageClaim(
            cov_scope, 1700000300000000, "complete", '{"refs_checked":2}'
        )
        core.admit_coverage(cov_claim)
        core.admit_coverage_proof(
            cov_claim, (commit_obj.oid, tag_obj.oid), prov_reported
        )

    pr_key = ResourceKey.from_native(SERVICE, "pull_request", "42")
    issue_key = ResourceKey.from_native(SERVICE, "issue", "7")
    review_key = ResourceKey.document(pr_key, "review", "pr_review", "rev-1")
    thread_key = ResourceKey.document(pr_key, "thread", "review_thread", "thr-1")
    comment_key = ResourceKey.document(pr_key, "comment", "review_comment", "rc-1")
    issue_comment_key = ResourceKey.document(
        issue_key, "comment", "issue_comment", "ic-1"
    )

    ctx_prov_1 = canonical({"source": "github.rest", "evidence": "event-101"})
    ctx_prov_2 = canonical({"source": "github.graphql", "evidence": "event-102"})

    def admit_context(context: Context, core_present: bool) -> None:
        context.provider(SERVICE, "github", '{"name":"GitHub"}')
        context.repository(REPOSITORY, '{"default_branch":"main"}')
        context.source(SOURCE, SERVICE, '{"org":"example"}')
        context.associate_source(SOURCE, REPOSITORY, ctx_prov_1)

        inv_obs = SourceInventory(
            SOURCE,
            canonical(
                {
                    "coverage_kind": "repositories",
                    "service_instance_uuidv4": SERVICE,
                }
            ),
            1700000100000000,
            "complete",
            True,
            (REPOSITORY,),
            ctx_prov_1,
        )
        context.inventory(inv_obs)
        inv_cov_scope = CoverageScope.source_inventory(
            SOURCE, inv_obs.scope_json, "repositories"
        )
        context.prove_inventory(
            CoverageClaim(inv_cov_scope, 1700000100000000, "complete"),
            inv_obs,
        )

        # Pull Request 42
        context.resource(pr_key, REPOSITORY)
        admit_provider_role(
            context,
            pr_key,
            "base_repository",
            FieldClock("github:pr:updated_at", 100),
            ctx_prov_1,
            100,
        )
        context.admit_field(
            FieldCandidate(
                pr_key,
                "title",
                canonical("Implement P6 query and search"),
                FieldClock("github:pr:updated_at", 100),
                ctx_prov_1,
                100,
            )
        )
        # Competing incomparable field candidate on PR state
        context.admit_field(
            FieldCandidate(
                pr_key,
                "state",
                canonical("open"),
                FieldClock("github:pr:updated_at", 100),
                ctx_prov_1,
                100,
            )
        )
        context.admit_field(
            FieldCandidate(
                pr_key,
                "state",
                canonical("merged"),
                FieldClock("github:graphql:snapshot", 100),
                ctx_prov_2,
                105,
            )
        )
        # Explicit null field candidate ("closed_at" is null, whereas "milestone" is unobserved)
        context.admit_field(
            FieldCandidate(
                pr_key,
                "closed_at",
                "null",
                FieldClock("github:pr:updated_at", 100),
                ctx_prov_1,
                100,
            )
        )
        context.admit_text(
            pr_key,
            "PR 42 body text explaining P6 snapshot consistency and search fallback.",
            FieldClock("github:pr:updated_at", 100),
            ctx_prov_1,
            100,
        )

        # Core references on PR 42:
        # 1) "head" -> commit_obj.oid (present in Core when core_present=True)
        head_ref = CoreReference(pr_key, "head", commit_obj.oid, ctx_prov_1)
        if core_present:
            context.link_core(
                pr_key,
                "head",
                *commit_obj.oid.key,
                ctx_prov_1,
                lambda f, o: (f, o) == commit_obj.oid.key,
            )
        else:
            context.report_core_reference(
                head_ref,
                clock=FieldClock("github:pr:updated_at", 100),
                observed_at_us=100,
            )

        # 2) "base" -> absent OID (never in Core, reported only)
        absent_oid = OID(fmt, "f" * width)
        base_ref = CoreReference(pr_key, "base", absent_oid, ctx_prov_1)
        context.report_core_reference(
            base_ref,
            clock=FieldClock("github:pr:updated_at", 100),
            observed_at_us=100,
        )

        # Child resources of PR 42: review, thread, review_comment
        context.observe(
            ResourceObservation(
                review_key,
                (
                    FieldCandidate(
                        review_key,
                        "state",
                        canonical("APPROVED"),
                        FieldClock("github:review:submitted_at", 110),
                        ctx_prov_1,
                        110,
                    ),
                ),
                identification=RI.scoped(review_key, pr_key, "pr_review", "rev-1"),
            )
        )
        context.observe(
            ResourceObservation(
                thread_key,
                (
                    FieldCandidate(
                        thread_key,
                        "is_resolved",
                        canonical(True),
                        FieldClock("github:thread", None),
                        ctx_prov_1,
                        115,
                    ),
                ),
                identification=RI.scoped(thread_key, pr_key, "review_thread", "thr-1"),
            )
        )
        context.observe(
            ResourceObservation(
                comment_key,
                (
                    FieldCandidate(
                        comment_key,
                        "diff_hunk",
                        canonical("@@ -1,3 +1,5 @@"),
                        FieldClock("github:comment:updated_at", 120),
                        ctx_prov_1,
                        120,
                    ),
                ),
                identification=RI.scoped(comment_key, pr_key, "review_comment", "rc-1"),
            )
        )
        context.admit_text(
            comment_key,
            "Nitpick on pagination cursor validation.",
            FieldClock("github:comment:updated_at", 120),
            ctx_prov_1,
            120,
        )

        # Relations and Collections on PR 42
        context.relation(
            ResourceRelation(
                pr_key,
                "reviews",
                (review_key,),
                ctx_prov_1,
                canonical({"page": 1}),
                120,
            )
        )
        context.relation(
            ResourceRelation(
                comment_key,
                "in_review_thread",
                (thread_key,),
                ctx_prov_1,
                canonical({"direct": True}),
                120,
            )
        )

        col_scope_json = canonical(
            {
                "coverage_kind": "reviews",
                "service_instance_uuidv4": SERVICE,
            }
        )
        col_obs = CollectionObservation(
            pr_key,
            "reviews",
            ctx_prov_1,
            col_scope_json,
            125,
            "complete",
            (review_key,),
        )
        context.collection(col_obs)
        col_cov_scope = CoverageScope.collection(
            pr_key, "reviews", ctx_prov_1, "reviews"
        )
        context.prove_collection(
            CoverageClaim(col_cov_scope, 125, "complete"),
            col_obs,
            required_scope_json=col_scope_json,
        )

        # Issue 7 and empty collection coverage
        context.resource(issue_key, REPOSITORY)
        admit_provider_role(
            context,
            issue_key,
            "owning_repository",
            FieldClock("github:issue:updated_at", 90),
            ctx_prov_1,
            90,
        )
        context.admit_field(
            FieldCandidate(
                issue_key,
                "title",
                canonical("Track P6 edge cases"),
                FieldClock("github:issue:updated_at", 90),
                ctx_prov_1,
                90,
            )
        )
        context.observe(
            ResourceObservation(
                issue_comment_key,
                (
                    FieldCandidate(
                        issue_comment_key,
                        "author_login",
                        canonical("octocat"),
                        FieldClock("github:comment:updated_at", 95),
                        ctx_prov_1,
                        95,
                    ),
                ),
                identification=RI.scoped(
                    issue_comment_key, issue_key, "issue_comment", "ic-1"
                ),
            )
        )
        empty_scope_json = canonical(
            {
                "coverage_kind": "comments",
                "service_instance_uuidv4": SERVICE,
            }
        )
        empty_col = CollectionObservation(
            issue_key,
            "comments",
            ctx_prov_2,
            empty_scope_json,
            130,
            "complete",
            (),
        )
        context.collection(empty_col)
        empty_cov_scope = CoverageScope.collection(
            issue_key, "comments", ctx_prov_2, "comments"
        )
        context.prove_collection(
            CoverageClaim(empty_cov_scope, 130, "complete"),
            empty_col,
            required_scope_json=empty_scope_json,
        )

    # Trusted fixture composition grants only this declared synthetic catalog.
    # These grants do not authorize Provider/Exchange routes or recovery intake.
    provider_key = ResourceKey.from_native(SERVICE, "repository", "1001")
    authorization, _ = fixture_service(
        DependencySet(
            resources={
                pr_key,
                issue_key,
                review_key,
                thread_key,
                comment_key,
                issue_comment_key,
                provider_key,
            },
            repositories={REPOSITORY},
            sources={SOURCE},
            source_repository_pairs={(SOURCE, REPOSITORY)},
            provider_registrations={SERVICE},
            object_oids={commit_obj.oid, OID(fmt, "f" * width)},
            mapping_claims={
                MappingClaimKey.for_repository(
                    provider_key,
                    REPOSITORY,
                    clock=FieldClock("github:pr:updated_at", 100),
                    provenance_json=ctx_prov_1,
                ),
                MappingClaimKey.for_repository(
                    provider_key,
                    REPOSITORY,
                    clock=FieldClock("github:issue:updated_at", 90),
                    provenance_json=ctx_prov_1,
                ),
            },
        )
    )
    admission = fixture_context(authorization)

    if include_core and include_context:
        coordinator = PairCoordinator(directory, authorization=authorization)

        def core_cb(db):
            with GitCore.for_transaction(db) as c:
                admit_core(c)

        def ctx_cb(db):
            with Context.for_transaction(db, directory) as ctx:
                admit_context(ctx, core_present=True)

        coordinator.admit(core_cb, ctx_cb, admission=admission)
    elif include_core:
        core = GitCore(directory / "core.sqlite3")
        try:
            admit_core(core)
        finally:
            core.close()
    elif include_context:
        with closing(connect(directory / "context.sqlite3", "context")) as db:
            with Context.owned_transaction(
                db,
                directory,
                authorization=authorization,
                admission=admission,
            ) as ctx:
                admit_context(ctx, core_present=False)

    return {
        "absent_oid": OID(fmt, "f" * width),
        "comment_key": comment_key,
        "commit_obj": commit_obj,
        "ref_fixture": ref_fixture,
        "ctx_prov_1": ctx_prov_1,
        "ctx_prov_2": ctx_prov_2,
        "issue_comment_key": issue_comment_key,
        "issue_key": issue_key,
        "missing_blob_oid": missing_blob_oid,
        "missing_parent_oid": missing_parent_oid,
        "note_blob": note_blob,
        "note_body_bytes": note_body_bytes,
        "notes_tree": notes_tree,
        "pr_key": pr_key,
        "review_key": review_key,
        "tag_obj": tag_obj,
        "thread_key": thread_key,
        "tree_obj": tree_obj,
        "unretained_commit_oid": unretained_commit_oid,
    }
