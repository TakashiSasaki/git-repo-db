"""Reader contracts over selected profiles, immutable fact DAGs and local damage."""

import json
import uuid
from dataclasses import dataclass

import pytest

from repo_catalog.adapters.sqlite.cas_integrity import diagnose_corruption
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.adapters.sqlite.text_bodies import intern_text_body
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.application.target_queries import TargetQueryService
from repo_catalog.domain.models import CatalogError


def uid():
    return str(uuid.uuid4())


@dataclass
class Catalog:
    state: object
    store: Store
    model: ParserModel
    repository: str
    request: str
    profile: str
    verification: str

    def documents(self, **options):
        return QueryService(self.state).query(
            "pr documents", {"repo": self.repository, **options}
        )

    def profile_definition(self, label):
        definition = {
            "implementation": {"synthetic_test_parser": label},
            "settings": {},
            "output_schema": {"test_contract": 1},
            "capabilities": [
                {"owner_kind": "repository", "fact_kind": kind}
                for kind in ("change-request", "issue-comment")
            ],
        }
        profile = self.model.register_profile(definition)
        verification = self.model.verify_profile(
            profile,
            criteria={"test": "independent reader fixture"},
            evidence={
                "definition": definition,
                "capabilities": [
                    {**capability, "outcome": "passed", "checks": ["fixture"]}
                    for capability in definition["capabilities"]
                ],
            },
        )
        self.model.trust_verification(verification)
        return profile, verification

    def observe(self, body, *, profile=None, document="1", select=True, timestamp=0):
        profile = profile or self.profile
        fetch_uuid = uid()
        payload = intern_payload(self.store.connection, body.encode())
        fetch_id = self.store.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,observed_at_us,parsed_at_us) VALUES(?,?,?,0,?,?,'{}',?,0)",
            (
                fetch_uuid,
                self.repository,
                "collection",
                *payload.parameters(),
                timestamp,
            ),
        ).lastrowid
        result = self.model.create_result(
            profile,
            repository_uuidv4=self.repository,
            inputs=[{"fetch_occurrence_uuidv4": fetch_uuid}],
            parsed_at_us=timestamp,
        )
        self.store.execute(
            "INSERT INTO change_request_observations(change_request_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,observed_at_us,published,payload,parsed_at_us,origin_fetch_occurrence_id) VALUES(?,?,?,?,?,1,?,0,?)",
            (
                uid(),
                result,
                self.repository,
                self.request,
                timestamp,
                json.dumps({"title": body, "state": "open", "user": {"login": body}}),
                fetch_id,
            ),
        )
        if not self.store.one(
            "SELECT 1 FROM documents WHERE change_request_id=? AND kind='issue-comment' AND provider_change_request_document_id=?",
            (self.request, document),
        ):
            self.store.execute(
                "INSERT INTO documents VALUES(?,'issue-comment',?)",
                (self.request, document),
            )
        digest = intern_text_body(self.store.connection, body)
        observation = self.store.execute(
            "INSERT INTO document_observations(document_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at_us,parsed_at_us,fetch_occurrence_id,metadata,author,url) VALUES(?,?,?,?,'issue-comment',?,?,?,0,?,?,?,?)",
            (
                uid(),
                result,
                self.repository,
                self.request,
                document,
                digest,
                timestamp,
                fetch_id,
                json.dumps({"user": {"login": body}, "body": body}),
                body,
                "https://synthetic.invalid/" + body,
            ),
        ).lastrowid
        self.model.publish_result(result)
        decisions = []
        if select:
            decisions.append(
                self.model.select_fact(
                    result, fact_kind="change-request", change_request_id=self.request
                )
            )
            decisions.append(self.choose(result, document=document))
        return {
            "result": result,
            "observation": observation,
            "digest": payload.sha256,
            "decisions": decisions,
        }

    def choose(self, result, *, document="1", **options):
        return self.model.select_fact(
            result,
            fact_kind="issue-comment",
            change_request_id=self.request,
            kind="issue-comment",
            provider_change_request_document_id=document,
            **options,
        )


