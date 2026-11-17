// Shared by Vite and the MkDocs standalone renderer. Keep this module dependency-free.
export function renderApp(model) {
  const app = document.getElementById("app");
  const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  // Links to the existing site also work in the isolated Vite/AI Studio preview.
  const siteBase = location.pathname.startsWith("/design/semantic") ? "/" : "https://git-repo-db.moukaeritai.work/";
  const sources = (items = [], revision = model.source_revision) => `<ul class="sources">${items.map((c) => `<li><a href="https://github.com/TakashiSasaki/resource-atlas/blob/${revision}/${c.path.split("/").map(encodeURIComponent).join("/")}#L${c.line}" target="_blank" rel="noopener noreferrer">${esc(c.path)}:${c.line}<span class="sr-only">（固定コミットの出典・別タブ）</span></a></li>`).join("")}</ul>`;
  const bullets = (items) => `<ul>${items.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`;
  const domainMap = new Map(model.domains.map((d) => [d.id, d]));
  const concepts = new Map(model.concepts.map((c) => [c.id, c]));
  const statusNames = { implemented: "実装あり", partial: "一部実装", "not-implemented": "未実装" };
  const scopeNames = { "structural-only": "構造RDFのみ", "instance-pilot": "限定インスタンス検証", unmapped: "意味対応は未実装" };
  const relationNames = { "domain-reference": "意味上の参照", observation: "観測", claim: "主張", derivation: "導出", execution: "実行" };
  let selected = null;
  let filter = "all";
  let query = "";
  let readingPath = "";
  let relationFilter = "all";
  let nearbyOnly = false;
  let activeRelation = null;
  app.innerHTML = `
    <header class="site-header"><a class="brand" href="${siteBase}">resource-atlas <span>TECHNICAL ATLAS</span></a><nav aria-label="関連する解説"><a href="${siteBase}design/">5ストア設計</a><a href="${siteBase}schema/viewer/">物理スキーマ</a><a href="https://github.com/TakashiSasaki/resource-atlas">GitHub ↗</a></nav></header>
    <main id="main" tabindex="-1">
      <section class="hero" aria-labelledby="title"><div><p class="eyebrow">APPLICATION SEMANTIC MAP</p><h1 id="title">アプリ全体を、<br>意味のつながりから読む。</h1><p class="lead">Gitの対象と主張、サービスの文脈、接続設定、取得要求、検索、ファイルとWorktreeの観測。領域をまたぐ関係を、一枚の図から辿ります。</p><p class="revision">コード調査 ${esc(model.reviewed_at)} · <a href="https://github.com/TakashiSasaki/resource-atlas/tree/${model.source_revision}">${model.source_revision.slice(0, 8)}</a> を固定</p></div><aside class="finding"><p class="eyebrow">この図で探索できること</p><h2>${model.domains.length}つの責務領域。<br>${model.concepts.length}の概念と${model.relations.length}の関係。</h2><p>何を同じ対象とみなし、どの観測・主張・証拠に結び付くかを確認できます。説明用にまとめたモデルであり、全クラスの一覧や物理スキーマではありません。</p><a href="#model-map">意味モデルの全体図へ ↓</a></aside></section>
      <nav class="section-nav" aria-label="ページ内"><a href="#model-map">意味モデルの全体図</a><a href="#overview">領域の役割</a><a href="#explore">概念を詳しく読む</a><a href="#rdf">RDFの進捗</a><a href="#reading">コードを読む</a></nav>
      <section id="model-map" aria-labelledby="map-title">
        <div class="section-heading"><p class="eyebrow">01 / CONNECTED MODEL</p><h2 id="map-title">異なる事実が、どこでつながるか。</h2><p>枠は責務領域、点は意味を持つ概念、矢印は説明用モデルに登録した関係です。概念や矢印を選ぶと、同一性・関係の意味・固定コミットの出典を読めます。</p></div>
        <div class="map-controls">
          <label>読む順路<select id="reading-path"><option value="">自由に探索する</option>${model.reading_paths.map((p) => `<option value="${p.id}">${esc(p.label)}</option>`).join("")}</select></label>
          <label>概念へ移動<select id="map-concept">${model.domains.map((d) => `<optgroup label="${esc(d.label)}">${model.concepts.filter((c) => c.domain === d.id).map((c) => `<option value="${c.id}">${esc(c.label)}</option>`).join("")}</optgroup>`).join("")}</select></label>
          <label>矢印の種類<select id="relation-filter"><option value="all">すべての関係</option>${Object.entries(relationNames).map(([id, label]) => `<option value="${id}">${esc(label)}</option>`).join("")}</select></label>
          <label class="map-check"><input id="map-nearby" type="checkbox" />選択した概念の関係だけを表示</label>
        </div>
        <div id="path-guide" class="path-guide" aria-live="polite"></div>
        <div class="map-layout"><div class="map-stage">
          <div class="map-toolbar"><div class="zoom-controls" aria-label="図の拡大率"><button id="map-zoom-out" type="button" aria-label="図を縮小">−</button><output id="map-zoom" aria-live="polite"></output><button id="map-zoom-in" type="button" aria-label="図を拡大">＋</button><button id="map-fit" type="button">全体を収める</button></div><button id="map-reset" type="button">図をリセット</button></div>
          <div id="map-viewport" class="map-viewport" tabindex="0" role="region" aria-label="意味モデルの関係図。スクロールで移動できます" aria-describedby="map-help"><svg id="semantic-graph" role="group" aria-labelledby="semantic-title semantic-desc"></svg></div>
          <p id="map-help" class="caption">拡大後は図の中をスクロールして移動できます。概念は上の選択欄からも選べます。矢印の向きは関係を記述する向きであり、取得順や起動依存を表しません。</p>
          <ul class="map-legend" aria-label="矢印の凡例">${Object.entries(relationNames).map(([id, label]) => `<li><span class="legend-line ${id}" aria-hidden="true"></span>${esc(label)}</li>`).join("")}</ul>
          <p id="map-status" class="caption" role="status"></p>
        </div><aside id="map-inspector" class="map-inspector" aria-label="選択した概念と関係" aria-live="polite"></aside></div>
        <details class="scope-note"><summary>図の範囲とRDFとの関係</summary><p>${esc(model.scope)}</p><p>${esc(model.runtime_scope)}</p><p>${esc(model.conclusion)}</p><a href="#rdf">RDFの実装範囲と残課題を読む</a></details>
      </section>
      <section id="overview" aria-labelledby="overview-title"><div class="section-heading"><p class="eyebrow">02 / LANDSCAPE</p><h2 id="overview-title">7つの責務。異なる種類の事実。</h2><p>${esc(model.runtime_scope)}</p></div><div class="landscape"><div><div class="graph-wrap"><svg class="domain-graph" viewBox="0 0 900 480" role="img" aria-labelledby="graph-title graph-desc"><title id="graph-title">責務領域の主な関係</title><desc id="graph-desc">矢印は意味上の参照・検索投影・実行を区別します。領域を選ぶと概念を絞り込みます。同じ図の内容を下の一覧でも確認できます。</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="currentColor"/></marker></defs><g class="graph-edges"></g><g class="graph-nodes"></g></svg></div><p class="caption">意味上の参照 <span class="line-sample"></span>　検索投影 <span class="line-sample dashed"></span>　実行 <span class="line-sample dotted"></span><br>主要な関係の案内です。物理FK・必須起動順・データベース数を表す図ではありません。</p><details><summary>図の関係を一覧で読む</summary><ul id="domain-edges"></ul></details></div><aside class="domain-list" aria-label="責務の一覧">${model.domains.map((d) => `<button class="domain-card" data-domain="${d.id}"><span class="domain-dot ${d.id}"></span><span><strong>${esc(d.label)}</strong><small>${esc(d.summary)}</small></span><span aria-hidden="true">↗</span></button>`).join("")}</aside></div><details class="scope-note"><summary>この俯瞰の範囲と、既存資料の読み方</summary><p>${esc(model.scope)}</p><p>以前の5ストア設計ビューアーは、その資料が固定した出典時点の案内です。このページはFilesystem／Worktreesを含む新しいコードを調査しています。7責務・10登録スキーマ形式・15配布物は異なる単位であり、必要なDBファイル数ではありません。</p>${sources([{ path: "website/schema-model-inventory.md", line: 1 }])}<p class="revision">選択製品SHA: <code>${model.source_revision}</code><br>選択製品tree: <code>${model.source_tree}</code><br>このページの文書・ビルドrevisionは、選択製品とは別の情報です。</p></details></section>
      <section id="explore" aria-labelledby="explore-title"><div class="section-heading"><p class="eyebrow">03 / CONCEPT EXPLORER</p><h2 id="explore-title">概念・同一性・主張を辿る</h2><p>テーブルの形から離れて、何を識別し、何について述べるデータなのかを確認します。</p></div><div class="filters"><label>責務 <select id="domain-filter"><option value="all">すべての領域</option>${model.domains.map((d) => `<option value="${d.id}">${esc(d.label)}</option>`).join("")}</select></label><label class="query-label">概念を検索 <input id="concept-search" type="search" placeholder="例: Notes、同一性、走査、未解決" /></label><button id="reset" type="button">絞り込みを解除</button></div><p id="match-count" role="status"></p><div class="explorer"><div id="concept-list" class="concept-list" aria-label="概念の一覧"></div><article id="concept-detail" class="concept-detail" aria-live="polite"></article></div></section>
      <section id="rdf" aria-labelledby="rdf-title"><div class="section-heading"><p class="eyebrow">04 / RDF READINESS</p><h2 id="rdf-title">「RDFがある」と「意味を記述できる」の間</h2><p>版付きの構造投影と、Filesystem／Worktreesの意味のある検証パイロットがあります。表・列のRDF化だけで、GitやContextの意味全体を形式化したとは判断できません。</p></div><div class="layer-grid">${model.layers.map((l, i) => `<details class="layer"><summary><span>${String(i + 1).padStart(2, "0")}</span>${esc(l.label)}</summary><p>${esc(l.summary)}</p>${sources(l.citations)}</details>`).join("")}</div><p class="caption">ADR 0040で区別する6層。各層の実装・採択・実行結果は個別に評価します。</p><div class="workstreams">${model.workstreams.map((w) => `<article class="workstream"><div><span class="badge ${w.status}">${esc(statusNames[w.status] || w.status)}</span><h3>${esc(w.label)}</h3><p>${esc(w.summary)}</p></div><div><h4>確認できる範囲</h4>${bullets(w.implemented)}<h4>残っている範囲</h4>${bullets(w.gaps)}<details><summary>実装・決定の根拠</summary>${sources(w.citations)}</details></div></article>`).join("")}</div><div class="evidence-note"><h3>制約適合・仕様・操作・実装の結果を分ける</h3><p>このページはコードの調査結果です。RDF／SHACL検証を新たに実行した記録ではありません。既存パイロットの成功をアプリ全体の検証済み表示へ拡張しません。</p><div class="result-grid">${model.result_families.map((f) => `<article><code>${esc(f.id)}</code><h4>${esc(f.label)}</h4><p>${esc(f.summary)}</p><span class="badge">今回の調査: ${esc(f.status)}</span></article>`).join("")}</div></div><div class="next-steps"><h3>意味モデルを広げる次の作業</h3><ol>${model.next_steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol></div></section>
      <section id="reading" aria-labelledby="reading-title"><div class="section-heading"><p class="eyebrow">05 / REPOSITORY GUIDE</p><h2 id="reading-title">問いから、コードと設計へ</h2><p>ブラウザーで技術解説を読み、固定コミットの出典へ戻るための入口です。</p></div><div class="reading-grid"><article><h3>Git・Providerの意味</h3><p>原観測と主張、Notesの保持目的、Resourceの同一性から読みます。</p>${sources([{ path: "packages/core/src/repo_catalog/domain/ref_observation.py", line: 1 }, { path: "packages/context/src/repo_catalog/domain/resource_identity.py", line: 1 }, { path: "docs/adr/0036-ref-observations-and-shared-notes-mappings.md", line: 1 }])}</article><article><h3>ローカルのファイルとWorktree</h3><p>観測の区間、部分走査、ハッシュ状態、任意の外部参照を確認します。Localはこれらを組み合わせる配布物です。</p>${sources([{ path: "docs/adr/0039-independent-filesystem-and-worktree-catalogs.md", line: 1 }, { path: "packages/filesystem/README.md", line: 1 }, { path: "packages/worktrees/README.md", line: 1 }, { path: "packages/local/README.md", line: 1 }])}</article><article><h3>RDF・SHACLの実装</h3><p>語彙、投影、制約一覧、使い捨てフィクスチャ、結果の解釈を別々に辿ります。</p>${sources([{ path: "docs/adr/0040-scoped-machine-readable-model-validation.md", line: 1 }, { path: "tools/schema-model/README.md", line: 1 }, { path: "tools/schema-model/INSTANCE-PILOT.md", line: 1 }])}</article><article><h3>サイトを編集する</h3><p>ルートのnpm入口はこのUIの開発用です。Python製品、サイト全体のMkDocsビルド、データモデルの正本は独立した役割を持ちます。手順へのリンクはmainの現行文書です。</p>${sources([{ path: "website/README.md", line: 1 }, { path: "AGENTS.md", line: 1 }], "main")}<a href="${siteBase}architecture/">既存のアーキテクチャ解説 ↗</a></article></div></section>
      <footer><strong>resource-atlas / データモデルの技術解説</strong><p>ソースと採択済み設計が正本です。このページは説明用の派生資料です。</p><a href="${siteBase}">解説サイトのホーム</a> · <a href="https://github.com/TakashiSasaki/resource-atlas">リポジトリ</a></footer>
    </main>`;

  const coords = { core: [315, 145], context: [610, 145], access: [150, 40], operational: [745, 40], search: [460, 340], filesystem: [150, 340], worktrees: [150, 205] };
  const edgeData = [
    ["context", "core", "文脈からGitへの参照", "reference"],
    ["access", "core", "明示的なRepository関連付け", "reference"],
    ["worktrees", "core", "Repositoryへの任意の関連付け", "reference"],
    ["worktrees", "filesystem", "修飾された任意の走査参照", "reference"],
    ["core", "search", "検索投影", "derivation"],
    ["context", "search", "文脈テキストの検索投影", "derivation"],
    ["operational", "context", "取得の実行状態", "execution"],
  ];
  document.querySelector(".graph-edges").innerHTML = edgeData.map(([a, b, label, kind]) => {
    const [ax, ay] = coords[a], [bx, by] = coords[b];
    const dx = bx - ax, dy = by - ay, length = Math.hypot(dx, dy);
    // Intersect the 140×60 node boundary, leaving room for the target arrowhead.
    const boundary = 1 / Math.max(Math.abs(dx) / 70, Math.abs(dy) / 30);
    const x1 = ax + 70 + dx * boundary + dx / length * 3;
    const y1 = ay + 30 + dy * boundary + dy / length * 3;
    const x2 = bx + 70 - dx * boundary - dx / length * 8;
    const y2 = by + 30 - dy * boundary - dy / length * 8;
    return `<path class="edge ${kind}" data-source="${a}" data-target="${b}" d="M${x1} ${y1} L${x2} ${y2}" marker-end="url(#arrow)"><title>${esc(label)}</title></path>`;
  }).join("");
  document.querySelector(".graph-nodes").innerHTML = model.domains.map((d) => {
    const [x, y] = coords[d.id];
    return `<g class="graph-node ${d.id}" data-domain="${d.id}" role="button" tabindex="0" aria-label="${esc(d.label)}の概念を表示" transform="translate(${x},${y})"><rect width="140" height="60" rx="12"/><text x="70" y="35" text-anchor="middle">${d.id[0].toUpperCase() + d.id.slice(1)}</text></g>`;
  }).join("");
  document.getElementById("domain-edges").innerHTML = edgeData.map(([a, b, label]) => `<li>${esc(domainMap.get(a).label)} → ${esc(domainMap.get(b).label)}: ${esc(label)}</li>`).join("");

  // Layout is derived from the concept registry, never from physical tables.
  // Two balanced columns leave room to read clusters; all edges remain in one SVG.
  const mapPositions = new Map();
  const columnBottoms = [24, 24];
  const mapWidth = 1252;
  const nodeWidth = 260, nodeHeight = 68;
  const clusters = model.domains.map((d) => {
    const items = model.concepts.filter((c) => c.domain === d.id);
    const column = columnBottoms[0] <= columnBottoms[1] ? 0 : 1;
    const x = 24 + column * 624, y = columnBottoms[column];
    const height = 74 + Math.ceil(items.length / 2) * 86;
    columnBottoms[column] += height + 24;
    items.forEach((c, i) => mapPositions.set(c.id, { x: x + 24 + (i % 2) * 284, y: y + 58 + Math.floor(i / 2) * 86 }));
    return `<g class="semantic-cluster ${d.id}"><rect x="${x}" y="${y}" width="600" height="${height}" rx="16"/><text x="${x + 24}" y="${y + 33}">${esc(d.label)} · ${items.length}</text></g>`;
  }).join("");
  const mapHeight = Math.max(...columnBottoms);
  const graph = document.getElementById("semantic-graph");
  graph.setAttribute("viewBox", `0 0 ${mapWidth} ${mapHeight}`);
  const relationKey = (a, b) => [a, b].sort().join("|");
  const graphEdges = model.relations.map((r, i) => {
    const a = mapPositions.get(r.source), b = mapPositions.get(r.target);
    const ax = a.x + nodeWidth / 2, ay = a.y + nodeHeight / 2;
    const bx = b.x + nodeWidth / 2, by = b.y + nodeHeight / 2;
    const dx = bx - ax, dy = by - ay, length = Math.hypot(dx, dy);
    const boundary = 1 / Math.max(Math.abs(dx) / (nodeWidth / 2), Math.abs(dy) / (nodeHeight / 2));
    const x1 = ax + dx * boundary + dx / length * 3;
    const y1 = ay + dy * boundary + dy / length * 3;
    const x2 = bx - dx * boundary - dx / length * 9;
    const y2 = by - dy * boundary - dy / length * 9;
    const label = `${concepts.get(r.source).label} → ${concepts.get(r.target).label}：${r.label}（${relationNames[r.kind]}）`;
    return `<g class="semantic-edge ${r.kind}" data-relation="${i}" data-source="${r.source}" data-target="${r.target}" role="button" tabindex="0" aria-label="${esc(label)}"><title>${esc(label)}</title><path class="edge-hit" d="M${x1} ${y1} L${x2} ${y2}"/><path class="edge-line" d="M${x1} ${y1} L${x2} ${y2}" marker-end="url(#semantic-arrow-${r.kind})"/></g>`;
  }).join("");
  graph.innerHTML = `<title id="semantic-title">アプリケーションの意味モデル：${model.domains.length}領域・${model.concepts.length}概念・${model.relations.length}関係</title><desc id="semantic-desc">概念と矢印をキーボードまたはポインターで選べます。枠は責務領域です。物理FKや同時に稼働するDB数を表しません。</desc><defs>${Object.keys(relationNames).map((kind) => `<marker id="semantic-arrow-${kind}" class="${kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10z"/></marker>`).join("")}</defs>${clusters}<g class="semantic-edges">${graphEdges}</g><g class="semantic-nodes">${model.concepts.map((c) => {
    const { x, y } = mapPositions.get(c.id);
    const chars = Array.from(c.label);
    const lines = chars.length > 16 ? [chars.slice(0, 16).join(""), chars.slice(16).join("")] : [c.label];
    return `<g class="semantic-node ${c.domain}" data-map-concept="${c.id}" role="button" tabindex="0" aria-label="${esc(domainMap.get(c.domain).label)}：${esc(c.label)}" aria-pressed="false" transform="translate(${x},${y})"><title>${esc(c.meaning)}</title><rect width="${nodeWidth}" height="${nodeHeight}" rx="9"/><text x="16" y="${lines.length > 1 ? 28 : 39}">${lines.map((line, i) => `<tspan x="16" dy="${i ? 24 : 0}">${esc(line)}</tspan>`).join("")}</text></g>`;
  }).join("")}</g>`;

  const viewport = document.getElementById("map-viewport");
  let mapScale = 1;
  const minimumMapScale = () => Math.min(0.25, viewport.clientWidth / mapWidth, viewport.clientHeight / mapHeight);
  function setMapScale(value, keepCenter = true) {
    const cx = (viewport.scrollLeft + viewport.clientWidth / 2) / mapScale;
    const cy = (viewport.scrollTop + viewport.clientHeight / 2) / mapScale;
    // Fit must remain possible even when a narrow viewport needs <25% zoom.
    mapScale = Math.max(minimumMapScale(), Math.min(1.75, value));
    graph.style.width = `${mapWidth * mapScale}px`;
    graph.style.height = `${mapHeight * mapScale}px`;
    document.getElementById("map-zoom").textContent = `${Math.round(mapScale * 100)}%`;
    document.getElementById("map-zoom-out").disabled = mapScale <= minimumMapScale();
    document.getElementById("map-zoom-in").disabled = mapScale >= 1.75;
    if (keepCenter) viewport.scrollTo({ left: cx * mapScale - viewport.clientWidth / 2, top: cy * mapScale - viewport.clientHeight / 2, behavior: "instant" });
  }
  function fitMap() { setMapScale(Math.min(viewport.clientWidth / mapWidth, viewport.clientHeight / mapHeight), false); viewport.scrollTo(0, 0); }
  function revealConcept(id) {
    const p = mapPositions.get(id);
    viewport.scrollTo({ left: (p.x + nodeWidth / 2) * mapScale - viewport.clientWidth / 2, top: (p.y + nodeHeight / 2) * mapScale - viewport.clientHeight / 2, behavior: "instant" });
  }
  function relationContent(r) {
    return `<span class="badge">${esc(relationNames[r.kind])}</span><p class="map-direction">${esc(concepts.get(r.source).label)} <span aria-label="から">→</span> ${esc(concepts.get(r.target).label)}</p><strong>${esc(r.label)}</strong><p>${esc(r.note)}</p><details><summary>関係の出典</summary>${sources(r.citations)}</details>`;
  }
  function updateMap() {
    const path = model.reading_paths.find((p) => p.id === readingPath);
    const pathNodes = new Set(path?.steps || []);
    const pathEdges = new Set((path?.steps || []).slice(1).map((id, i) => relationKey(path.steps[i], id)));
    const relatedNodes = new Set(selected ? [selected] : []);
    let visibleEdges = 0;
    graph.querySelectorAll(".semantic-edge").forEach((el, i) => {
      const r = model.relations[i];
      const touching = r.source === selected || r.target === selected;
      const visible = (relationFilter === "all" || r.kind === relationFilter) && (!nearbyOnly || touching);
      el.classList.toggle("is-hidden", !visible);
      el.setAttribute("tabindex", visible ? "0" : "-1");
      el.setAttribute("aria-hidden", String(!visible));
      el.classList.toggle("emphasized", activeRelation === i || (path ? pathEdges.has(relationKey(r.source, r.target)) : touching));
      el.classList.toggle("subdued", path ? !pathEdges.has(relationKey(r.source, r.target)) : !touching);
      if (visible) { visibleEdges++; if (touching) { relatedNodes.add(r.source); relatedNodes.add(r.target); } }
    });
    graph.querySelectorAll(".semantic-node").forEach((el) => {
      const id = el.dataset.mapConcept;
      el.classList.toggle("selected", id === selected);
      el.classList.toggle("in-path", pathNodes.has(id));
      el.classList.toggle("subdued", path ? !pathNodes.has(id) && id !== selected : nearbyOnly && !relatedNodes.has(id));
      el.setAttribute("aria-pressed", String(id === selected));
    });
    document.getElementById("map-concept").value = selected || "";
    document.getElementById("reading-path").value = readingPath;
    document.getElementById("map-status").textContent = `${model.domains.length}領域・${model.concepts.length}概念 ／ ${visibleEdges} / ${model.relations.length}関係を表示。${path ? "読む順路を強調しています。" : "選択した概念につながる関係を強調しています。"}`;
    document.getElementById("path-guide").innerHTML = path ? `<h3>${esc(path.label)}</h3><p>${esc(path.summary)}</p><ol>${path.steps.map((id) => `<li><button type="button" data-map-concept="${id}" aria-pressed="${id === selected}">${esc(concepts.get(id).label)}</button></li>`).join("")}</ol><p class="caption">番号は読む順番です。各関係の向きと意味は図・詳細で確認できます。</p>` : '<p>読む順路を選ぶと、関連する概念と関係が浮かび上がります。全概念は常に図に残ります。</p>';
    const c = concepts.get(selected);
    const relations = model.relations.map((r, i) => ({ ...r, index: i })).filter((r) => r.source === selected || r.target === selected);
    document.getElementById("map-inspector").innerHTML = `${activeRelation !== null ? `<article class="selected-relation"><p class="eyebrow">選択した関係</p>${relationContent(model.relations[activeRelation])}</article>` : ""}${c ? `<p class="eyebrow">${esc(domainMap.get(c.domain).label)}</p><h3>${esc(c.label)}</h3><p>${esc(c.meaning)}</p><h4>同一性</h4><p class="map-key">${esc(c.key)}</p><button type="button" class="text-button" data-concept="${c.id}">意味を保つ条件とRDF対応を詳しく読む ↓</button><details><summary>概念の出典</summary>${sources(c.citations)}</details><h4>つながる関係 · ${relations.length}</h4><p class="caption">この一覧は関係フィルターにかかわらず、選択概念のすべての関係を示します。</p><ul class="map-relations">${relations.map((r) => {
      const other = r.source === selected ? r.target : r.source;
      return `<li>${relationContent(r)}<button type="button" class="text-button" data-map-concept="${other}">${esc(concepts.get(other).label)}へ移動 →</button></li>`;
    }).join("")}</ul>` : "<h3>概念を選んでください</h3><p>図の点か、概念の選択欄から探索できます。</p>"}`;
  }
  document.getElementById("map-zoom-in").addEventListener("click", () => setMapScale(mapScale * 1.25));
  document.getElementById("map-zoom-out").addEventListener("click", () => setMapScale(mapScale / 1.25));
  document.getElementById("map-fit").addEventListener("click", fitMap);
  document.getElementById("map-concept").addEventListener("change", (event) => { activeRelation = null; selectConcept(event.target.value, false, true); revealConcept(event.target.value); });
  document.getElementById("reading-path").addEventListener("change", (event) => {
    readingPath = event.target.value; activeRelation = null;
    const path = model.reading_paths.find((p) => p.id === readingPath);
    relationFilter = "all"; nearbyOnly = false;
    document.getElementById("relation-filter").value = "all";
    document.getElementById("map-nearby").checked = false;
    selectConcept(path?.steps[0] || selected || model.concepts[0].id, false, true);
    revealConcept(selected);
  });
  document.getElementById("relation-filter").addEventListener("change", (event) => { relationFilter = event.target.value; activeRelation = null; updateMap(); });
  document.getElementById("map-nearby").addEventListener("change", (event) => { nearbyOnly = event.target.checked; updateMap(); });
  document.getElementById("map-reset").addEventListener("click", () => {
    readingPath = ""; relationFilter = "all"; nearbyOnly = false; activeRelation = null;
    document.getElementById("relation-filter").value = "all";
    document.getElementById("map-nearby").checked = false;
    selectConcept(model.concepts[0].id, false, true); fitMap();
  });
  // Keep mobile labels readable initially; fit-to-view is an explicit control.
  setMapScale(Math.max(0.65, Math.min(1, viewport.clientWidth / mapWidth)), false);

  function detail(c) {
    const relations = model.relations.filter((r) => r.source === c.id || r.target === c.id);
    document.getElementById("concept-detail").innerHTML = `<p class="eyebrow">${esc(domainMap.get(c.domain).label)}</p><h3>${esc(c.label)}</h3><p class="concept-meaning">${esc(c.meaning)}</p><h4>何を同じ対象とみなすか</h4><p class="semantic-key">${esc(c.key)}</p><h4>意味を保つための条件</h4>${bullets(c.invariants)}<div class="rdf-scope"><span class="badge">${esc(scopeNames[c.rdf_scope])}</span><p>${esc(model.rdf_scope_notes[c.rdf_scope])}</p></div><h4>他の概念との関係</h4>${relations.length ? `<ul class="relations">${relations.map((r) => { const other = concepts.get(r.source === c.id ? r.target : r.source); return `<li><span class="relation-kind">${esc(relationNames[r.kind] || r.kind)}</span><div>${esc(concepts.get(r.source).label)} <span aria-hidden="true">→</span> ${esc(concepts.get(r.target).label)}<br><strong>${esc(r.label)}</strong><p>${esc(r.note)}</p><button type="button" class="text-button" data-concept="${other.id}">${esc(other.label)}を読む →</button></div></li>`; }).join("")}</ul>` : "<p>この俯瞰には直接の関係を登録していません。</p>"}<h4>コード・設計の出典</h4>${sources(c.citations)}`;
  }
  function renderConcepts() {
    const text = query.trim().toLocaleLowerCase();
    const matches = model.concepts.filter((c) => (filter === "all" || c.domain === filter) && [c.label, c.meaning, c.key, ...c.invariants].join(" ").toLocaleLowerCase().includes(text));
    document.getElementById("match-count").textContent = `${matches.length} / ${model.concepts.length} 概念`;
    const chosen = matches.find((c) => c.id === selected) || matches[0];
    selected = chosen?.id || null;
    document.getElementById("concept-list").innerHTML = matches.map((c) => `<button type="button" data-concept="${c.id}" class="concept-card ${c.id === selected ? "selected" : ""}" aria-pressed="${c.id === selected}"><small>${esc(domainMap.get(c.domain).label)}</small><strong>${esc(c.label)}</strong><span>${esc(c.meaning)}</span></button>`).join("") || '<p class="empty">一致する概念はありません。検索語や責務の絞り込みを変更してください。</p>';
    if (chosen) detail(chosen);
    else document.getElementById("concept-detail").innerHTML = '<h3>概念が見つかりません</h3><p>絞り込みを解除して全体へ戻れます。</p>';
    document.querySelectorAll("[data-domain]").forEach((el) => el.classList.toggle("active", el.dataset.domain === filter));
    updateMap();
  }
  function selectConcept(id, moveFocus = false, inMap = false) {
    const c = concepts.get(id);
    if (!c) return;
    filter = "all"; query = ""; selected = id;
    document.getElementById("domain-filter").value = filter;
    document.getElementById("concept-search").value = query;
    const params = new URLSearchParams({ concept: id });
    if (inMap) { params.set("view", "map"); if (readingPath) params.set("path", readingPath); }
    else { readingPath = ""; activeRelation = null; }
    history.pushState(null, "", `#${params}`);
    renderConcepts();
    if (moveFocus) {
      const detailEl = document.getElementById("concept-detail");
      detailEl.tabIndex = -1; detailEl.focus({ preventScroll: true });
      detailEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  app.addEventListener("click", (event) => {
    const mapButton = event.target.closest("[data-map-concept]");
    const relationButton = event.target.closest("[data-relation]");
    if (mapButton) {
      activeRelation = null;
      const id = mapButton.dataset.mapConcept;
      selectConcept(id, false, true);
      if (!mapButton.matches("g")) {
        revealConcept(id);
        graph.querySelector(`[data-map-concept="${id}"]`).focus({ preventScroll: true });
      }
      return;
    }
    if (relationButton) {
      const index = Number(relationButton.dataset.relation);
      activeRelation = index;
      selectConcept(model.relations[index].source, false, true);
      return;
    }
    const domainButton = event.target.closest("[data-domain]");
    const conceptButton = event.target.closest("[data-concept]");
    if (domainButton) {
      filter = domainButton.dataset.domain; query = ""; selected = null;
      document.getElementById("domain-filter").value = filter;
      document.getElementById("concept-search").value = "";
      renderConcepts();
      document.getElementById("explore").scrollIntoView({ behavior: "smooth" });
      document.getElementById("domain-filter").focus({ preventScroll: true });
    } else if (conceptButton) selectConcept(conceptButton.dataset.concept, true);
  });
  app.addEventListener("keydown", (event) => {
    if (event.target.matches("g[data-domain], g[data-map-concept], g[data-relation]") && ["Enter", " "].includes(event.key)) { event.preventDefault(); event.target.dispatchEvent(new MouseEvent("click", { bubbles: true })); }
  });
  document.getElementById("domain-filter").addEventListener("change", (event) => { filter = event.target.value; renderConcepts(); });
  document.getElementById("concept-search").addEventListener("input", (event) => { query = event.target.value; renderConcepts(); });
  document.getElementById("reset").addEventListener("click", () => { filter = "all"; query = ""; document.getElementById("domain-filter").value = filter; document.getElementById("concept-search").value = ""; renderConcepts(); });
  function fromHash() {
    const params = new URLSearchParams(location.hash.slice(1));
    const id = params.get("concept");
    const inMap = params.get("view") === "map";
    readingPath = inMap && model.reading_paths.some((p) => p.id === params.get("path")) ? params.get("path") : "";
    activeRelation = null;
    if (concepts.has(id)) {
      selected = id; filter = "all"; query = "";
      document.getElementById("domain-filter").value = filter;
      document.getElementById("concept-search").value = "";
      renderConcepts();
      document.getElementById(inMap ? "model-map" : "explore").scrollIntoView();
      if (inMap) revealConcept(id);
    } else {
      selected = null; filter = "all"; query = "";
      document.getElementById("domain-filter").value = filter;
      document.getElementById("concept-search").value = "";
      renderConcepts();
    }
  }
  window.addEventListener("popstate", fromHash);
  window.addEventListener("hashchange", fromHash);
  renderConcepts();
  fromHash();
}
