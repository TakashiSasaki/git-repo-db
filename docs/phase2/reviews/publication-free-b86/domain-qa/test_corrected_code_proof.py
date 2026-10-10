"""Independent exact-code-proof arrival and target-context checks."""
import copy
import json

import pytest

from test_independent_domain_qa import PR, REPO, candidate, insert, new_store, oid, seed, store
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.application.catalog_validation import check_catalog


def code_unit(s):
    seed(s)
    head, base = oid("sha1", "commit", b"head"), oid("sha1", "commit", b"base")
    scope = candidate(100)["acquisition_scope"]
    scope["request_context"] = {"head": {"sha": head.hex()}, "base": {"sha": base.hex()}}
    for kind in ("commits", "files"):
        collection, listing = "qa-" + kind, "listing-" + kind
        insert(s, "fetch_collections", fetch_collection_id=collection, repository_uuidv4=REPO, change_request_id=PR, kind="pr-" + kind, observed_at_us=100, scope_json=json.dumps(scope))
        insert(s, "code_listings", code_listing_id=listing, change_request_id=PR, fetch_collection_id=collection, kind=kind, object_format="sha1", head_oid=head, base_oid=base)
        proof = CurrentCollectionProof(s.connection)
        proof.page(collection, 0, 100, None, [], parser_module="independent-qa", parser_version="1")
        insert(s, "completion_markers", fetch_collection_id=collection, asserted_state="complete", evidence=json.dumps(proof.evidence(collection)), observed_at_us=100)
        insert(s, "code_listing_progress", code_listing_id=listing, state="complete", terminal=1, page_count=1, context_proven=1)
    insert(s, "code_assessments", code_assessment_id="qa-complete-code", change_request_id=PR, repository_uuidv4=REPO, commit_code_listing_id="listing-commits", file_code_listing_id="listing-files", state="complete", object_format="sha1", head_oid=head, base_oid=base, observed_at_us=100, parser_module="qa", parser_version="1", details_json="{}")
    return Graph(s.connection).export(REPO)


@pytest.mark.parametrize("mismatch", ["kind", "head", "base"])
def test_wrong_listing_capture_cannot_complete_assessment(store, tmp_path, mismatch):
    unit = copy.deepcopy(code_unit(store))
    collection = next(r for r in unit["records"] if r["table"] == "fetch_collections" and r["values"]["kind"] == "pr-commits")
    if mismatch == "kind":
        collection["values"]["kind"] = "pr-files"
    else:
        scope = json.loads(collection["values"]["scope_json"])
        scope["request_context"][mismatch]["sha"] = oid("sha1", "commit", b"different target").hex()
        collection["values"]["scope_json"] = json.dumps(scope)
    with new_store(tmp_path / "receiver") as target:
        result = Graph(target.connection).receive(unit)
        assert result["staged_records"] > 0
        assert not target.one("SELECT 1 FROM code_assessments WHERE state='complete'")
        assert target.one("SELECT state,context_proven FROM code_listing_progress WHERE code_listing_id='listing-commits'")[0] == "partial"
        assert target.one("SELECT context_proven FROM code_listing_progress WHERE code_listing_id='listing-commits'")[0] == 0


def test_complete_code_assessment_waits_for_late_actual_terminal_proof(store, tmp_path):
    unit = code_unit(store)
    late_tables = {"current_collection_pages", "completion_markers"}
    initial = {**unit, "records": [r for r in unit["records"] if r["table"] not in late_tables]}
    late = {**unit, "records": [r for r in unit["records"] if r["table"] in late_tables]}
    with new_store(tmp_path / "receiver") as target:
        first = Graph(target.connection).receive(initial)
        assert first["staged_records"] > 0
        assert not target.one("SELECT 1 FROM code_assessments")
        assert not target.one("SELECT 1 FROM code_listing_progress WHERE state='complete'")
        onward = Graph(target.connection).export(REPO)
        assert any(r["table"] == "code_assessments" for r in onward["records"])
        late["records"].reverse()
        outcome = Graph(target.connection).receive(late)
        assert outcome["staged_records"] == 0
        assert target.one("SELECT count(*) FROM code_listing_progress WHERE state='complete'")[0] == 2
        assert target.one("SELECT state FROM code_assessments")[0] == "complete"
        assert Graph(target.connection).receive(unit)["staged_records"] == 0
        assert check_catalog(target, full=True) == []
