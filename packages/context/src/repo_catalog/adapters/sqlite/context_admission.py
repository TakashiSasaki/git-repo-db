"""Commit-owned admission fences shared by the Context store and facade.

The authorization port is trusted local infrastructure. A SQL connection is not
an input capability, and a caller-owned outer transaction cannot carry a lease
past our return: those unwired paths deliberately refuse writes.
"""

from contextlib import ExitStack, contextmanager
from functools import wraps
from inspect import Parameter, signature

from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    ContextAdmissionService,
    DependencySet,
    dependencies,
)

MUTATIONS = frozenset(
    {
        "provider",
        "admit_identity_evidence",
        "repository",
        "source",
        "associate_source",
        "inventory",
        "admit_inventory_history",
        "resource",
        "observe",
        "inherit_fields",
        "relation",
        "collection",
        "prove_collection",
        "admit_collection_history",
        "prove_inventory",
        "text",
        "admit_text",
        "admit_field",
        "admit_repository_relation",
        "admit_repository_relation_result",
        "admit_mapping_disposition",
        "admit_transfer_event",
        "scope",
        "admit_coverage",
        "link_core",
        "report_core_reference",
    }
)


def _arguments(operation, self, args, kwargs):
    return signature(operation).bind(self, *args, **kwargs).arguments


def _dependencies(name, values):
    # Domain units enumerate their complete typed inputs without local lookups.
    result = dependencies(
        tuple(
            value
            for key, value in values.items()
            if key not in {"self", "validate", "permitted"}
        )
    )
    from repo_catalog.domain.context_admission import extract_provenance_sources

    for key, value in values.items():
        if key.endswith("provenance_json") and value is not None:
            result |= DependencySet(sources=extract_provenance_sources(value))
    if name == "link_core":
        from repo_catalog.domain.shared_values import OID

        result |= DependencySet(
            object_oids={OID(values["object_format"], values["object_oid"])}
        )
    if name == "admit_identity_evidence":
        import json

        record = json.loads(values["record_json"])
        providers = ()
        if values["kind"] == "relation":
            providers = (
                record["left_service_instance_uuidv4"],
                record["right_service_instance_uuidv4"],
            )
        result |= DependencySet(
            identity_assertions={record["relation_uuidv4"]},
            provider_registrations=providers,
        )
    repositories = set(result.repositories)
    sources = set(result.sources)
    providers = set(result.provider_registrations)
    if name == "provider":
        providers.add(values["service"])
    if name == "repository":
        repositories.add(values["repository_uuidv4"])
    if name in {"source", "associate_source"}:
        sources.add(values["source"])
    if name == "source":
        providers.add(values["service"])
    for key in ("repository_uuidv4",):
        if values.get(key) is not None:
            repositories.add(values[key])
    pairs = set(result.source_repository_pairs)
    if name == "associate_source":
        repository = values.get("repository", values.get("repository_uuidv4"))
        repositories.add(repository)
        pairs.add((values["source"], repository))
    return result | DependencySet(
        repositories=repositories,
        sources=sources,
        source_repository_pairs=pairs,
        provider_registrations=providers,
    )


def _registered_source_dependencies(name, values):
    """Separate Source-owned units from attributed original-origin references.

    This does not remove either kind from permission/selection dependencies.
    Only local registration existence differs: an original may name a detached
    Source, while a Source owner or association still needs its real local row.
    """
    from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope
    from repo_catalog.domain.production_context import SourceInventory

    result = set()
    if name in {"source", "associate_source"}:
        result.add(values["source"])
    pending = [value for key, value in values.items() if key != "self"]
    while pending:
        value = pending.pop()
        if isinstance(value, CoverageClaim):
            pending.append(value.scope)
        elif isinstance(value, CoverageScope):
            if value.owner_kind in {"source", "source_inventory"}:
                result.add(value.coordinates[0])
        elif isinstance(value, SourceInventory):
            result.add(value.source_registration_uuidv4)
        elif type(value) in (tuple, list):
            pending.extend(value)
    return frozenset(result)


