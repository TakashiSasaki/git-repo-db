"""Narrow local read/export authority from an explicit finite grant document.

No package or stored row can enlarge these grants. This capability cannot admit
Context mutations; the existing Context adapter rejects export contexts there.
"""

from contextlib import contextmanager
from threading import RLock
from uuid import uuid4


def create_identity_export_authority(*, grants, selection, budget=None):
    from repo_catalog.domain.context_admission import (
        AdmissionBudget,
        AdmissionRefused,
        AdmissionSelection,
        AuthenticatedPrincipal,
        ContextAdmissionService,
        DependencySet,
    )

    if type(grants) is not DependencySet or type(selection) is not AdmissionSelection:
        raise AdmissionRefused("PERMISSION_DENIED")
    budget = budget if budget is not None else AdmissionBudget()
    if type(budget) is not AdmissionBudget:
        raise AdmissionRefused("INPUT_LIMIT")
    exact = DependencySet(
        provider_registrations=grants.provider_registrations,
        identity_assertions=grants.identity_assertions,
    )
    principal = AuthenticatedPrincipal("local-identity-export", str(uuid4()))
    credential = object()

    class Policy:
        def __init__(self):
            self.grants = exact
            self._lock, self._revoked = RLock(), False

        def revoke(self):
            with self._lock:
                self._revoked = True

        @contextmanager
        def lease(self, subject, operation, dependencies):
            with self._lock:
                if (
                    self._revoked
                    or subject != principal
                    or operation != "exchange_export"
                    or type(dependencies) is not DependencySet
                    or not dependencies.issubset(exact)
                ):
                    raise AdmissionRefused("PERMISSION_DENIED")
                policy = self

                class Lease:
                    def check_current(self):
                        if policy._revoked:
                            raise AdmissionRefused("PERMISSION_DENIED")

                yield Lease()

    def authenticate(supplied):
        if supplied is not credential:
            raise AdmissionRefused("PERMISSION_DENIED")
        return principal

    policy = Policy()
    service = ContextAdmissionService(policy, authenticate)
    admission = service.context(credential, "exchange_export", selection, budget)
    return service, admission, policy
