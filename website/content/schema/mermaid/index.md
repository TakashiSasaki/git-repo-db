# Mermaid ER ダイアグラム一覧 (Mermaid ER Diagrams)

`git-repo-db` のデータベーススキーマは、機能モジュールごとに分割された **10 種類の Mermaid ダイアグラム** として可視化されています。

各ページでは、ビルド時に事前レンダリングされた**高解像度 SVG ダイアグラム**を直接閲覧できるほか、フルサイズ表示や GitHub 上のソースコード確認が可能です。

---

## ダイアグラム一覧

| ダイアグラム | 対象ストア | テーブル数 | 主な内容・着目ポイント |
|---|---|---|---|
| [**Three-Store 全体俯瞰**](overview.md) | 全ストア | 84 | Core、Operational、Search の 3 ストア物理分離と、ストア間の論理依存関係（PF-P11, PF-P14, PF-P15）の全体マップ。 |
| [**Core: 全体構造マップ**](core-overview.md) | Core | 70 | Core Store の 7 つの機能モジュール（Identity, Current State, Coverage, Git, CAS, Exchange, Catalog）の配置関係。 |
| [**Core: ポータブル識別子・リポジトリ**](core-identity.md) | Core | 14 | `service_instances`, `sources`, `repositories`, `change_requests`, `review_threads` などのエンティティ識別子と関係性。 |
| [**Core: 現行状態プロジェクション**](core-current-state.md) | Core | 5 | PR / Issue / ドキュメントの最新状態プロジェクション（`change_request_state`, `document_state` など）。 |
| [**Core: カバレッジ・取得証跡**](core-coverage.md) | Core | 19 | API 取得コレクション、カバレッジクレーム、コード一覧取得の進捗と完了マーカー。 |
| [**Core: Git ドメイン・コミット DAG**](core-git.md) | Core | 21 | コミットグラフ（`commits`, `commit_parents`）、ツリー階層（`tree_objects`, `tree_entries`）、オブジェクト参照（`git_objects`）。 |
| [**Core: CAS・完全性・保持義務**](core-cas.md) | Core | 7 | 生バイト列（`stored_bytes`）、CAS ペイロード（`payloads`）、不正バイト隔離（`payload_quarantine`）、保持義務（`preservation_obligations`）。 |
| [**Core: Exchange ステージング**](core-exchange.md) | Core | 4 | カタログ間データ交換用の一時ステージングおよび受け入れテーブル。 |
| [**Operational: ジョブ・キャッシュ・進捗**](operational.md) | Operational | 10 | 実行中ジョブ（`jobs`, `job_attempts`）、Git パックファイルキャッシュリース、一時進捗追跡。 |
| [**Search: 検索プロジェクション・FTS5**](search.md) | Search | 4 | 全文検索用 FTS5 仮想テーブル、再構築可能な検索ドキュメントプロジェクション、世代管理。 |

---

## 特徴と閲覧機能

- **ビルド時 SVG 静的レンダリング**: 外部 CDN やクライアント側の JavaScript レンダリング負荷に依存せず、ビルド時に事前生成された SVG を埋め込んでいます。
- **フルサイズ拡大・縮小**: 大規模な ER 図（Core Git や Core Coverage など）は、「フルサイズ SVG を開く」ボタンからブラウザ全体でパン・ズーム表示が可能です。
- **Mermaid ソースコード**: 各ダイアグラムの下部に折りたたみブロックで生の Mermaid 構文を保持しており、コピー＆ペーストして再利用できます。
