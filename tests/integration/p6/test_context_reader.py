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


@pytest.mark.parametrize("reader", [ContextQueryService, ProductionQueryService])
@pytest.mark.parametrize("field", ["identifier_namespace", "parent"])
def test_list_rebuilds_key_fields_without_instance_coordinates(tmp_path, reader, field):
    data = populate_rich_catalog(tmp_path, include_core=False, include_context=True)
    key = replace(data["pr_key"])
    original = key.coordinates()
    object.__setattr__(key, "coordinates", lambda: original)
    object.__setattr__(key, "provider_resource_id", "[")
    service = reader(tmp_path, mode="context_only")
    with pytest.raises(QueryError) as caught:
        service.list_context_resources(**{field: key})
    assert caught.value.code == "INVALID_INPUT"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    assert service.list_context_resources().total_count > 0


@pytest.mark.parametrize("reader", [ContextQueryService, ProductionQueryService])
def test_list_caller_cursor_rejected_before_opening_damaged_authority(tmp_path, reader):
    from repo_catalog.domain.query_contracts import PageRequest

    tmp_path.mkdir(exist_ok=True)
    damaged = tmp_path / "context.sqlite3"
    damaged.write_bytes(b"not sqlite")
    service = reader(tmp_path, mode="context_only")
    with pytest.raises(QueryError) as caught:
        service.list_context_resources(PageRequest(cursor="invalid"))
    assert caught.value.code == "INVALID_CURSOR"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    assert damaged.read_bytes() == b"not sqlite"


@pytest.mark.parametrize("reader", [ContextQueryService, ProductionQueryService])
@pytest.mark.parametrize(
    "field",
    ["service_instance_uuidv4", "repository_uuidv4", "cursor", "expected_token"],
)
def test_list_rejects_string_subclasses_outside_corruption_boundary(
    tmp_path, reader, field
):
    import json

    from repo_catalog.domain.query_contracts import PageRequest

    class HostileString(str):
        def __eq__(self, other):
            raise json.JSONDecodeError("caller comparison", "", 0)

        def __ne__(self, other):
            raise json.JSONDecodeError("caller comparison", "", 0)

    data = populate_rich_catalog(tmp_path, include_core=False, include_context=True)
    service = reader(tmp_path, mode="context_only")
    if field in {"cursor", "expected_token"}:
        page = PageRequest()
        object.__setattr__(
            page, field, HostileString(service.snapshot_token().encode())
        )

        def operation():
            return service.list_context_resources(page)

        expected = "INVALID_CURSOR" if field == "cursor" else "INVALID_TOKEN"
    else:

        def operation():
            return service.list_context_resources(
                **{field: HostileString(data["pr_key"].service_instance_uuidv4)}
            )

        expected = "INVALID_INPUT"
    with pytest.raises(QueryError) as caught:
        operation()
    assert caught.value.code == expected
    assert not (tmp_path / "p1-recovery-stop.json").exists()