@pytest.fixture
def catalog(tmp_path):
    state = tmp_path / "catalog"
    MaintenanceService(state).init("catalog-text-v1", 32 * 1024 * 1024, 0)
    with Store(state) as store:
        model = ParserModel(store.connection)
        repo, request = uid(), uid()
        fixture = Catalog(state, store, model, repo, request, "", "")
        with store.transaction():
            service = add_instance(store, "github", "reader-test")
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'reader/test','{}')",
                (repo,),
            )
            bind(store, repo, service, "1")
            binding = store.one(
                "SELECT repository_binding_id FROM repository_bindings WHERE repository_uuidv4=?",
                (repo,),
            )[0]
            store.execute(
                "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)",
                (request, repo, binding),
            )
            store.execute(
                "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,request_context,parser_version,profile_version,confidence) VALUES('scope',?,'{}','test','test','proven')",
                (repo,),
            )
            store.execute(
                "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,resume_scope_id) VALUES('collection',?,?,'issue-comment','scope')",
                (repo, request),
            )
            fixture.profile, fixture.verification = fixture.profile_definition("first")
            for kind in ("change-request", "issue-comment"):
                model.select_profile(
                    fixture.profile,
                    fixture.verification,
                    repository_uuidv4=repo,
                    fact_kind=kind,
                )
        yield fixture
        assert not store.all("PRAGMA foreign_key_check")
        assert store.one("PRAGMA integrity_check")[0] == "ok"


def test_normal_reads_use_selected_profile_and_history_is_explicit(catalog):
    with catalog.store.transaction():
        catalog.observe("chosen")
        other, _ = catalog.profile_definition("second")
        catalog.observe("other-parser", profile=other, select=False, timestamp=2**60)
    current = catalog.documents().data["items"]
    assert [row["body"] for row in current] == ["chosen"]
    assert current[0]["author"] == "chosen"
    assert current[0]["document_url"].endswith("/chosen")
    history = catalog.documents(document_observations="all").data["items"]
    assert {row["body"] for row in history} == {"chosen", "other-parser"}
    assert {row["parser_profile_uuidv4"] for row in history} == {catalog.profile, other}
    assert [
        row["body"]
        for row in catalog.documents(
            document_observations="all", parser_profile=other
        ).data["items"]
    ] == ["other-parser"]


def test_no_selection_does_not_use_largest_observation_or_timestamp(catalog):
    with catalog.store.transaction():
        catalog.observe("unselected", select=False, timestamp=2**60)
    result = catalog.documents()
    assert result.data["items"] == []
    assert result.status == "partial"
    shown = QueryService(catalog.state).query("pr show", {"repo": catalog.repository})
    assert shown.data["items"][0]["payload"] == {}
    assert shown.data["items"][0]["current_selected"] is False


def test_fact_conflict_is_partial_until_explicit_multi_predecessor_resolution(catalog):
    with catalog.store.transaction():
        first = catalog.observe("first")
        second = catalog.observe("second", select=False, timestamp=-1)
        branch = catalog.choose(second["result"], predecessors=[])
    assert catalog.documents().data["items"] == []
    assert catalog.documents().status == "partial"
    with catalog.store.transaction():
        catalog.choose(second["result"], predecessors=[first["decisions"][1], branch])
    assert [row["body"] for row in catalog.documents().data["items"]] == ["second"]


def test_conflicting_cr_profile_blocks_repository_inheritance(catalog):
    with catalog.store.transaction():
        first = catalog.observe("first")
        other, verification = catalog.profile_definition("second")
        second = catalog.observe("second", profile=other, select=False)
        args = {
            "repository_uuidv4": catalog.repository,
            "change_request_id": catalog.request,
            "fact_kind": "issue-comment",
            "predecessors": [],
        }
        a = catalog.model.select_profile(catalog.profile, catalog.verification, **args)
        b = catalog.model.select_profile(other, verification, **args)
    assert catalog.documents().data["items"] == []
    assert catalog.documents().status == "partial"
    with catalog.store.transaction():
        catalog.model.select_profile(
            other, verification, **{**args, "predecessors": [a, b]}
        )
    # Explicit profile selection still cannot choose an incompatible old result.
    assert catalog.documents().data["items"] == []
    with catalog.store.transaction():
        catalog.choose(second["result"], predecessors=[first["decisions"][1]])
    assert [row["body"] for row in catalog.documents().data["items"]] == ["second"]


