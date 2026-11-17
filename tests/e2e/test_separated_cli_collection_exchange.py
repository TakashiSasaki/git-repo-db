"""Collection-rooted imports retain explicit finite local authority targets."""

from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import AdmissionSelection
from tests.e2e.test_separated_cli import document, run
from tests.integration.p5.conftest import init_catalog_stores
from tests.integration.p5.test_selected_collection_exchange import setup


@pytest.mark.parametrize("denied", [None, "member-grant", "local-selection"])
def test_normal_cli_collection_import_keeps_local_selection_separate_from_packet_roots(
    tmp_path, capsys, denied
):
    fixture, selection, key = setup(tmp_path / "sender")
    scope = document(tmp_path, "scope.json", selection)
    packet = tmp_path / "packet.json"
    run(
        capsys,
        "exchange",
        "export",
        "--catalog",
        fixture.path,
        "--selection",
        scope,
        "--output",
        packet,
    )
    target = tmp_path / "receiver"
    init_catalog_stores(
        target, repository_uuidv4=fixture.repository, stores=("context", "operational")
    )
    grants = fixture.grants
    selected = AdmissionSelection(
        resource_keys=tuple(grants.resources),
        source_uuidv4s=tuple(grants.sources),
        repository_uuidv4s=tuple(grants.repositories),
        object_oids=tuple(grants.object_oids),
    )
    if denied == "member-grant":
        grants = replace(grants, resources=grants.resources - {fixture.files[0]})
    if denied == "local-selection":
        selected = AdmissionSelection(
            resource_keys=(fixture.parent,),
            repository_uuidv4s=(),
            source_uuidv4s=tuple(grants.sources),
            object_oids=tuple(grants.object_oids),
        )
    auth = document(
        tmp_path, "authority.json", {"grants": grants, "selection": selected}
    )
    result = run(
        capsys,
        "exchange",
        "import",
        "--catalog",
        target,
        "--selection",
        scope,
        "--authority",
        auth,
        "--input",
        packet,
        "--new-request",
        expected=2 if denied else 0,
    )
    with Context.snapshot(target) as context:
        count = context.db.execute("SELECT count(*) FROM resources").fetchone()[0]
        if denied:
            assert result["code"] in (
                "PERMISSION_DENIED",
                "OMITTED_BY_SELECTION",
                "MISSING_DEPENDENCY",
            )
            assert count == 0
        else:
            assert count == 3
            assert (
                context.db.execute(
                    "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                    fixture.reviews[0].coordinates(),
                ).fetchone()
                is None
            )
    if not denied:
        replay = run(
            capsys,
            "exchange",
            "import",
            "--catalog",
            target,
            "--selection",
            scope,
            "--authority",
            auth,
            "--input",
            packet,
        )
        assert replay["idempotent_replay"]
        provenance = document(tmp_path, "original.json", key[4])
        captured = run(
            capsys,
            "query",
            "pr-code-capture",
            "--catalog",
            target,
            "--service-instance",
            fixture.service,
            "--provider-resource-id",
            fixture.parent.provider_resource_id,
            "--kind",
            "pr_files",
            "--provenance-file",
            provenance,
        )
        assert captured["state"] == "complete" and captured["total_count"] == 2
        assert captured["coverage"]["current_provider_state_asserted"] is False
