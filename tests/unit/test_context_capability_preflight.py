"""Local facade lifetime refuses before authority or existence-bearing checks."""

from contextlib import ExitStack

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import AdmissionRefused, DependencySet
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.production_context import ContextError
from tests.support.context_admission import fixture_context, fixture_service

PROVIDER = "e19d36ab-3876-4c36-b998-183827af06ef"
RESOURCE = ResourceKey.from_native(PROVIDER, "issue", "7")


class NoStorage:
    """Any DB or Recovery Stop inspection is an unexpected disclosure attempt."""

    def __init__(self):
        self.lookups = 0

    def __getattr__(self, name):
        self.lookups += 1
        raise AssertionError(f"unexpected storage lookup: {name}")

    def __truediv__(self, name):
        self.lookups += 1
        raise AssertionError(f"unexpected Recovery Stop lookup: {name}")


def local_facade(service, *, active=True, writable=True):
    # Isolate the already-issued local capability state from the real factories,
    # which are exercised by the original transaction/snapshot integration tests.
    context = object.__new__(Context)
    storage = NoStorage()
    context.directory = storage
    context.db = storage
    context._active = active
    context._writable = writable
    context._authorization = service
    context._admission_owner = None
    context._transaction_admission = None
    context._admission_depth = 0
    context._admission_leases = ExitStack()
    context._admission_live_leases = []
    return context, storage


@pytest.mark.parametrize(
    "active,writable,code",
    [
        (False, True, "CAPABILITY_EXPIRED"),
        (False, False, "CAPABILITY_EXPIRED"),
        (True, False, "READ_ONLY"),
    ],
)
@pytest.mark.parametrize("invocation", ["missing", "issued", "foreign"])
@pytest.mark.parametrize("mutation", ["text", "resource"])
def test_unusable_facade_rejects_without_authority_or_storage(
    monkeypatch, active, writable, code, invocation, mutation
):
    service, policy = fixture_service(DependencySet(resources={RESOURCE}))
    foreign, foreign_policy = fixture_service(DependencySet(resources={RESOURCE}))
    issued = fixture_context(service)
    foreign_issued = fixture_context(foreign)
    admission = {"missing": None, "issued": issued, "foreign": foreign_issued}[
        invocation
    ]
    context, storage = local_facade(service, active=active, writable=writable)
    validations = []

    def forbidden_validation(admission):
        validations.append(admission)
        raise AssertionError("local capability refusal consulted authority")

    monkeypatch.setattr(service, "validate_context", forbidden_validation)
    with context._admission_leases:
        with pytest.raises(ContextError) as refused:
            getattr(context, mutation)(
                "synthetic text" if mutation == "text" else RESOURCE,
                admission=admission,
            )
    assert refused.value.code == code
    assert validations == []
    assert policy.calls == [] and foreign_policy.calls == []
    assert storage.lookups == 0
    assert issued.budget.used_work == foreign_issued.budget.used_work == 0


@pytest.mark.parametrize("invocation", ["missing", "foreign", "denied"])
def test_active_writable_facade_still_requires_authority_before_lookup(invocation):
    service, policy = fixture_service(DependencySet())
    foreign, foreign_policy = fixture_service(
        DependencySet(resources={RESOURCE}, provider_registrations={PROVIDER})
    )
    issued = fixture_context(service)
    foreign_issued = fixture_context(foreign)
    admission = {"missing": None, "foreign": foreign_issued, "denied": issued}[
        invocation
    ]
    context, storage = local_facade(service)
    with context._admission_leases:
        with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
            context.resource(RESOURCE, admission=admission)
    assert storage.lookups == 0
    assert len(policy.calls) == (1 if invocation == "denied" else 0)
    assert foreign_policy.calls == []
