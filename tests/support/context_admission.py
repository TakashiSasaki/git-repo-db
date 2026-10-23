"""Explicit finite local authority for synthetic Context admission tests."""

from contextlib import contextmanager
from threading import RLock

from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionRefused,
    AdmissionSelection,
    ContextAdmissionService,
    DependencySet,
)


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
