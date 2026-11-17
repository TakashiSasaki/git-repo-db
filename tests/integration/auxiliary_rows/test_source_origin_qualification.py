"""Creating Source evidence cannot bypass a present origin's service identity."""

from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import AdmissionRefused, DependencySet
from repo_catalog.domain.shared_values import encode
from tests.integration.auxiliary_rows.test_source_inventory_history import prepare


@pytest.mark.parametrize("method", ["inventory", "admit_inventory_history"])
@pytest.mark.parametrize("provider_member", [False, True])
def test_existing_foreign_source_origin_refuses_before_any_inventory_or_pair(
    tmp_path, method, provider_member
):
    old, _, authorization, admission, policy = prepare(tmp_path)
    foreign_source, foreign_service = str(uuid4()), str(uuid4())
    policy.grants |= DependencySet(
        sources={foreign_source}, provider_registrations={foreign_service}
    )
    observation = replace(
        old,
        state="partial",
        provenance_json=encode(
            {
                "source": "registered foreign origin",
                "evidence": "original report",
                "source_registration_uuidv4": foreign_source,
            }
        ),
        provider_repositories=old.provider_repositories if provider_member else (),
    )
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        context.provider(foreign_service, "synthetic")
        context.source(foreign_source, foreign_service)
        with pytest.raises(AdmissionRefused) as error:
            getattr(context, method)(observation)
        assert error.value.code == "UNQUALIFIED_MAPPING"
        assert (
            context.db.execute(
                "SELECT count(*) FROM source_inventory_evidence"
            ).fetchone()[0]
            == 0
        )
        assert (
            context.db.execute("SELECT count(*) FROM source_repositories").fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("method", ["inventory", "admit_inventory_history"])
def test_missing_detached_source_origin_remains_authorized_original_without_registration(
    tmp_path, method
):
    old, _, authorization, admission, policy = prepare(tmp_path)
    detached = str(uuid4())
    policy.grants |= DependencySet(sources={detached})
    provenance = encode(
        {
            "source": "detached original",
            "evidence": "original report",
            "source_registration_uuidv4": detached,
        }
    )
    observation = replace(old, provenance_json=provenance)
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        getattr(context, method)(observation)
        assert (
            context.db.execute(
                "SELECT provenance_json FROM source_inventory_evidence"
            ).fetchone()[0]
            == provenance
        )
        assert (
            context.db.execute(
                "SELECT 1 FROM sources WHERE source_registration_uuidv4=?", (detached,)
            ).fetchone()
            is None
        )


@pytest.mark.parametrize("method", ["inventory", "admit_inventory_history"])
def test_both_source_coordinates_still_require_current_authority(tmp_path, method):
    old, _, authorization, admission, policy = prepare(tmp_path)
    detached = str(uuid4())
    # A missing origin stays unresolved only after its independent actor grant.
    observation = replace(
        old,
        provenance_json=encode(
            {
                "source": "detached original",
                "evidence": "original report",
                "source_registration_uuidv4": detached,
            }
        ),
    )
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        with pytest.raises(AdmissionRefused) as error:
            getattr(context, method)(observation)
        assert error.value.code == "PERMISSION_DENIED"
        assert (
            context.db.execute(
                "SELECT count(*) FROM source_inventory_evidence"
            ).fetchone()[0]
            == 0
        )
