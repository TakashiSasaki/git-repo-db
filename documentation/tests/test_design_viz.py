"""Design projection and publication boundaries, independent of physical P1 DDL."""

import copy
import json
import re

import pytest

from tools.adr_publication import (
    PUBLIC_ADRS,
    accepted_rows,
    destinations,
    rewrite_links,
    stage_adrs,
)
from tools.design_viz import MODEL, ROOT, generate_html, load_model


def test_cited_semantic_model_and_observation_separation():
    m = load_model()
    entities = {e["id"]: e for e in m["entities"]}
    assert len({s["id"] for s in m["stores"]}) == 5
    assert (
        entities["design/core/coverage_claims"]
        != entities["design/context/coverage_claims"]
    )
    assert (
        entities["design/core/ref_observations"]["keys"][0]["text"]
        == "(observation_origin_uuidv4, ref_observation_uuidv7)"
    )
    for name in [
        "ref_observation_claims",
        "notes_mappings",
        "notes_mapping_claims",
        "notes_mapping_groups",
        "notes_mapping_evidence",
        "notes_role_evidence",
    ]:
        assert "design/core/" + name in entities
    assert entities["design/access/scope_locators"]["keys"][0]["status"] == "P"
    assert (
        entities["design/access/connection_configurations"]["keys"][0]["status"] == "P"
    )
    assert (
        entities["design/core/ref_enumeration_observations"]["meaning"]["status"] == "P"
    )
    assert entities["design/context/resources"]["keys"][0]["text"].startswith(
        "(service_instance_uuidv4, resource_kind, provider_resource_id)"
    )
    assert all(r["kind"] == "semantic" for r in m["relations"])
    facts = [s["meaning"] for s in m["stores"]] + [r["meaning"] for r in m["relations"]]
    for e in entities.values():
        facts.extend([e["meaning"], *e["keys"], *e["constraints"]])
    for f in facts:
        for source in f["sources"]:
            headings = re.findall(
                r"^#+ (.+)$", (ROOT / source["path"]).read_text(), re.M
            )
            anchors = {
                re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings
            }
            assert source["anchor"] in anchors, source


@pytest.mark.parametrize(
    "change", ["uncited", "status", "duplicate", "endpoint", "unqualified", "tree"]
)
def test_invalid_design_model_refused(tmp_path, change):
    m = json.loads(MODEL.read_text())
    if change == "uncited":
        m["entities"][0]["meaning"]["sources"] = []
    if change == "status":
        m["entities"][0]["meaning"]["status"] = "implemented"
    if change == "duplicate":
        m["entities"].append(copy.deepcopy(m["entities"][0]))
    if change == "endpoint":
        m["relations"][0]["target"] = "repositories"
    if change == "unqualified":
        m["entities"][0]["id"] = "repositories"
    if change == "tree":
        m["source_tree"] = "0" * 40
    path = tmp_path / "model.json"
    path.write_text(json.dumps(m))
    with pytest.raises(ValueError):
        load_model(path)


def test_published_decision_bodies_and_scoped_applicability(tmp_path):
    rows = accepted_rows()
    assert set(rows) == set(PUBLIC_ADRS)
    stage_adrs(tmp_path, "a39311eb95293f778c1e67d24bd7a6acc272dc3e")
    assert len(list((tmp_path / "adr").glob("*.md"))) == len(destinations()) + 1
    for source, dest in destinations().items():
        # After removing the separate applicability banner, every canonical byte
        # survives except rewritten links. No editable second decision source.
        text = (tmp_path / dest).read_text()
        expected = rewrite_links(
            (ROOT / source).read_text(),
            source,
            "a39311eb95293f778c1e67d24bd7a6acc272dc3e",
        )
        if source in rows:
            text = re.sub(
                r"> \*\*現在の適用範囲（正本索引）:\*\* .*?\n> 全文.*?\n\n", "", text
            )
        assert text.strip() == expected.strip()
    index = (tmp_path / "adr/index.md").read_text()
    assert "Placement/full-backup now superseded by ADR 0029" in index
    assert not any(
        p.name.startswith(("0003-", "0018-", "0019-", "0020-", "0021-", "0027-"))
        for p in (tmp_path / "adr").glob("*.md")
    )
    assert "ADR 0036" in index


def test_link_routing_stays_local_only_for_published_sources():
    text = "[next](0036-ref-observations-and-shared-notes-mappings.md#decision) [private](../testing.md)"
    out = rewrite_links(text, "docs/adr/0029-independent-access-store.md", "abc123")
    assert "[next](0036-ref-observations-and-shared-notes-mappings.md#decision)" in out
    assert (
        "[private](https://github.com/TakashiSasaki/git-repo-db/blob/abc123/docs/testing.md)"
        in out
    )


def test_viewer_embeds_only_semantic_design_model():
    html = generate_html()
    data = re.search(
        r'<script id="design-model" type="application/json">(.*?)</script>', html, re.S
    )[1]
    assert json.loads(data) == load_model()
    assert "CREATE TABLE" not in data
    assert '<script src="http' not in html
    assert "width=device-width" in html
    assert "minmax(0,1fr)" in html
