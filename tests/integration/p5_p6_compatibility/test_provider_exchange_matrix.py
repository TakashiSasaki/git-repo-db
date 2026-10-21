import inspect
import json
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import ProviderAcquisition
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.acquisition import (
    ProviderIntakeBatch,
    ProviderIssueIntake,
    ProviderRegistration,
    make_provenance,
)
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.p1_context import ResourceKey
from tests.integration.p5.conftest import init_catalog_stores


def do_import(service, pkg):
    kwargs = (
        {"new_request": True}
        if "new_request" in inspect.signature(service.import_package).parameters
        else {}
    )
    return service.import_package(pkg, **kwargs)


def field_rows(cat):
    with Context.snapshot(cat) as ctx:
        return ctx.db.execute(
            "SELECT service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_domain,source_clock_us,provenance_json,observed_at_us FROM field_candidates ORDER BY 1,2,3,4,5,6,7,8,9"
        ).fetchall()


@pytest.mark.parametrize(
    "order", [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]
)
def test_provider_late_reordered_repeat_reverse_onward_preserves_candidates(
    tmp_path, order
):
    repo = str(uuid4())
    svc = str(uuid4())
    cats = [tmp_path / name for name in ("a", "b", "c")]
    for cat in cats:
        init_catalog_stores(
            cat, repository_uuidv4=repo, stores=("context", "operational")
        )
    snapshots = [
        {"id": 1, "title": "new", "state": "open", "updated_at": 20},
        {"id": 1, "title": "old", "body": "retained", "updated_at": 10},
        {"id": 1, "body": None},
    ]
    for n in order:
        ProviderAcquisition(cats[0]).admit_batch(
            ProviderIntakeBatch(
                svc,
                providers=(ProviderRegistration(svc, "github"),),
                issues=(
                    ProviderIssueIntake(
                        snapshots[n],
                        100 + n,
                        make_provenance("synthetic", ["observation", n]),
                    ),
                ),
            )
        )
    with Context.snapshot(cats[0]) as ctx:
        rk = ResourceKey.from_native(svc, "issue", "1")
        title = ctx.candidates(rk, "title")
        body = ctx.candidates(rk, "text_body_sha256")
        assert [json.loads(c.value_json) for c in title] == ["new"]
        assert len(body) == 2 and any(c.value_json == "null" for c in body)
    expected = field_rows(cats[0])
    a, b, c = map(ExchangeService, cats)
    pa = a.export_package(
        selection=ExchangeSelectionScope(all_selected=True), exported_at_us=200
    )
    do_import(b, pa)
    do_import(b, pa)
    assert field_rows(cats[1]) == expected
    pb = b.export_package(
        selection=ExchangeSelectionScope(all_selected=True), exported_at_us=201
    )
    do_import(a, pb)
    do_import(c, pb)
    assert field_rows(cats[0]) == expected == field_rows(cats[2])


def test_exchange_preserves_non_time_json_real(tmp_path):
    from repo_catalog.domain.p1_context import FieldCandidate, FieldClock
    from repo_catalog.domain.production_context import ResourceObservation

    repo = str(uuid4())
    svc = str(uuid4())
    rk = ResourceKey.from_native(svc, "issue", "2")
    a, b = tmp_path / "a", tmp_path / "b"
    for cat in (a, b):
        init_catalog_stores(
            cat, repository_uuidv4=repo, stores=("context", "operational")
        )
    ProviderAcquisition(a).admit_batch(
        ProviderIntakeBatch(
            svc,
            providers=(ProviderRegistration(svc, "github"),),
            observations=(
                ResourceObservation(
                    rk,
                    (
                        FieldCandidate(
                            rk,
                            "score",
                            "1.5",
                            FieldClock("source:updated_at", None),
                            make_provenance("synthetic", "fractional measurement"),
                            1,
                        ),
                    ),
                ),
            ),
        )
    )
    p = ExchangeService(a).export_package(
        selection=ExchangeSelectionScope(all_selected=True), exported_at_us=1
    )
    do_import(ExchangeService(b), p)
    assert field_rows(a) == field_rows(b)
