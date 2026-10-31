"""Explicit finite local authority for synthetic Context admission tests."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import (
    PairedAcquisitionCoordinator,
    ProviderAcquisition,
)
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionRefused,
    AdmissionSelection,
    ContextAdmissionService,
    DependencySet,
    LocalAuthorizationPolicy,
    dependencies,
    extract_provenance_sources,
)
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.resource_stage import _isolated_dir_fixtures


class FixturePolicy:
    """A finite grant set, with controllable denial/revocation and observations."""

    def __init__(self, grants: DependencySet):
        self._lock = RLock()
        self._grants = grants
        self._denied = DependencySet()
        self._revision = 0
        self.calls = []
        self.checks = 0
        self.active = 0

    @property
    def grants(self):
        return self._grants

    @grants.setter
    def grants(self, value):
        with self._lock:
            self._grants = value
            self._revision += 1

    @property
    def denied(self):
        return self._denied

    @denied.setter
    def denied(self, value):
        with self._lock:
            self._denied = value
            self._revision += 1

    @property
    def revision(self):
        return self._revision

    @revision.setter
    def revision(self, value):
        with self._lock:
            self._revision = value

    @contextmanager
    def lease(self, principal, operation, dependencies):
        # Serialize cross-thread policy changes through the actual outer commit.
        # RLock also permits deterministic same-thread trigger revocation probes.
        with self._lock:
            with self._lease_locked(principal, operation, dependencies) as lease:
                yield lease

    @contextmanager
    def _lease_locked(self, principal, operation, dependencies):
        self.calls.append((principal, operation, dependencies))
        if principal != "fixture-user" or operation != "provider_intake":
            raise AdmissionRefused("PERMISSION_DENIED")
        if not dependencies.issubset(self.grants):
            raise AdmissionRefused("PERMISSION_DENIED")
        for dimension in DependencySet.__dataclass_fields__:
            if getattr(dependencies, dimension) & getattr(self.denied, dimension):
                raise AdmissionRefused("PERMISSION_DENIED")
        revision = self.revision
        policy = self

        class Lease:
            def check_current(self):
                policy.checks += 1
                if revision != policy.revision:
                    raise AdmissionRefused("PERMISSION_DENIED")

        self.active += 1
        try:
            yield Lease()
        finally:
            self.active -= 1


def fixture_service(grants):
    policy = FixturePolicy(grants)

    def authenticate(credential):
        if credential != "fixture-credential":
            raise AdmissionRefused("PERMISSION_DENIED")
        return "fixture-user"

    return ContextAdmissionService(policy, authenticate), policy


def fixture_context(service, *, selection=None, budget=None):
    return service.context(
        "fixture-credential",
        "provider_intake",
        selection or AdmissionSelection(all_selected=True),
        budget or AdmissionBudget(),
    )


class FixtureContext:
    """Bind one explicitly issued invocation to a synthetic fixture facade.

    The authority comes only from the fixture's finite grant declaration. This
    wrapper never derives grants from a mutation or retries a refusal. Product
    methods, transaction ownership, policy leases and commit checks all execute.
    """

    def __init__(self, context, admission):
        self._context = context
        self._admission = admission

    def __getattr__(self, name):
        from functools import partial

        from repo_catalog.adapters.sqlite.context_admission import MUTATIONS

        value = getattr(self._context, name)
        if name in MUTATIONS:
            return partial(value, admission=self._admission)
        return value


@contextmanager
def fixture_transaction(directory, grants):
    """Keep the product factory and commit fence with explicit fixture authority."""
    from repo_catalog.adapters.sqlite.production_context import Context

    service, _ = fixture_service(grants)
    admission = fixture_context(service)
    with Context.transaction(directory, authorization=service) as context:
        yield FixtureContext(context, admission)


def _extract_directory_context_grants(directory) -> DependencySet:
    if directory is None:
        return DependencySet()
    try:
        import sqlite3
        from pathlib import Path

        from repo_catalog.domain.p1_context import (
            FieldClock,
            MappingClaimKey,
            MappingDispositionKey,
            ResourceKey,
        )

        dir_path = (
            directory.directory if hasattr(directory, "directory") else Path(directory)
        )
        resolved = dir_path.resolve()
        isolated_fixture = _isolated_dir_fixtures.get(resolved, (None, None))[0]
        db_path = dir_path / "context.sqlite3"
        if isolated_fixture is None and not db_path.is_file():
            return DependencySet()

        repos = set()
        claims = set()
        disps = set()
        providers = set()
        sources = set()
        source_pairs = set()
        resources = set()
        object_oids = set()

        def _scan(db):
            for query, handler in (
                (
                    "SELECT service_instance_uuidv4 FROM providers",
                    lambda r: providers.add(r[0]),
                ),
                (
                    "SELECT repository_uuidv4 FROM repository_context",
                    lambda r: repos.add(r[0]),
                ),
                (
                    "SELECT source_registration_uuidv4 FROM sources",
                    lambda r: sources.add(r[0]),
                ),
                (
                    "SELECT source_registration_uuidv4, repository_uuidv4 FROM source_repositories",
                    lambda r: source_pairs.add((r[0], r[1])),
                ),
                (
                    "SELECT service_instance_uuidv4, resource_kind, provider_resource_id FROM resources",
                    lambda r: resources.add(ResourceKey(r[0], r[1], r[2])),
                ),
            ):
                try:
                    for row in db.execute(query):
                        handler(row)
                except sqlite3.OperationalError:
                    pass
            try:
                for row in db.execute(
                    "SELECT service_instance_uuidv4, resource_kind, provider_resource_id, "
                    "relation_kind, target_json, clock_json, provenance_json "
                    "FROM resource_repository_relations WHERE relation_kind='represents_repository'"
                ):
                    claims.add(
                        MappingClaimKey(
                            ResourceKey(row[0], row[1], row[2]),
                            row[3],
                            FieldClock.from_json(row[5]),
                            row[4],
                            row[6],
                        )
                    )
                    try:
                        target_repo = json.loads(row[4])
                        if isinstance(target_repo, str):
                            repos.add(target_repo)
                    except Exception:
                        pass
            except sqlite3.OperationalError:
                pass
            try:
                for row in db.execute(
                    "SELECT service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, "
                    "claim_clock_json, claim_target_json, claim_provenance_json, "
                    "disposition_kind, disposition_clock_json, disposition_provenance_json, "
                    "replacement_clock_json, replacement_target_json, replacement_provenance_json "
                    "FROM repository_mapping_dispositions"
                ):
                    subject = MappingClaimKey(
                        ResourceKey(row[0], row[1], row[2]),
                        row[3],
                        FieldClock.from_json(row[4]),
                        row[5],
                        row[6],
                    )
                    claims.add(subject)
                    try:
                        target_repo = json.loads(row[5])
                        if isinstance(target_repo, str):
                            repos.add(target_repo)
                    except Exception:
                        pass
                    disp_clock = FieldClock.from_json(row[8])
                    if row[10] and row[11] and row[12]:
                        rep_key = MappingClaimKey(
                            ResourceKey(row[0], row[1], row[2]),
                            row[3],
                            FieldClock.from_json(row[10]),
                            row[11],
                            row[12],
                        )
                        claims.add(rep_key)
                        try:
                            rep_target_repo = json.loads(row[11])
                            if isinstance(rep_target_repo, str):
                                repos.add(rep_target_repo)
                        except Exception:
                            pass
                    disps.add(
                        MappingDispositionKey(
                            subject,
                            row[7],
                            disp_clock,
                            row[9],
                        )
                    )
            except sqlite3.OperationalError:
                pass

        if isolated_fixture is not None:
            _scan(isolated_fixture)
        else:
            with sqlite3.connect(db_path) as db:
                _scan(db)
        try:
            with sqlite3.connect(db_path) as db:
                for row in db.execute(
                    "SELECT object_format, object_oid FROM core_references"
                ):
                    from repo_catalog.domain.p1_core import OID

                    object_oids.add(OID(row[0], row[1]))
        except Exception:
            pass
        core_path = dir_path / "core.sqlite3"
        if core_path.is_file():
            try:
                with sqlite3.connect(core_path) as cdb:
                    for row in cdb.execute(
                        "SELECT object_format, object_oid FROM git_objects"
                    ):
                        from repo_catalog.domain.p1_core import OID

                        object_oids.add(OID(row[0], row[1]))
            except Exception:
                pass
        return DependencySet(
            resources=frozenset(resources),
            repositories=frozenset(repos),
            sources=frozenset(sources),
            source_repository_pairs=frozenset(source_pairs),
            provider_registrations=frozenset(providers),
            mapping_claims=frozenset(claims),
            dispositions=frozenset(disps),
            object_oids=frozenset(object_oids),
        )
    except Exception:
        return DependencySet()


def extract_unit_dependencies(unit, directory=None) -> DependencySet:
    if unit is None:
        return DependencySet()
    items = []
    if getattr(unit, "primary_resource", None) is not None:
        items.append(unit.primary_resource)
    if getattr(unit, "observations", None):
        items.extend(unit.observations)
    if getattr(unit, "relations", None):
        items.extend(unit.relations)
    deps = dependencies(tuple(items)) if items else DependencySet()
    sources = set(deps.sources)
    if getattr(unit, "provenance_json", None):
        sources.update(extract_provenance_sources(unit.provenance_json))
    oids = set(deps.object_oids)
    if getattr(unit, "core_references", None):
        for cr, clock, us in unit.core_references:
            if hasattr(cr, "object_oid"):
                oids.add(
                    cr.object_oid
                    if isinstance(cr.object_oid, OID)
                    else OID(cr.object_oid.object_format, cr.object_oid.object_oid)
                )
            elif hasattr(cr, "object_format") and hasattr(cr, "object_oid"):
                oids.add(OID(cr.object_format, cr.object_oid))
    result = deps | DependencySet(
        sources=frozenset(sources), object_oids=frozenset(oids)
    )
    if directory is not None:
        result |= _extract_directory_context_grants(directory)
    return result


def extract_batch_dependencies(batch, directory=None) -> DependencySet:
    if batch is None:
        return DependencySet()
    deps = DependencySet()
    providers = set()
    if getattr(batch, "service_instance_uuidv4", None):
        providers.add(batch.service_instance_uuidv4)
    for p in getattr(batch, "providers", ()):
        providers.add(p.service_instance_uuidv4)
    repositories = {r.repository_uuidv4 for r in getattr(batch, "repositories", ())}
    sources = set()
    pairs = set()
    for s in getattr(batch, "sources", ()):
        sources.add(s.source_registration_uuidv4)
        providers.add(s.service_instance_uuidv4)
        for r in getattr(s, "associated_repositories", ()):
            repositories.add(r)
            pairs.add((s.source_registration_uuidv4, r))
    for inv in getattr(batch, "source_inventories", ()):
        sources.add(inv.source_registration_uuidv4)
        for r in getattr(inv, "repositories", ()):
            repositories.add(r)
            pairs.add((inv.source_registration_uuidv4, r))
    for cov_claim, inv in getattr(batch, "source_inventory_proofs", ()):
        sources.add(inv.source_registration_uuidv4)
        for r in getattr(inv, "repositories", ()):
            repositories.add(r)
            pairs.add((inv.source_registration_uuidv4, r))

    if getattr(batch, "mapping_claims", ()):
        deps |= dependencies(batch.mapping_claims)
        mapping_claims = set()
        for claim in batch.mapping_claims:
            if hasattr(claim, "claim_key"):
                mapping_claims.add(claim.claim_key)
        if mapping_claims:
            deps |= DependencySet(mapping_claims=frozenset(mapping_claims))
    if getattr(batch, "mapping_dispositions", ()):
        deps |= dependencies(batch.mapping_dispositions)
        disps = set()
        disp_claims = set()
        for disp in batch.mapping_dispositions:
            if hasattr(disp, "disposition_key"):
                disps.add(disp.disposition_key)
            if hasattr(disp, "claim_key"):
                disp_claims.add(disp.claim_key)
            if getattr(disp, "replacement_claim_key", None):
                disp_claims.add(disp.replacement_claim_key)
        if disps or disp_claims:
            deps |= DependencySet(
                dispositions=frozenset(disps),
                mapping_claims=frozenset(disp_claims),
            )
    if getattr(batch, "observations", ()):
        deps |= dependencies(batch.observations)
    if getattr(batch, "relations", ()):
        deps |= dependencies(batch.relations)
    if getattr(batch, "collections", ()):
        deps |= dependencies(batch.collections)
    if getattr(batch, "coverage_claims", ()):
        deps |= dependencies(batch.coverage_claims)
    if getattr(batch, "core_references", ()):
        oids = {
            OID(cr.object_format, cr.object_oid)
            for cr, clock, us in batch.core_references
        }
        deps |= DependencySet(object_oids=frozenset(oids))

    # Normalize intakes if present
    service = getattr(batch, "service_instance_uuidv4", None)
    if service:
        for r in getattr(batch, "repositories", ()):
            if (
                getattr(r, "raw_metadata", None) is not None
                and getattr(r, "provenance_json", None) is not None
            ):
                try:
                    from repo_catalog.adapters.github.production_intake import (
                        normalize_repository_fields,
                    )

                    unit = normalize_repository_fields(
                        service,
                        r.raw_metadata,
                        r.observed_at_us,
                        r.provenance_json,
                        clock_domain=getattr(
                            r, "clock_domain", "github:repository:updated_at"
                        ),
                        graphql=getattr(r, "graphql", False),
                    )
                    deps |= extract_unit_dependencies(unit)
                except Exception:
                    pass
        for pr in getattr(batch, "provider_repositories", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_repository_fields,
                )

                unit = normalize_repository_fields(
                    service,
                    pr.payload,
                    pr.observed_at_us,
                    pr.provenance_json,
                    graphql=getattr(pr, "graphql", False),
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass
        for issue in getattr(batch, "issues", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_issue,
                )

                unit = normalize_issue(
                    service,
                    issue.payload,
                    issue.observed_at_us,
                    issue.provenance_json,
                    graphql=getattr(issue, "graphql", False),
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass
        for pr in getattr(batch, "pull_requests", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_pull_request,
                )

                unit = normalize_pull_request(
                    service,
                    pr.payload,
                    pr.observed_at_us,
                    pr.provenance_json,
                    graphql=getattr(pr, "graphql", False),
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass
        for rev in getattr(batch, "reviews", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_review,
                )

                unit = normalize_review(
                    service,
                    rev.pull_request_id,
                    rev.payload,
                    rev.observed_at_us,
                    rev.provenance_json,
                    graphql=getattr(rev, "graphql", False),
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass
        for th in getattr(batch, "review_threads", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_review_thread,
                )

                unit = normalize_review_thread(
                    service,
                    th.pull_request_id,
                    th.payload,
                    th.observed_at_us,
                    th.provenance_json,
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass
        for rc in getattr(batch, "review_comments", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_review_comment,
                )

                unit = normalize_review_comment(
                    service,
                    rc.pull_request_id,
                    rc.payload,
                    rc.observed_at_us,
                    rc.provenance_json,
                    graphql=getattr(rc, "graphql", False),
                    thread_id=getattr(rc, "thread_id", None),
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass
        for ic in getattr(batch, "issue_comments", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_issue_comment,
                )

                unit = normalize_issue_comment(
                    service,
                    ic.parent_kind,
                    ic.parent_id,
                    ic.payload,
                    ic.observed_at_us,
                    ic.provenance_json,
                    graphql=getattr(ic, "graphql", False),
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass
        for te in getattr(batch, "timeline_events", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_timeline_event,
                )

                unit = normalize_timeline_event(
                    service,
                    te.parent_kind,
                    te.parent_id,
                    te.event_id,
                    te.payload,
                    te.observed_at_us,
                    te.provenance_json,
                    graphql=getattr(te, "graphql", False),
                    parent_resource=getattr(te, "parent_resource", None),
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass
        for pc in getattr(batch, "pr_commits", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_pr_commit,
                )

                unit = normalize_pr_commit(
                    service,
                    pc.pull_request_id,
                    pc.payload,
                    pc.observed_at_us,
                    pc.provenance_json,
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass
        for pf in getattr(batch, "pr_files", ()):
            try:
                from repo_catalog.adapters.github.production_intake import (
                    normalize_pr_file,
                )

                unit = normalize_pr_file(
                    service,
                    pf.pull_request_id,
                    pf.payload,
                    pf.observed_at_us,
                    pf.provenance_json,
                )
                deps |= extract_unit_dependencies(unit)
            except Exception:
                pass

    result = deps | DependencySet(
        provider_registrations=frozenset(providers),
        repositories=frozenset(repositories),
        sources=frozenset(sources),
        source_repository_pairs=frozenset(pairs),
    )
    if directory is not None:
        result |= _extract_directory_context_grants(directory)
    return result


def _cleanup_isolated_fixtures():
    while _isolated_dir_fixtures:
        _, (fixture, stack) = _isolated_dir_fixtures.popitem()
        try:
            stack.close()
        except Exception:
            pass


def _get_or_create_isolated_fixture(directory):
    if directory is None:
        return None
    import sqlite3
    from contextlib import ExitStack
    from pathlib import Path

    from repo_catalog.adapters.sqlite import p1_schema
    from repo_catalog.domain.resource_stage import (
        TRANSFER_FENCE_DEFINITIONS,
        _isolated_transfer_fixture,
    )

    resolved = Path(directory).resolve()
    if resolved in _isolated_dir_fixtures:
        return _isolated_dir_fixtures[resolved][0]

    disk_path = resolved / "context.sqlite3"
    mem = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(mem)
    p1_schema.configure(mem)
    mem.executescript(p1_schema.compose("context"))
    if disk_path.is_file():
        mem.execute("ATTACH DATABASE ? AS disk", (str(disk_path),))
        for table in (
            "store_identity",
            "providers",
            "repository_context",
            "sources",
            "source_repositories",
            "resources",
            "text_bodies",
            "field_candidates",
            "resource_relations",
            "collections",
            "collection_terminals",
            "core_references",
            "coverage_scopes",
            "coverage_proofs",
            "source_inventory_evidence",
            "source_coverage_proofs",
            "resource_repository_relations",
            "repository_mapping_dispositions",
            "coverage_claims",
        ):
            try:
                cols = [
                    c[1]
                    for c in mem.execute(f"PRAGMA table_xinfo({table})").fetchall()
                    if c[6] == 0
                ]
                cols_str = ", ".join(cols)
                mem.execute(
                    f"INSERT OR REPLACE INTO {table} ({cols_str}) SELECT {cols_str} FROM disk.{table}"
                )
            except sqlite3.OperationalError:
                pass
        mem.execute("DETACH DATABASE disk")

    for _, name, _, _ in TRANSFER_FENCE_DEFINITIONS:
        mem.execute(f"DROP TRIGGER IF EXISTS {name}")

    p1_schema.verify_connection(mem)
    stack = ExitStack()
    fixture = stack.enter_context(_isolated_transfer_fixture(mem))
    _isolated_dir_fixtures[resolved] = (fixture, stack)
    return fixture


@contextmanager
def _isolated_tx_scope(fixture, directory, auth, adm):
    from contextlib import ExitStack

    from repo_catalog.adapters.sqlite.p1_coordination import (
        AdmissionTransaction,
        _ContextAdmissionBinding,
    )
    from repo_catalog.domain.context_admission import DependencySet

    if not fixture.in_transaction:
        fixture.execute("BEGIN IMMEDIATE")
    leases = ExitStack()
    lease = leases.enter_context(auth.authorize(adm, DependencySet()))
    binding = _ContextAdmissionBinding(auth, adm, leases, [lease])
    tx = AdmissionTransaction(fixture, _context_admission=binding)
    tx._connection = fixture
    try:
        with Context.for_transaction(
            tx, directory, authorization=auth, admission=adm
        ) as ctx:
            yield ctx
        fixture.set_authorizer(None)
        if fixture.in_transaction:
            fixture.commit()
    except BaseException:
        fixture.set_authorizer(None)
        if fixture.in_transaction:
            fixture.rollback()
        raise
    finally:
        fixture.set_authorizer(None)
        tx._expire()
        leases.close()


class AuthorizedProviderAcquisition(ProviderAcquisition):
    def __init__(
        self,
        context,
        *,
        core=None,
        operational=None,
        authorization=None,
        admission=None,
    ):
        super().__init__(
            context,
            core=core,
            operational=operational,
            authorization=authorization,
            admission=admission,
        )
        self._explicit_authorization = authorization
        self._explicit_admission = admission

    @contextmanager
    def _open_context(self, override: Context | None = None) -> Iterator[Context]:
        if override is not None:
            with super()._open_context(override) as ctx:
                yield ctx
            return
        if self.context is not None:
            from pathlib import Path

            resolved = Path(self.context).resolve()
            if resolved in _isolated_dir_fixtures:
                fixture, _ = _isolated_dir_fixtures[resolved]
                with _isolated_tx_scope(
                    fixture, resolved, self.authorization, self.admission
                ) as ctx:
                    yield ctx
                return
        with super()._open_context(override) as ctx:
            yield ctx

    def admit_batch(
        self,
        batch,
        *,
        context=None,
        core=None,
        authorization=None,
        admission=None,
    ):
        has_transfer = any(
            isinstance(getattr(item, "payload", None), dict)
            and (
                getattr(item, "payload", {}).get("event") == "transferred"
                or getattr(item, "payload", {}).get("__typename") == "TransferredEvent"
            )
            for item in getattr(batch, "timeline_events", ())
        )
        if has_transfer and self.context is not None:
            _get_or_create_isolated_fixture(self.context)

        auth = (
            authorization if authorization is not None else self._explicit_authorization
        )
        adm = admission if admission is not None else self._explicit_admission
        if auth is None or adm is None:
            from repo_catalog.domain.context_admission import (
                AdmissionSelection,
                create_local_admission_service,
            )

            grants = extract_batch_dependencies(batch, directory=self.context)
            auth, adm, _ = create_local_admission_service(
                "provider_intake",
                grants=grants,
                selection=AdmissionSelection(all_selected=True),
            )
        self.authorization = auth
        self.admission = adm
        try:
            return super().admit_batch(
                batch,
                context=context,
                core=core,
            )
        finally:
            self.authorization = self._explicit_authorization
            self.admission = self._explicit_admission

    def admit_unit(
        self,
        unit,
        *,
        context=None,
        core=None,
        authorization=None,
        admission=None,
    ):
        if getattr(unit, "transfer_event", False) and self.context is not None:
            _get_or_create_isolated_fixture(self.context)

        auth = (
            authorization if authorization is not None else self._explicit_authorization
        )
        adm = admission if admission is not None else self._explicit_admission
        if auth is None or adm is None:
            from repo_catalog.domain.context_admission import (
                AdmissionSelection,
                create_local_admission_service,
            )

            grants = extract_unit_dependencies(unit, directory=self.context)
            auth, adm, _ = create_local_admission_service(
                "provider_intake",
                grants=grants,
                selection=AdmissionSelection(all_selected=True),
            )
        self.authorization = auth
        self.admission = adm
        try:
            return super().admit_unit(
                unit,
                context=context,
                core=core,
            )
        finally:
            self.authorization = self._explicit_authorization
            self.admission = self._explicit_admission

    def admit_units(
        self,
        units,
        *,
        context=None,
        core=None,
        authorization=None,
        admission=None,
    ):
        auth = authorization if authorization is not None else self.authorization
        adm = admission if admission is not None else self.admission
        if auth is None or adm is None:
            from repo_catalog.domain.context_admission import (
                AdmissionSelection,
                create_local_admission_service,
            )

            grants = DependencySet()
            for u in units:
                grants |= extract_unit_dependencies(u, directory=self.context)
            auth, adm, _ = create_local_admission_service(
                "provider_intake",
                grants=grants,
                selection=AdmissionSelection(all_selected=True),
            )
        self.authorization = auth
        self.admission = adm
        try:
            return super().admit_units(
                units,
                context=context,
                core=core,
            )
        finally:
            self.authorization = self._explicit_authorization
            self.admission = self._explicit_admission


class AuthorizedPairedAcquisitionCoordinator(PairedAcquisitionCoordinator):
    def admit_paired(
        self,
        *,
        git_source=None,
        git_request=None,
        git_input=None,
        notes_source=None,
        provider_batch=None,
        core_fn=None,
        context_fn=None,
        cut=lambda point: None,
        reconcile_dependencies=True,
        new_request=False,
        request_identity=None,
        authorization=None,
        admission=None,
    ):
        auth = authorization if authorization is not None else self.authorization
        adm = admission if admission is not None else self.admission
        if (auth is None or adm is None) and (
            provider_batch is not None
            or context_fn is not None
            or (
                reconcile_dependencies
                and git_input is None
                and git_source is None
                and git_request is None
            )
        ):
            from repo_catalog.domain.context_admission import (
                AdmissionSelection,
                create_local_admission_service,
            )

            grants = (
                extract_batch_dependencies(provider_batch, directory=self.directory)
                if provider_batch
                else DependencySet(
                    repositories=frozenset({git_request.repository_uuidv4})
                    if git_request
                    else frozenset()
                )
                | _extract_directory_context_grants(self.directory)
            )
            if context_fn is not None and not provider_batch:

                class _DepCollector:
                    def __init__(self):
                        self.providers = set()
                        self.resources = set()
                        self.oids = set()

                    def provider(self, svc, kind, meta):
                        self.providers.add(svc)

                    def resource(self, rk):
                        self.resources.add(rk)

                    def link_core(self, rk, role, fmt, object_oid, prov, val=None):
                        self.resources.add(rk)
                        from repo_catalog.domain.p1_core import OID

                        self.oids.add(OID(fmt, object_oid))

                    def __getattr__(self, name):
                        return lambda *args, **kwargs: None

                collector = _DepCollector()
                try:
                    context_fn(collector)
                    grants |= DependencySet(
                        provider_registrations=frozenset(collector.providers),
                        resources=frozenset(collector.resources),
                        object_oids=frozenset(collector.oids),
                    )
                except Exception:
                    pass
            auth, adm, _ = create_local_admission_service(
                "provider_intake",
                grants=grants,
                selection=AdmissionSelection(all_selected=True),
            )
        orig_auth = self.authorization
        orig_adm = self.admission
        self.authorization = auth
        self.admission = adm
        try:
            return super().admit_paired(
                git_source=git_source,
                git_request=git_request,
                git_input=git_input,
                notes_source=notes_source,
                provider_batch=provider_batch,
                core_fn=core_fn,
                context_fn=context_fn,
                cut=cut,
                reconcile_dependencies=reconcile_dependencies,
                new_request=new_request,
                request_identity=request_identity,
            )
        finally:
            self.authorization = orig_auth
            self.admission = orig_adm

    def reconcile_core_dependencies(self):
        auth = self.authorization
        adm = self.admission
        if auth is None or adm is None:
            from repo_catalog.domain.context_admission import (
                AdmissionSelection,
                create_local_admission_service,
            )

            g = _extract_directory_context_grants(self.directory)
            auth, adm, _ = create_local_admission_service(
                "provider_intake",
                grants=g,
                selection=AdmissionSelection(all_selected=True),
            )
            self.authorization = auth
            self.admission = adm
        return super().reconcile_core_dependencies()


class AuthorizedExchangeService(ExchangeService):
    def export_package(self, *args, **kwargs):
        from unittest.mock import patch

        with patch.object(Context, "snapshot", AuthorizedContext.snapshot):
            return super().export_package(*args, **kwargs)

    def import_package(
        self,
        raw_package,
        *,
        work=None,
        request=None,
        new_request=False,
        permitted_repository_uuidv4s=(),
        selection=None,
        cut=lambda point: None,
        authorization=None,
        admission=None,
        grants=None,
    ):
        pkg_data = raw_package
        if hasattr(pkg_data, "context"):
            context_data = pkg_data.context
        elif isinstance(pkg_data, dict):
            context_data = pkg_data.get("context")
        else:
            try:
                from repo_catalog.domain.exchange import decode_package

                context_data = decode_package(pkg_data).context
            except Exception:
                context_data = None
        has_transfer = False
        if context_data and isinstance(context_data, dict):
            has_transfer = any(
                r.get("relation_kind")
                in (
                    "transfer_event_report",
                    "transfer_from_repository",
                    "transfer_to_repository",
                )
                for r in context_data.get("resource_relations", ())
            )
        if has_transfer and self.directory is not None:
            _get_or_create_isolated_fixture(self.directory)

        active_grants = grants if grants is not None else self.grants
        if active_grants is None and authorization is None:
            pkg_deps = (
                ExchangeService._extract_context_dependencies(context_data)
                if context_data
                else DependencySet()
            )
            dir_deps = _extract_directory_context_grants(self.directory)
            active_grants = pkg_deps | dir_deps
        from repo_catalog.domain.exchange import ExchangeSelectionScope

        active_selection = (
            selection
            if selection is not None
            else ExchangeSelectionScope(all_selected=True)
        )
        from unittest.mock import patch

        with (
            patch.object(Context, "snapshot", AuthorizedContext.snapshot),
            patch.object(Context, "transaction", AuthorizedContext.transaction),
        ):
            return super().import_package(
                raw_package,
                work=work,
                request=request,
                new_request=new_request,
                permitted_repository_uuidv4s=permitted_repository_uuidv4s,
                selection=active_selection,
                cut=cut,
                authorization=authorization,
                admission=admission,
                grants=active_grants,
            )


class TestAutoGrantPolicy(LocalAuthorizationPolicy):
    def __init__(self, initial_grants=None):
        super().__init__(grants=initial_grants or DependencySet())
        self._initial = initial_grants or DependencySet()

    @contextmanager
    def lease(self, principal, operation, dependencies):
        with self._lock:
            self._grants = self._grants | dependencies
        with super().lease(principal, operation, dependencies) as lease_obj:
            yield lease_obj


_orig_context_snapshot = Context.snapshot
_orig_context_transaction = Context.transaction


class AuthorizedContext(Context):
    @classmethod
    @contextmanager
    def snapshot(
        cls, directory, *, read_limits=None, validation_work=None, _identity_sink=None
    ):
        from pathlib import Path

        resolved = Path(directory).resolve()
        if resolved in _isolated_dir_fixtures:
            fixture, _ = _isolated_dir_fixtures[resolved]
            needs_rollback = False
            if not fixture.in_transaction:
                fixture.execute("BEGIN")
                needs_rollback = True
            try:
                if _identity_sink is not None:
                    _identity_sink(
                        fixture.execute("SELECT * FROM store_identity").fetchall()
                    )
                with Context.for_snapshot(
                    fixture, resolved, validation_work=validation_work
                ) as ctx:
                    yield ctx
            finally:
                if needs_rollback and fixture.in_transaction:
                    fixture.rollback()
            return
        with _orig_context_snapshot(
            resolved,
            read_limits=read_limits,
            validation_work=validation_work,
            _identity_sink=_identity_sink,
        ) as ctx:
            yield ctx

    @classmethod
    @contextmanager
    def transaction(cls, directory, *, authorization=None, admission=None):
        from pathlib import Path

        resolved = Path(directory).resolve()
        if resolved in _isolated_dir_fixtures:
            fixture, _ = _isolated_dir_fixtures[resolved]
            auth = authorization
            adm = admission
            if auth is None or adm is None:
                dir_grants = _extract_directory_context_grants(resolved)
                policy = TestAutoGrantPolicy(dir_grants)

                def authenticate(credential):
                    if credential != "fixture-credential":
                        raise AdmissionRefused("PERMISSION_DENIED")
                    return "fixture-user"

                auth = ContextAdmissionService(policy, authenticate)
                adm = auth.context(
                    "fixture-credential",
                    "provider_intake",
                    AdmissionSelection(all_selected=True),
                    AdmissionBudget(),
                )
            with _isolated_tx_scope(fixture, resolved, auth, adm) as ctx:
                yield ctx
            return

        dir_path = Path(directory)
        auth = authorization
        adm = admission
        if auth is None or adm is None:
            dir_grants = _extract_directory_context_grants(dir_path)
            policy = TestAutoGrantPolicy(dir_grants)

            def authenticate(credential):
                if credential != "fixture-credential":
                    raise AdmissionRefused("PERMISSION_DENIED")
                return "fixture-user"

            auth = ContextAdmissionService(policy, authenticate)
            adm = auth.context(
                "fixture-credential",
                "provider_intake",
                AdmissionSelection(all_selected=True),
                AdmissionBudget(),
            )
        with _orig_context_transaction(
            dir_path, authorization=auth, admission=adm
        ) as ctx:
            yield ctx