def test_staged_individual_selection_blocks_parent_until_dependency_arrives(catalog):
    with catalog.store.transaction():
        catalog.observe("first")
        local = catalog.model.select_profile(
            catalog.profile,
            catalog.verification,
            repository_uuidv4=catalog.repository,
            change_request_id=catalog.request,
            fact_kind="issue-comment",
        )
        record = dict(
            catalog.store.one(
                "SELECT * FROM parser_profile_selection_decisions WHERE selection_decision_uuidv4=?",
                (local,),
            )
        )
        predecessor = {
            **record,
            "selection_decision_uuidv4": uid(),
            "predecessor_manifest_json": json.dumps([local]),
        }
        later = {
            **record,
            "selection_decision_uuidv4": uid(),
            "predecessor_manifest_json": json.dumps(
                [predecessor["selection_decision_uuidv4"]]
            ),
        }
        assert catalog.model.receive_profile_decision(later) == "staged"
    assert catalog.documents().data["items"] == []
    with catalog.store.transaction():
        assert catalog.model.receive_profile_decision(predecessor) == "admitted"
        catalog.model.promote_staging()
    assert [row["body"] for row in catalog.documents().data["items"]] == ["first"]
    assert (
        catalog.store.one("SELECT count(*) FROM parser_profile_selection_staging")[0]
        == 0
    )


@pytest.mark.parametrize("invalidate", [False, True])
def test_untrusted_or_invalidated_verification_does_not_expose_current(
    catalog, invalidate
):
    with catalog.store.transaction():
        catalog.observe("first")
        if invalidate:
            catalog.model.invalidate_verification(
                catalog.verification, "synthetic verifier defect"
            )
        else:
            catalog.model.trust_verification(catalog.verification, False)
    assert catalog.documents().data["items"] == []
    assert catalog.documents().status == "partial"
    assert [
        row["body"]
        for row in catalog.documents(document_observations="all").data["items"]
    ] == ["first"]


def test_trust_change_invalidates_query_cursor(catalog):
    with catalog.store.transaction():
        catalog.observe("first", document="1")
        catalog.observe("second", document="2")
    query = QueryService(catalog.state)
    first = query.query("pr documents", {"repo": catalog.repository}, limit=1)
    cursor = first.data["page"]["next_cursor"]
    assert cursor
    with catalog.store.transaction():
        catalog.model.trust_verification(catalog.verification, False)
    with pytest.raises(CatalogError) as error:
        query.query(
            "pr documents", {"repo": catalog.repository}, limit=1, cursor=cursor
        )
    assert error.value.code == "STALE_CURSOR"


def test_quarantine_hides_only_dependent_results_and_invalidates_cursor(catalog):
    with catalog.store.transaction():
        damaged = catalog.observe("first", document="1")
        catalog.observe("second", document="2")
    query = QueryService(catalog.state)
    page = query.query("pr documents", {"repo": catalog.repository}, limit=1)
    # Deliberately emulate disk damage while restoring the production trigger.
    trigger = catalog.store.one(
        "SELECT sql FROM sqlite_schema WHERE type='trigger' AND name='stored_bytes_immutable'"
    )[0]
    with catalog.store.transaction():
        catalog.store.execute("DROP TRIGGER stored_bytes_immutable")
        catalog.store.execute(
            "UPDATE stored_bytes SET body=? WHERE sha256=?",
            (b"xxxxx", damaged["digest"]),
        )
        catalog.store.execute(trigger)
        diagnose_corruption(catalog.store.connection, damaged["digest"])
    result = catalog.documents()
    assert [row["body"] for row in result.data["items"]] == ["second"]
    assert result.status == "partial"
    assert [
        row["body"]
        for row in catalog.documents(document_observations="all").data["items"]
    ] == ["second"]
    with pytest.raises(CatalogError) as error:
        query.query(
            "pr documents",
            {"repo": catalog.repository},
            limit=1,
            cursor=page.data["page"]["next_cursor"],
        )
    assert error.value.code == "STALE_CURSOR"


