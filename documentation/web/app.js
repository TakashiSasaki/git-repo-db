// Shared by Vite and the MkDocs standalone renderer. Keep this module dependency-free.
export function renderApp(model) {
  const app = document.getElementById("app");
  const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  // Links to the existing site also work in the isolated Vite/AI Studio preview.
  const siteBase = location.pathname.startsWith("/design/semantic") ? "/" : "https://git-repo-db.moukaeritai.work/";
  const sources = (items = [], revision = model.source_revision) => `<ul class="sources">${items.map((c) => `<li><a href="https://github.com/TakashiSasaki/git-repo-db/blob/${revision}/${c.path.split("/").map(encodeURIComponent).join("/")}#L${c.line}" target="_blank" rel="noopener noreferrer">${esc(c.path)}:${c.line}<span class="sr-only">（固定コミットの出典・別タブ）</span></a></li>`).join("")}</ul>`;
  const bullets = (items) => `<ul>${items.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`;
  const domainMap = new Map(model.domains.map((d) => [d.id, d]));
  const concepts = new Map(model.concepts.map((c) => [c.id, c]));
  const statusNames = { implemented: "実装あり", partial: "一部実装", "not-implemented": "未実装" };
  const scopeNames = { "structural-only": "構造RDFのみ", "instance-pilot": "限定インスタンス検証", unmapped: "意味対応は未実装" };
  const relationNames = { "domain-reference": "意味上の参照", observation: "観測", claim: "主張", derivation: "導出", execution: "実行" };
  let selected = null;
  let filter = "all";
  let query = "";
  app.innerHTML = `
    <header class="site-header"><a class="brand" href="${siteBase}">git-repo-db <span>TECHNICAL ATLAS</span></a><nav aria-label="関連する解説"><a href="${siteBase}design/">5ストア設計</a><a href="${siteBase}schema/viewer/">物理スキーマ</a><a href="https://github.com/TakashiSasaki/git-repo-db">GitHub ↗</a></nav></header>
    <main id="main" tabindex="-1">
      <section class="hero" aria-labelledby="title"><div><p class="eyebrow">DATA MODEL / SEMANTICS / RDF</p><h1 id="title">データが表す意味から、<br>アプリケーションを読む。</h1><p class="lead">Repositoryの同一性、GitとProviderの主張、ファイルの観測。その関係と、RDFで記述できている範囲を辿ります。</p><p class="revision">コード調査 ${esc(model.reviewed_at)} · <a href="https://github.com/TakashiSasaki/git-repo-db/tree/${model.source_revision}">${model.source_revision.slice(0, 8)}</a> を固定</p></div><aside class="finding"><p class="eyebrow">現在の到達点</p><h2>RDF化は進行中。<br>全領域の意味モデルは未完了。</h2><p>${esc(model.conclusion)}</p><a href="#rdf">実装範囲と残課題を見る ↓</a></aside></section>
      <nav class="section-nav" aria-label="ページ内"><a href="#overview">全体像</a><a href="#explore">概念と関係</a><a href="#rdf">RDFの進捗</a><a href="#reading">コードを読む</a></nav>
      <section id="overview" aria-labelledby="overview-title"><div class="section-heading"><p class="eyebrow">01 / LANDSCAPE</p><h2 id="overview-title">7つの責務。異なる種類の事実。</h2><p>${esc(model.runtime_scope)}</p></div><div class="landscape"><div><div class="graph-wrap"><svg class="domain-graph" viewBox="0 0 900 480" role="img" aria-labelledby="graph-title graph-desc"><title id="graph-title">責務領域の主な関係</title><desc id="graph-desc">矢印は意味上の参照・検索投影・実行を区別します。領域を選ぶと概念を絞り込みます。同じ図の内容を下の一覧でも確認できます。</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="currentColor"/></marker></defs><g class="graph-edges"></g><g class="graph-nodes"></g></svg></div><p class="caption">意味上の参照 <span class="line-sample"></span>　検索投影 <span class="line-sample dashed"></span>　実行 <span class="line-sample dotted"></span><br>主要な関係の案内です。物理FK・必須起動順・データベース数を表す図ではありません。</p><details><summary>図の関係を一覧で読む</summary><ul id="domain-edges"></ul></details></div><aside class="domain-list" aria-label="責務の一覧">${model.domains.map((d) => `<button class="domain-card" data-domain="${d.id}"><span class="domain-dot ${d.id}"></span><span><strong>${esc(d.label)}</strong><small>${esc(d.summary)}</small></span><span aria-hidden="true">↗</span></button>`).join("")}</aside></div><details class="scope-note"><summary>この俯瞰の範囲と、既存資料の読み方</summary><p>${esc(model.scope)}</p><p>以前の5ストア設計ビューアーは、その資料が固定した出典時点の案内です。このページはFilesystem／Worktreesを含む新しいコードを調査しています。7責務・10登録スキーマ形式・15配布物は異なる単位であり、必要なDBファイル数ではありません。</p>${sources([{ path: "documentation/schema-model-inventory.md", line: 1 }])}<p class="revision">選択製品SHA: <code>${model.source_revision}</code><br>選択製品tree: <code>${model.source_tree}</code><br>このページの文書・ビルドrevisionは、選択製品とは別の情報です。</p></details></section>
      <section id="explore" aria-labelledby="explore-title"><div class="section-heading"><p class="eyebrow">02 / CONCEPT EXPLORER</p><h2 id="explore-title">概念・同一性・主張を辿る</h2><p>テーブルの形から離れて、何を識別し、何について述べるデータなのかを確認します。</p></div><div class="filters"><label>責務 <select id="domain-filter"><option value="all">すべての領域</option>${model.domains.map((d) => `<option value="${d.id}">${esc(d.label)}</option>`).join("")}</select></label><label class="query-label">概念を検索 <input id="concept-search" type="search" placeholder="例: Notes、同一性、走査、未解決" /></label><button id="reset" type="button">絞り込みを解除</button></div><p id="match-count" role="status"></p><div class="explorer"><div id="concept-list" class="concept-list" aria-label="概念の一覧"></div><article id="concept-detail" class="concept-detail" aria-live="polite"></article></div></section>
      <section id="rdf" aria-labelledby="rdf-title"><div class="section-heading"><p class="eyebrow">03 / RDF READINESS</p><h2 id="rdf-title">「RDFがある」と「意味を記述できる」の間</h2><p>版付きの構造投影と、Filesystem／Worktreesの意味のある検証パイロットがあります。表・列のRDF化だけで、GitやContextの意味全体を形式化したとは判断できません。</p></div><div class="layer-grid">${model.layers.map((l, i) => `<details class="layer"><summary><span>${String(i + 1).padStart(2, "0")}</span>${esc(l.label)}</summary><p>${esc(l.summary)}</p>${sources(l.citations)}</details>`).join("")}</div><p class="caption">ADR 0040で区別する6層。各層の実装・採択・実行結果は個別に評価します。</p><div class="workstreams">${model.workstreams.map((w) => `<article class="workstream"><div><span class="badge ${w.status}">${esc(statusNames[w.status] || w.status)}</span><h3>${esc(w.label)}</h3><p>${esc(w.summary)}</p></div><div><h4>確認できる範囲</h4>${bullets(w.implemented)}<h4>残っている範囲</h4>${bullets(w.gaps)}<details><summary>実装・決定の根拠</summary>${sources(w.citations)}</details></div></article>`).join("")}</div><div class="evidence-note"><h3>制約適合・仕様・操作・実装の結果を分ける</h3><p>このページはコードの調査結果です。RDF／SHACL検証を新たに実行した記録ではありません。既存パイロットの成功をアプリ全体の検証済み表示へ拡張しません。</p><div class="result-grid">${model.result_families.map((f) => `<article><code>${esc(f.id)}</code><h4>${esc(f.label)}</h4><p>${esc(f.summary)}</p><span class="badge">今回の調査: ${esc(f.status)}</span></article>`).join("")}</div></div><div class="next-steps"><h3>意味モデルを広げる次の作業</h3><ol>${model.next_steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol></div></section>
      <section id="reading" aria-labelledby="reading-title"><div class="section-heading"><p class="eyebrow">04 / REPOSITORY GUIDE</p><h2 id="reading-title">問いから、コードと設計へ</h2><p>ブラウザーで技術解説を読み、固定コミットの出典へ戻るための入口です。</p></div><div class="reading-grid"><article><h3>Git・Providerの意味</h3><p>原観測と主張、Notesの保持目的、Resourceの同一性から読みます。</p>${sources([{ path: "packages/core/src/repo_catalog/domain/ref_observation.py", line: 1 }, { path: "packages/context/src/repo_catalog/domain/resource_identity.py", line: 1 }, { path: "docs/adr/0036-ref-observations-and-shared-notes-mappings.md", line: 1 }])}</article><article><h3>ローカルのファイルとWorktree</h3><p>観測の区間、部分走査、ハッシュ状態、任意の外部参照を確認します。Localはこれらを組み合わせる配布物です。</p>${sources([{ path: "docs/adr/0039-independent-filesystem-and-worktree-catalogs.md", line: 1 }, { path: "packages/filesystem/README.md", line: 1 }, { path: "packages/worktrees/README.md", line: 1 }, { path: "packages/local/README.md", line: 1 }])}</article><article><h3>RDF・SHACLの実装</h3><p>語彙、投影、制約一覧、使い捨てフィクスチャ、結果の解釈を別々に辿ります。</p>${sources([{ path: "docs/adr/0040-scoped-machine-readable-model-validation.md", line: 1 }, { path: "tools/schema-model/README.md", line: 1 }, { path: "tools/schema-model/INSTANCE-PILOT.md", line: 1 }])}</article><article><h3>サイトを編集する</h3><p>ルートのnpm入口はこのUIの開発用です。Python製品、サイト全体のMkDocsビルド、データモデルの正本は独立した役割を持ちます。手順へのリンクはmainの現行文書です。</p>${sources([{ path: "documentation/README.md", line: 1 }, { path: "AGENTS.md", line: 1 }], "main")}<a href="${siteBase}architecture/">既存のアーキテクチャ解説 ↗</a></article></div></section>
      <footer><strong>git-repo-db / データモデルの技術解説</strong><p>ソースと採択済み設計が正本です。このページは説明用の派生資料です。</p><a href="${siteBase}">解説サイトのホーム</a> · <a href="https://github.com/TakashiSasaki/git-repo-db">リポジトリ</a></footer>
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
    const x1 = ax + 60 + dx / length * 60, y1 = ay + 25 + dy / length * 28;
    const x2 = bx + 60 - dx / length * 60, y2 = by + 25 - dy / length * 28;
    return `<path class="edge ${kind}" d="M${x1} ${y1} L${x2} ${y2}" marker-end="url(#arrow)"><title>${esc(label)}</title></path>`;
  }).join("");
  document.querySelector(".graph-nodes").innerHTML = model.domains.map((d) => {
    const [x, y] = coords[d.id];
    return `<g class="graph-node ${d.id}" data-domain="${d.id}" role="button" tabindex="0" aria-label="${esc(d.label)}の概念を表示" transform="translate(${x},${y})"><rect width="140" height="60" rx="12"/><text x="70" y="35" text-anchor="middle">${d.id[0].toUpperCase() + d.id.slice(1)}</text></g>`;
  }).join("");
  document.getElementById("domain-edges").innerHTML = edgeData.map(([a, b, label]) => `<li>${esc(domainMap.get(a).label)} → ${esc(domainMap.get(b).label)}: ${esc(label)}</li>`).join("");

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
  }
  function selectConcept(id, moveFocus = false) {
    const c = concepts.get(id);
    if (!c) return;
    filter = "all"; query = ""; selected = id;
    document.getElementById("domain-filter").value = filter;
    document.getElementById("concept-search").value = query;
    history.pushState(null, "", `#concept=${encodeURIComponent(id)}`);
    renderConcepts();
    if (moveFocus) {
      const detailEl = document.getElementById("concept-detail");
      detailEl.tabIndex = -1; detailEl.focus({ preventScroll: true });
      detailEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  app.addEventListener("click", (event) => {
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
    if (event.target.matches("g[data-domain]") && ["Enter", " "].includes(event.key)) { event.preventDefault(); event.target.dispatchEvent(new MouseEvent("click", { bubbles: true })); }
  });
  document.getElementById("domain-filter").addEventListener("change", (event) => { filter = event.target.value; renderConcepts(); });
  document.getElementById("concept-search").addEventListener("input", (event) => { query = event.target.value; renderConcepts(); });
  document.getElementById("reset").addEventListener("click", () => { filter = "all"; query = ""; document.getElementById("domain-filter").value = filter; document.getElementById("concept-search").value = ""; renderConcepts(); });
  function fromHash() {
    const id = new URLSearchParams(location.hash.slice(1)).get("concept");
    if (concepts.has(id)) {
      selected = id; filter = "all"; query = "";
      document.getElementById("domain-filter").value = filter;
      document.getElementById("concept-search").value = "";
      renderConcepts();
      document.getElementById("explore").scrollIntoView();
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
