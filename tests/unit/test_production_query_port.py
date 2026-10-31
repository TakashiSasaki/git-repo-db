"""Public Query port remains importable and resolves its current Ref contract."""

import importlib
import inspect
from typing import get_type_hints


def test_production_query_port_import_and_ref_contract():
    port = importlib.import_module(
        "repo_catalog.domain.ports.production_query"
    ).ProductionQueryPort
    for name, method in vars(port).items():
        if not name.startswith("_") and inspect.isfunction(method):
            assert get_type_hints(method), name
    for name in (
        "get_ref_observation",
        "list_ref_observations",
        "get_ref_enumeration",
        "get_notes_mapping",
        "list_ref_notes_inventories",
        "read_ref_note_bytes",
    ):
        assert callable(getattr(port, name))
    for name in (
        "list_notes_captures",
        "get_notes_target",
        "list_notes_inventories",
        "read_note_bytes",
    ):
        assert not hasattr(port, name)
    assert "note_captures" not in inspect.signature(port.get_git_object).parameters
    for name in ("list_ref_observations", "rebuild_search"):
        inspect.signature(getattr(port, name)).bind(None, work=None)
    inspect.signature(port.search).bind(None, object(), work=None)


def test_core_query_port_excludes_optional_query_capabilities():
    """The independently installed Core port has complete, resolvable contracts."""
    port = importlib.import_module("repo_catalog.domain.ports.core_query").CoreQueryPort
    for name, method in vars(port).items():
        if not name.startswith("_") and inspect.isfunction(method):
            assert get_type_hints(method), name
    for name in (
        "get_repository_view",
        "get_git_object",
        "read_metadata_bytes",
        "get_ref_observation",
        "list_ref_notes_inventories",
        "read_ref_note_bytes",
    ):
        assert callable(getattr(port, name))
    for name in (
        "search",
        "rebuild_search",
        "list_providers",
        "get_context_resource",
        "get_paired_resource",
    ):
        assert not hasattr(port, name)
