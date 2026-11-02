"""The selected Context boundary rejects callers before stored-data classifiers."""

from dataclasses import replace

import pytest

from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.query_contracts import QueryError
from tests.integration.p6.conftest import populate_rich_catalog


@pytest.mark.parametrize("reader", [ContextQueryService, ProductionQueryService])
@pytest.mark.parametrize(
    "invalid", ["wrong_type", "mutated_key", "include_text", "digest"]
)
def test_invalid_context_read_input_does_not_stop_authority(tmp_path, reader, invalid):
    data = populate_rich_catalog(tmp_path, include_core=False, include_context=True)
    key = data["pr_key"]
    service = reader(tmp_path, mode="context_only")
    bad = replace(key)

    def operation():
        if invalid == "wrong_type":
            return service.get_context_resource(object())
        if invalid == "mutated_key":
            object.__setattr__(bad, "provider_resource_id", "[")
            return service.get_context_resource(bad)
        if invalid == "include_text":
            return service.get_context_resource(key, include_text=object())
        return service.read_context_text(object())

    with pytest.raises(QueryError) as caught:
        operation()
    assert caught.value.code == "INVALID_INPUT"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    assert service.get_context_resource(key).resource == key
