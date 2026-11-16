"""The semantic overview stays source-bound and uses one browser implementation."""

import json
import re

import pytest

from tools import semantic_viz
from tools.semantic_viz import MODEL, generate_html, load_model


def test_semantic_overview_distinguishes_structure_and_domain_pilot():
    model = load_model()
    assert model["source_revision"] == "d6f9634cffdbeca1986d973245d7cc99b73fa408"
    assert "未完了" in model["conclusion"]
    concepts = {c["id"]: c for c in model["concepts"]}
    assert {c["domain"] for c in concepts.values()} == {
        d["id"] for d in model["domains"]
    }
    assert any(c["rdf_scope"] == "instance-pilot" for c in concepts.values())
    assert all(
        c["rdf_scope"] != "instance-pilot"
        for c in concepts.values()
        if c["domain"] in {"core", "context", "access"}
    )
    streams = {w["id"]: w for w in model["workstreams"]}
    assert streams["structural-rdf"]["status"] == "implemented"
    assert len(model["layers"]) == 6
    assert {f["status"] for f in model["result_families"]} == {"not_run"}


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda m: m.update(source_tree="0" * 40), "tree mismatch"),
        (lambda m: m["relations"][0].update(target="invented-concept"), "endpoint"),
        (lambda m: m["concepts"][0].update(rdf_scope="verified"), "RDF scope"),
        (
            lambda m: m["result_families"][0].update(status="pass"),
            "new model execution",
        ),
        (
            lambda m: m["domains"][0]["citations"][0].update(path="../private"),
            "citation",
        ),
    ],
)
def test_invalid_semantic_claims_refused(tmp_path, mutation, reason):
    model = json.loads(MODEL.read_text())
    mutation(model)
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    with pytest.raises(ValueError, match=reason):
        load_model(path)


def test_mkdocs_page_inlines_the_same_ui_without_product_or_npm_imports():
    html = generate_html()
    data = re.search(r'id="semantic-model">(.*?)</script>', html, re.S).group(1)
    assert json.loads(data) == load_model()
    assert "export function renderApp(model)" in html
    assert 'id="app"' in html
    assert "/documentation/web/main.js" not in html
    assert not re.search(r'<(?:script|link)\b[^>]*(?:src|href)="https?://', html)


@pytest.mark.parametrize("target", ["entry", "web"])
def test_frontend_symlinks_refused_before_reading(tmp_path, monkeypatch, target):
    root = tmp_path / "repo"
    root.mkdir()
    web = root / "web"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("not a documentation input")
    if target == "entry":
        (root / "index.html").symlink_to(outside / "private.txt")
        web.mkdir()
    else:
        (root / "index.html").write_text("entry")
        web.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(semantic_viz, "ROOT", root)
    monkeypatch.setattr(semantic_viz, "WEB", web)
    with pytest.raises(ValueError, match="Symlink frontend"):
        generate_html()