def test_target_diagnostics_require_explicit_history_for_other_profiles(catalog):
    with catalog.store.transaction():
        catalog.observe("first")
        other, _ = catalog.profile_definition("other")
        catalog.observe("second", profile=other, select=False)
    query = TargetQueryService(catalog.state / "catalog.sqlite3")
    options = {"repo": catalog.repository, "provider_change_request_number": 1}
    normal = query.query("pr", options).data["items"]
    assert [
        row["body"] for row in normal if row["record_kind"] == "document_observation"
    ] == ["first"]
    history = query.query("pr", {**options, "observations": "all"}).data["items"]
    assert {
        row["body"] for row in history if row["record_kind"] == "document_observation"
    } == {"first", "second"}


def test_new_verification_never_silently_replaces_selected_evidence(catalog):
    with catalog.store.transaction():
        catalog.observe("first")
        catalog.model.invalidate_verification(
            catalog.verification, "superseded verifier"
        )
        definition = json.loads(
            catalog.store.one(
                "SELECT definition_json FROM parser_profiles WHERE parser_profile_uuidv4=?",
                (catalog.profile,),
            )[0]
        )
        verification = catalog.model.verify_profile(
            catalog.profile,
            criteria={"test": "new independent verification"},
            evidence={
                "definition": definition,
                "capabilities": [
                    {**capability, "outcome": "passed", "checks": ["fixture"]}
                    for capability in definition["capabilities"]
                ],
            },
        )
        catalog.model.trust_verification(verification)
    assert catalog.documents().data["items"] == []
    with catalog.store.transaction():
        catalog.model.select_profile(
            catalog.profile,
            verification,
            repository_uuidv4=catalog.repository,
            fact_kind="issue-comment",
        )
    assert [row["body"] for row in catalog.documents().data["items"]] == ["first"]


def test_fts_cannot_bypass_profile_or_trust_selection(catalog):
    from repo_catalog.adapters.sqlite.index import rebuild

    with catalog.store.transaction():
        catalog.observe("needle selected")
        other, _ = catalog.profile_definition("other")
        catalog.observe("needle unselected", profile=other, select=False)
    rebuild(catalog.store, "pr")
    query = QueryService(catalog.state)
    options = {"repo": catalog.repository, "literal": "needle"}
    normal = query.query("search pr", options)
    assert [row["body"] for row in normal.data["items"]] == ["needle selected"]
    history = query.query("search pr", {**options, "document_observations": "all"})
    assert {row["body"] for row in history.data["items"]} == {
        "needle selected",
        "needle unselected",
    }
    with catalog.store.transaction():
        catalog.model.trust_verification(catalog.verification, False)
    assert query.query("search pr", options).data["items"] == []


def test_cli_history_and_profile_filters_are_explicit(catalog):
    from tests.support.cli import run

    with catalog.store.transaction():
        catalog.observe("first")
        other, _ = catalog.profile_definition("other")
        catalog.observe("second", profile=other, select=False)
    filtered = run(
        catalog.state,
        "pr",
        "documents",
        "--repo",
        catalog.repository,
        "--provider-change-request-number",
        1,
        "--document-observations",
        "all",
        "--parser-profile",
        other,
        expected=3,
    )
    assert [row["body"] for row in filtered["data"]["items"]] == ["second"]
    diagnostic = run(
        catalog.state,
        "target",
        "--database",
        catalog.state / "catalog.sqlite3",
        "pr",
        "--repo",
        catalog.repository,
        "--provider-change-request-number",
        1,
        "--observations",
        "all",
        expected=3,
    )
    assert {
        row["body"]
        for row in diagnostic["data"]["items"]
        if row["record_kind"] == "document_observation"
    } == {"first", "second"}
