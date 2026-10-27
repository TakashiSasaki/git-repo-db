# 開発・テストおよびコントリビューションガイド

本ドキュメントでは、`git-repo-db` のローカル開発環境のセットアップ、テスト実行手順、品質検証、およびドキュメントサイトの管理方法について解説します。

---

## 1. 前提条件と環境構築

### 必要ツール
- **Python**: `python3` 3.9 以上（セットアップの起動にのみ使用）。製品用の Python 3.12 は検証済み配布物が提供します
- **uv**: 高速な Python パッケージマネージャー（`astral-sh/uv`）。セットアップは `uv` を導入しません
- **SQLite**: 3.51.3 以上（実行環境の Python が実際に読み込むもの。上記配布物に内蔵され、別途導入しません）
- **Git**: 2.40 以上
- **Node.js**: 20 以上（ドキュメントサイトの Mermaid ダイアグラムを SVG レンダリングする場合）

### 仮想環境のセットアップ
リポジトリのルートで次の一つのコマンドを実行します。manifest で固定された完全な Python 配布物の検証・導入、`.venv` の作成（既存 `.venv` は検証し、不一致なら破壊せず失敗）、`uv sync --locked --group dev`、製品 preflight、`artifacts/local-python/receipt.json` の保存まで行い、いずれかが失敗すれば非ゼロで終了します：

```bash
./scripts/setup-local-python.sh
```

以降のコマンドは `scripts/local-run.sh <command>` で実行すると、検証済みの Python が常に選ばれます（下記の `uv run --no-sync ...` は `scripts/local-run.sh uv run --no-sync ...` と読み替えてください）。詳細は [docs/local-python.md](https://github.com/TakashiSasaki/git-repo-db/blob/main/docs/local-python.md) を参照してください。

> [!NOTE]
> ドキュメント用の依存関係（`mkdocs`, `mkdocs-material`）は、本番アプリケーションの依存関係（`[project].dependencies`）とは完全に分離された `documentation/pyproject.toml` に定義されています。

---

## 2. ローカル検証ワークフロー (ADR 0001 準拠)

[ADR 0001](../adr/0001-validation-lifecycle-architecture.md) に基づき、日常の開発では**軽量かつ依存関係に応じた焦点化検証（Focused Validation）** をローカルで行います。

### 静的解析とコードフォーマット
```bash
# Ruff による構文・リンターチェック
uv run --no-sync ruff check src tests scripts

# フォーマットの検査
uv run --no-sync ruff format --check src tests scripts

# フォーマットの自動適用
uv run --no-sync ruff format src tests scripts
```

### スキーマ整合性検証 (Schema Freshness Check)
選択した製品コミットから検証済み製品環境で IR を作成し、文書環境で可視化成果物（HTML, Mermaid, DBML）を検証します。`FULL_PRODUCT_SHA` は現在の製品チェックアウトに一致する完全なコミット SHA を指定します：

```bash
FULL_PRODUCT_SHA="FULL_PRODUCT_COMMIT_SHA"
scripts/local-run.sh python scripts/schema_inventory.py --source "$FULL_PRODUCT_SHA" --output documentation/.build/inputs
uv run --project documentation --no-sync python documentation/tools/schema_viz.py --ir documentation/.build/inputs/inventory.json --check
```

不整合が検出された場合、以下のコマンドで可視化成果物を明示的に再生成します：

```bash
uv run --project documentation --no-sync python documentation/tools/schema_viz.py --ir documentation/.build/inputs/inventory.json --format all
```

### 焦点を絞ったテストの実行
変更したモジュールに対応するテストをピンポイントで実行します：

```bash
# スキーマ可視化ワークベンチのテスト
uv run --project documentation --no-sync pytest documentation/tests/test_schema_viz.py

# CI プランニングロジックのテスト
uv run --no-sync pytest tests/unit/test_ci_plan.py
```

---

## 3. ドキュメントサイトのビルドとプレビュー

開発者ドキュメントサイト（本サイト）は、MkDocs Material と専用のステージングスクリプト `documentation/tools/build_docs_site.py` によってビルドされます。

### ローカルでのサイトビルド
```bash
uv run --project documentation --no-sync python documentation/tools/build_docs_site.py --product-source FULL_PRODUCT_SHA --documentation-source FULL_DOC_SHA
```

このコマンドは内部で以下を順次実行します：
1. `documentation/tools/schema_viz.py --check` によるスキーマ鮮度の検証
2. 一時ステージングディレクトリへの公開許可ドキュメントの配置
3. 10 種類の Mermaid ER 図のブラウザ互換 SVG へのレンダリング
4. スタンドアロンスキーマビューアーおよび DBML ファイルの配置
5. `mkdocs build --strict` による静的サイト生成
6. 生成成果物に対する公開安全性検査（機密ファイル混入防止）およびリンク検証

### ローカルでのリアルタイムプレビュー
```bash
uv run --project documentation --no-sync python documentation/tools/build_docs_site.py --product-source FULL_PRODUCT_SHA --documentation-source FULL_DOC_SHA --serve
```

ローカルサーバーが起動し、`http://127.0.0.1:8000/` でホットリロード付きのプレビューが可能です。

### 検証専用コマンド (非公開チェック)
```bash
uv run --project documentation --no-sync python documentation/tools/build_docs_site.py --product-source FULL_PRODUCT_SHA --documentation-source FULL_DOC_SHA --check
```

---

## 4. CI パイプラインと自動デプロイ

### 開発モード (Development Mode)
Pull Request の作成時やブランチプッシュ時、GitHub Actions の `.github/workflows/tests.yml` は**軽量な静的検査とスモーク検査**のみを実行します。
また、`.github/workflows/pages.yml` はドキュメントサイトのビルドとリンク検証のみを行い、**公開デプロイは一切行いません**。

### リリース受入モード (Release Acceptance Mode)
完全な 2,254 件のテストスイート実行、ホイールパッケージの完全性検証、およびローカル・ホスト間の厳密な照合は、手動の `workflow_dispatch`（`mode: release`）でのみ実行されます。

### GitHub Pages への自動デプロイ
1. PR に対するレビューとローカル検証が完了。
2. リポジトリオーナーが PR を `main` ブランチへマージ。
3. `pages.yml` ワークフローが `main` ブランチの最新コミットを検知。
4. ビルド・検証ジョブが成功した場合にのみ、`deploy` ジョブが公式アクション（`actions/deploy-pages`）を用いて [https://git-repo-db.moukaeritai.work/](https://git-repo-db.moukaeritai.work/) へ自動反映。
