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
        "[private](https://github.com/TakashiSasaki/resource-atlas/blob/abc123/docs/testing.md)"
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


def test_design_fact_links_keep_the_historical_revision():
    import subprocess

    html = generate_html()
    model = load_model()
    reference = re.search(r"function reference\(source\) \{.*?\n      \}", html, re.S)[
        0
    ]
    source = model["stores"][0]["meaning"]["sources"][0]
    program = (
        "const model = "
        + json.dumps({"source_revision": model["source_revision"]})
        + "; const esc = x => String(x);\n"
        + reference
        + "\nprocess.stdout.write(reference("
        + json.dumps(source)
        + "));"
    )
    link = subprocess.check_output(["node", "-e", program], text=True)
    assert (
        f"https://github.com/TakashiSasaki/resource-atlas/blob/{model['source_revision']}/{source['path']}#{source['anchor']}"
        in link
    )


def test_historical_design_citation_survives_current_main_changes(
    tmp_path, monkeypatch
):
    import subprocess

    from tools import design_viz

    model = json.loads(design_viz.MODEL.read_text())
    source = tmp_path / "product"
    source.mkdir()

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=source, text=True).strip()

    def citations(value):
        if isinstance(value, dict):
            if "path" in value:
                yield value["path"]
            for item in value.values():
                yield from citations(item)
        elif isinstance(value, list):
            for item in value:
                yield from citations(item)

    paths = sorted(set(citations(model)))
    for name in paths:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("historical canonical source\n")
    git("init", "-q")
    git("config", "user.name", "Web tests")
    git("config", "user.email", "web-tests@example.invalid")
    git("add", ".")
    git("commit", "-qm", "historical citations")
    model["source_revision"] = git("rev-parse", "HEAD")
    model["source_tree"] = git("rev-parse", "HEAD^{tree}")
    (source / paths[0]).unlink()
    git("add", ".")
    git("commit", "-qm", "main retired an old source")
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model))
    monkeypatch.setattr(design_viz, "ROOT", source)
    assert design_viz.load_model(model_path) == model


def test_moved_source_links_resolve_on_the_owning_branch():
    import subprocess

    from tools.product_context import PRODUCT_ROOT, WEB_ROOT, selected_product

    product = selected_product()["commit"]
    web = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=WEB_ROOT, text=True
    ).strip()
    text = "[web](../../website/schema-model-inventory.md#scope) [product](../../scripts/schema_inventory.py) [guide](../../website/current-runtime-reference.md)"
    output = rewrite_links(text, "docs/adr/0040-example.md", product)
    assert f"/blob/{web}/website/schema-model-inventory.md#scope" in output
    assert f"/blob/{product}/scripts/schema_inventory.py" in output
    assert f"/blob/{product}/docs/current-runtime-reference.md" in output
    for root, commit, name in [
        (WEB_ROOT, web, "website/schema-model-inventory.md"),
        (PRODUCT_ROOT, product, "docs/current-runtime-reference.md"),
    ]:
        subprocess.run(
            ["git", "cat-file", "-e", commit + ":" + name], cwd=root, check=True
        )