def admission_checked(operation):
    """Expose a keyword admission context on every input mutation entry point."""
    name = operation.__name__
    if name not in MUTATIONS:
        return operation

    @wraps(operation)
    def call(self, *args, admission=None, **kwargs):
        self._check_mutation_capability()
        if self._admission_owner is not None:
            self._admission_owner._check_admission_active()
        service = self._authorization
        if not isinstance(service, ContextAdmissionService):
            raise AdmissionRefused("PERMISSION_DENIED")
        context = admission if admission is not None else self._transaction_admission
        if context is None and self._admission_depth:
            context = self._current_admission
        service.validate_context(context)
        if (
            self._admission_owner is not None
            and context is not self._transaction_admission
        ):
            raise AdmissionRefused("PERMISSION_DENIED")
        if context.operation == "exchange_export":
            raise AdmissionRefused("PERMISSION_DENIED")
        if self._admission_leases is None:
            raise AdmissionRefused("ADMISSION_TRANSACTION_REQUIRED")
        values = _arguments(operation, self, args, kwargs)
        service.charge_input(
            context,
            tuple(
                value
                for key, value in values.items()
                if key not in {"self", "validate", "permitted"}
            ),
        )
        required = _dependencies(name, values)
        lease = self._admission_leases.enter_context(
            service.authorize(context, required)
        )
        self._admission_live_leases.append(lease)
        # R12 orders permanent native semantics after authority/selection but
        # before missing-dependency diagnostics, including Source lookups.
        if name == "admit_transfer_event":
            from repo_catalog.domain.context_admission import validate_originals
            from repo_catalog.domain.p1_context import TransferEventReport
            from repo_catalog.domain.resource_stage import (
                UnsupportedResourceStage,
                has_transfer_fence,
            )

            report = values["report"]
            # Keep ordinary Transfer fenced. In the explicit isolated fixture,
            # revalidate the caller's current complete originals after authority
            # and selection, before any dependency lookup, SQL serialization or
            # duplicate success. Construction is not a seal on nested carriers.
            fenced = has_transfer_fence(self.db)
            try:
                validate_originals(report)
            except (AdmissionRefused, ValueError):
                if fenced:
                    raise UnsupportedResourceStage("admit_transfer_event") from None
                raise
            if (
                isinstance(report, TransferEventReport)
                and report.parent_issue != report.issue_resource
            ):
                raise AdmissionRefused("QS10_PARENT_INELIGIBLE")
            if fenced:
                raise UnsupportedResourceStage("admit_transfer_event")
        # Do not obtain existence-sensitive diagnostics before current authority.
        self._current_admission_for_expansion = context
        self._check_source_dependencies(
            required,
            creating=name
            in {"source", "associate_source", "inventory", "admit_inventory_history"},
            registered_sources=_registered_source_dependencies(name, values),
        )
        if name not in {
            "source",
            "associate_source",
            "inventory",
            "admit_inventory_history",
        }:
            pairs = set()
            for source in required.sources:
                for repository in required.repositories:
                    rows = self._bounded_admission_rows(
                        "SELECT 1 FROM source_repositories "
                        "WHERE source_registration_uuidv4=? AND repository_uuidv4=?",
                        (source, repository),
                    )
                    if rows:
                        pairs.add((source, repository))
            if pairs:
                self._authorize_dependencies(
                    DependencySet(source_repository_pairs=pairs)
                )
        previous = self._current_admission
        self._current_admission = context
        self._admission_depth += 1
        self.db.execute("SAVEPOINT context_admission_unit")
        try:
            result = operation(self, *args, **kwargs)
            lease.check_current()
            self.db.execute("RELEASE context_admission_unit")
            return result
        except BaseException as error:
            self._rollback_unit("context_admission_unit", error)
            raise
        finally:
            self._admission_depth -= 1
            self._current_admission = previous

    current = signature(operation)
    parameters = list(current.parameters.values())
    parameters.append(Parameter("admission", Parameter.KEYWORD_ONLY, default=None))
    call.__signature__ = current.replace(parameters=parameters)
    return call


