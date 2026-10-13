# 開発者ドキュメントサイト運用保守ガイド

本ドキュメントでは、`git-repo-db` の公式開発者向け技術ドキュメントサイト（[https://git-repo-db.moukaeritai.work/](https://git-repo-db.moukaeritai.work/)）の構成、ビルド手順、公開安全基準、および GitHub Actions による自動デプロイワークフローについて解説します。

---

## 1. サイトのアーキテクチャと公開境界

### 公開 URL と情報設計
- **公開ドメイン**: `https://git-repo-db.moukaeritai.work/`
- **主要ルート構成**:
  - `/`: トップページ（概要、解決する課題、開発状況、主要リンク）
  - `/architecture/`: アーキテクチャ概要（レイヤリング、データフロー）
  - `/architecture/three-store-boundary/`: Three-Store Boundary 詳解（ADR 0002 / PF-P01〜PF-P17）
  - `/schema/`: スキーマ概要とテーブル一覧（`docs/schema/README.md` から生成）
  - `/schema/viewer/`: インタラクティブスキーマビューアー（スタンドアロン HTML ワークベンチ）
  - `/schema/mermaid/`: Mermaid ER ダイアグラム一覧および各モジュールの SVG レンダリングページ
  - `/schema/dbml/`: DBML エクスポート解説とダウンロード
  - `/adr/`: ADR 一覧、ADR 0001、ADR 0002
  - `/development/`: 開発・テスト・検証ガイド

### 公開許可リスト（Publication Allowlist）の原則
本リポジトリには、設計変遷の検証記録、過去の試行ログ、非推奨となったモノリシック Schema 20 のドラフトなどが保存されています。
セキュリティおよびドキュメントの正確性を担保するため、**リポジトリ全体や `docs/` ディレクトリ全体を自動公開することは禁止**されています。

公開される成果物は、`scripts/build_docs_site.py` によって明示的にステージングされた以下のコンテンツのみに限定されます：
1. `docs/site/` 下に配置された公開用 Markdown ドキュメント
2. `docs/adr/0001-validation-lifecycle-architecture.md` および `0002-three-store-boundary-architecture.md`
3. `docs/schema/README.md`（ステージング時にリンクパスを調整して `schema/index.md` へ変換）
4. `docs/schema/index.html`（`schema/viewer/index.html` へ配置し、index.html の衝突を回避）
5. `docs/schema/mermaid/*.md`（Mermaid ブロックをビルド時に SVG へ変換して埋め込み）
6. `docs/schema/dbml/*.dbml`（静的ダウンロードファイルとして配置）

---

## 2. ローカルでのビルド・検証・プレビュー手順

### 必要ツールの準備
```bash
# ドキュメント開発用の依存関係（mkdocs, mkdocs-material）を同期
uv sync --locked --group dev --group docs
```

### ローカルビルド
```bash
uv run --no-sync python scripts/build_docs_site.py
```

ビルドプロセスは以下を自動実行します：
1. **スキーマ鮮度検証**: `scripts/schema_viz.py --check` を実行し、コミット済みスキーマ成果物が DDL と一致しているか検証（不一致時は直ちに失敗）。
2. **ステージング生成**: 一時ディレクトリ `.build/docs-source/` に許可リスト対象のファイルを収集・変換。
3. **Mermaid SVG レンダリング**: `@mermaid-js/mermaid-cli` を使用して 10 種のダイアグラムを SVG へ変換。
4. **MkDocs 静的ビルド**: `mkdocs build --strict` を実行し、リンク切れを許容せず `site/` を出力。
5. **公開安全性・リンク検査**: `site/` 内に禁止ファイル（`.sqlite3`, ソースコード, 認証情報等）が含まれていないか走査し、内部リンクを再検証。

### リアルタイムプレビューサーバーの起動
```bash
uv run --no-sync python scripts/build_docs_site.py --serve
```
ブラウザで `http://127.0.0.1:8000/` を開くと、ホットリロード対応のプレビューが可能です。

### 非公開・検証専用チェック
```bash
uv run --no-sync python scripts/build_docs_site.py --check
```

---

## 3. スキーマ変更時の更新手順

データベーススキーマ（DDL）を変更した場合の手順：

1. `src/repo_catalog/adapters/sqlite/schema.py` または SQL リソースを編集。
2. スキーマ可視化成果物を再生成：
   ```bash
   uv run --no-sync python scripts/schema_viz.py --format all
   ```
3. 鮮度チェックが成功することを確認：
   ```bash
   uv run --no-sync python scripts/schema_viz.py --check
   ```
4. ドキュメントサイトを再ビルドしてリンクや図面の表示を確認：
   ```bash
   uv run --no-sync python scripts/build_docs_site.py
   ```

> [!WARNING]
> ビルドスクリプトや CI は、コミットされたスキーマ成果物を自動で書き換えません。成果物の再生成は開発者の明示的なアクションとして実行し、差分をコミットする必要があります。

---

## 4. GitHub Actions ワークフロー (`.github/workflows/pages.yml`)

### トリガーと動作規則
- **Pull Request**:
  - `build` ジョブのみ実行。
  - スキーマ鮮度チェック、サイトビルド、公開安全性検査、厳密リンク検査を実施。
  - レビュー用に GitHub Actions Artifact として `pages-preview` を 7 日間保持。
  - **公開デプロイは実行されません（PR の完全分離）**。
- **`main` ブランチへの Push（PR マージ後）**:
  - `build` ジョブが成功すると、`deploy` ジョブがトリガーされます。
  - `actions/upload-pages-artifact` および `actions/deploy-pages` を使用して、公式の GitHub Pages 環境（`github-pages`）へ自動デプロイされます。
- **手動実行 (`workflow_dispatch`)**:
  - `main` ブランチでのみデプロイ可能。他のブランチからの手動実行時はビルド検証のみが行われます。

### 権限設定（Permissions）
最小権限の原則に従い、ジョブごとに必要最小限の権限のみが付与されています：
- `build` ジョブ: `contents: read` のみ
- `deploy` ジョブ: `pages: write`, `id-token: write` のみ（公式 OIDC 連携用）

### デプロイステータスの確認
- リポジトリの [Actions タブ](https://github.com/TakashiSasaki/git-repo-db/actions/workflows/pages.yml) でワークフローの実行状況を確認できます。
- リポジトリの Settings > Pages で、カスタムドメイン `git-repo-db.moukaeritai.work` の DNS 状態および SSL 証明書の発行状況を確認できます。

---

## 5. 新規ドキュメントの追加方法

新しい開発者向けドキュメントを追加する場合：

1. `docs/site/<category>/<document-name>.md` にファイルを配置します。
2. `mkdocs.yml` の `nav` セクションにページタイトルと相対パスを追加します。
3. `scripts/build_docs_site.py` を実行して、リンク切れや構文エラーがないかを検証します。
4. 過去の記録と現在の仕様を混同しないよう、最新のアーキテクチャ（Three-Store, Core 21 / Op 1 / Search 1）に基づいていることを確認してください。