class AdmissionTransactions:
    def _check_mutation_capability(self):
        """Optional pure local capability check, before any authority or lookup."""
        if self._admission_failed_cleanup is not None:
            raise AdmissionRefused("ADMISSION_TRANSACTION_REQUIRED")

    def _raise_failed_cleanup(self):
        if self._admission_failed_cleanup is not None:
            raise self._admission_failed_cleanup

    def _discard_failed_cleanup(self, original, cleanup):
        """A failed undo must never leave a partial unit available for commit."""
        if self._admission_failed_cleanup is not None:
            return
        self._admission_failed_cleanup = original
        self._active = False
        original.add_note(
            f"Context transaction cleanup failed: {type(cleanup).__name__}: {cleanup}"
        )
        from repo_catalog.adapters.sqlite.admission_transaction import (
            AdmissionTransaction,
        )
        from repo_catalog.adapters.sqlite.production_context import _GuardedConnection

        connection = self.db
        if type(connection) is _GuardedConnection:
            connection = connection._connection
        try:
            if isinstance(connection, AdmissionTransaction):
                connection._abort(original)
            else:
                connection.close()
        except BaseException as discard:
            original.add_note(
                f"Context connection discard failed: {type(discard).__name__}: {discard}"
            )
        finally:
            # This may be the coordinator's shared stack. Release every owned
            # lease now; neither this facade nor its SQL guard can be reused.
            if self._admission_leases is not None:
                try:
                    self._admission_leases.close()
                except BaseException as release:
                    original.add_note(
                        f"Context lease cleanup failed: {type(release).__name__}: {release}"
                    )

    def _rollback_unit(self, name, original):
        if self._admission_failed_cleanup is not None:
            return
        try:
            self.db.execute(f"ROLLBACK TO {name}")
            self.db.execute(f"RELEASE {name}")
        except BaseException as cleanup:
            self._discard_failed_cleanup(original, cleanup)

    def _init_admission(self, authorization):
        if authorization is not None and not isinstance(
            authorization, ContextAdmissionService
        ):
            raise AdmissionRefused("PERMISSION_DENIED")
        self._authorization = authorization
        self._admission_leases = None
        self._transaction_admission = None
        self._current_admission = None
        self._current_admission_for_expansion = None
        self._admission_depth = 0
        self._admission_live_leases = []
        self._admission_owner = None
        self._admission_failed_cleanup = None
        # Only the exact coordinator capability and its exact facade wrapper
        # carry trusted commit ownership. Caller duck types never supply it.
        from repo_catalog.adapters.sqlite.context_transaction import (
            AdmissionTransaction,
        )
        from repo_catalog.adapters.sqlite.production_context import _GuardedConnection

        connection = self.db
        if type(connection) is _GuardedConnection:
            connection = connection._connection
        if type(connection) is AdmissionTransaction:
            self._admission_owner = connection
            binding = connection.context_admission_binding
            if binding is not None:
                if (
                    authorization is not None
                    and authorization is not binding.authorization
                ):
                    raise AdmissionRefused("PERMISSION_DENIED")
                binding.authorization.validate_context(binding.admission)
                self._authorization = binding.authorization
                self._transaction_admission = binding.admission
                self._admission_leases = binding.leases
                self._admission_live_leases = binding.live_leases

    def _check_source_dependencies(
        self, required, *, creating=False, registered_sources=frozenset()
    ):
        registered_services = set()
        for source in registered_sources:
            row = self.db.execute(
                "SELECT service_instance_uuidv4 FROM sources WHERE source_registration_uuidv4=?",
                (source,),
            ).fetchone()
            if row is not None:
                registered_services.add(row[0])
        for source in required.sources:
            row = self.db.execute(
                "SELECT service_instance_uuidv4 FROM sources WHERE source_registration_uuidv4=?",
                (source,),
            ).fetchone()
            if row is None:
                if source in registered_sources and not creating:
                    raise AdmissionRefused("MISSING_DEPENDENCY")
                # Authority was checked above. Missing original-origin records
                # stay unresolved; this never creates or qualifies a Source.
                continue
            services = {
                resource.service_instance_uuidv4 for resource in required.resources
            }
            if (
                source not in registered_sources
                and registered_services
                and row[0] not in registered_services
            ):
                raise AdmissionRefused("UNQUALIFIED_MAPPING")
            if services and row[0] not in services:
                raise AdmissionRefused("UNQUALIFIED_MAPPING")
        if creating:
            # New positive pairs are created by the owning typed operation.
            # Existing Source origins were still qualified above; creation is
            # never an exemption from their permanent service identity.
            return
        for source, repository in required.source_repository_pairs:
            if (
                self.db.execute(
                    "SELECT 1 FROM source_repositories WHERE source_registration_uuidv4=? AND repository_uuidv4=?",
                    (source, repository),
                ).fetchone()
                is None
            ):
                raise AdmissionRefused("MISSING_DEPENDENCY")

    def _bounded_admission_rows(self, sql, parameters=()):
        """Charge each step and decoded row before accumulating finite results."""
        context = (
            self._current_admission
            or self._transaction_admission
            or self._current_admission_for_expansion
        )
        self._authorization.validate_context(context)
        cursor = self.db.execute(sql, parameters)
        rows = []
        try:
            while True:
                context.budget.charge(work=1)
                if context.budget.used_work > context.selection.max_work:
                    raise AdmissionRefused("INPUT_LIMIT")
                row = cursor.fetchone()
                if row is None:
                    return tuple(rows)
                context.budget.charge(dependencies=1)
                self._authorization.charge_input(context, tuple(row))
                if len(rows) >= context.selection.max_units:
                    raise AdmissionRefused("INPUT_LIMIT")
                rows.append(tuple(row))
        finally:
            cursor.close()

    def _authorize_dependencies(self, required):
        context = (
            self._current_admission
            or self._transaction_admission
            or self._current_admission_for_expansion
        )
        if self._admission_leases is None or context is None:
            raise AdmissionRefused("PERMISSION_DENIED")
        lease = self._admission_leases.enter_context(
            self._authorization.authorize(context, required)
        )
        self._admission_live_leases.append(lease)
        self._check_source_dependencies(required)
        return lease

    @contextmanager
    def _commit_scope(self, admission=None):
        if self._admission_leases is not None:
            raise AdmissionRefused("ADMISSION_TRANSACTION_REQUIRED")
        if admission is not None:
            if self._authorization is None:
                raise AdmissionRefused("PERMISSION_DENIED")
            self._authorization.validate_context(admission)
        with ExitStack() as leases:
            self._admission_leases = leases
            self._admission_live_leases = []
            self._transaction_admission = admission
            try:
                yield
            finally:
                self._transaction_admission = None
                self._admission_leases = None
                self._admission_live_leases = []

    def _precommit_admission(self):
        self._raise_failed_cleanup()
        for lease in self._admission_live_leases:
            lease.check_current()

    @contextmanager
    def _storage_gate(self):
        from pathlib import Path

        from repo_catalog.adapters.sqlite.catalog_runtime import catalog_gate
        from repo_catalog.adapters.sqlite.p1_schema import (
            expected_schema,
            schema_rows,
            verify_connection,
        )
        from repo_catalog.domain.resource_stage import (
            TRANSFER_FENCE_DEFINITIONS,
            UnsupportedTransferSchema,
            is_isolated_transfer_fixture,
        )

        with ExitStack() as gates:
            paths = self.db.execute("PRAGMA database_list").fetchall()
            if len(paths) != 1 or paths[0][1] != "main":
                raise UnsupportedTransferSchema()
            if paths[0][2]:
                gates.enter_context(
                    catalog_gate(Path(paths[0][2]).parent, exclusive=True)
                )
            verify_connection(self.db)
            actual, expected = schema_rows(self.db), expected_schema("context")
            if is_isolated_transfer_fixture(self.db):
                # Explicit disposable fixtures may add failure-injection triggers,
                # while every packaged non-fence object must remain exact.
                expected = tuple(
                    row for row in expected if row not in TRANSFER_FENCE_DEFINITIONS
                )
                extras = set(actual) - set(expected)
                valid = set(expected) <= set(actual) and all(
                    row[0] == "trigger" for row in extras
                )
            else:
                valid = actual == expected
            if not valid:
                raise UnsupportedTransferSchema()
            yield

    @contextmanager
    def admission_transaction(self, *, admission):
        """Own BEGIN through COMMIT and hold each current policy lease throughout.

        No caller-owned outer transaction is accepted. COMMIT failure, including
        deferred FK failure, explicitly rolls back pending database changes.
        """
        if self._authorization is None:
            raise AdmissionRefused("PERMISSION_DENIED")
        self._authorization.validate_context(admission)
        if admission.operation == "exchange_export":
            raise AdmissionRefused("PERMISSION_DENIED")
        if self.db.in_transaction:
            raise AdmissionRefused("ADMISSION_TRANSACTION_REQUIRED")
        with self._commit_scope(admission):
            self._authorize_dependencies(DependencySet())
            with self._storage_gate():
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    yield self
                    self._precommit_admission()
                    self.db.execute("COMMIT")
                except BaseException as error:
                    if self._admission_failed_cleanup is None:
                        try:
                            if self.db.in_transaction:
                                self.db.execute("ROLLBACK")
                        except BaseException as cleanup:
                            self._discard_failed_cleanup(error, cleanup)
                    raise

    # The raw Store has this alias. The facade defines its own catalog-gated
    # classmethod transaction, also keeping the same commit-owned lease scope.
    transaction = admission_transaction
