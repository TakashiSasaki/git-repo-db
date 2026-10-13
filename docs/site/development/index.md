# 開発・テストおよびコントリビューションガイド

本ドキュメントでは、`git-repo-db` のローカル開発環境のセットアップ、テスト実行手順、品質検証、およびドキュメントサイトの管理方法について解説します。

---

## 1. 前提条件と環境構築

### 必要ツール
- **Python**: 3.12 以上
- **uv**: 高速な Python パッケージマネージャー（`astral-sh/uv`）
- **SQLite**: 3.31 以上（STRICT モードおよび Generated Columns 対応）
- **Git**: 2.40 以上
- **Node.js**: 20 以上（ドキュメントサイトの Mermaid ダイアグラムを SVG レンダリングする場合）

### 仮想環境のセットアップ
リポジトリのルートで `uv` を使用して依存関係を同期します：

```bash
# 通常の開発・テスト用依存関係の同期
uv sync --locked --group dev

# ドキュメントサイト作成・検証を含めた同期
uv sync --locked --group dev --group docs
```

> [!NOTE]
> ドキュメント用の依存関係（`mkdocs`, `mkdocs-material`）は、本番アプリケーションの依存関係（`[project].dependencies`）とは完全に分離された `[dependency-groups].docs` に定義されています。

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
SQLite の DDL 定義と生成された可視化成果物（HTML, Mermaid, DBML）が一致しているかを検証します：

```bash
uv run --no-sync python scripts/schema_viz.py --check
```

不整合が検出された場合、以下のコマンドで可視化成果物を明示的に再生成します：

```bash
uv run --no-sync python scripts/schema_viz.py --format all
```

### 焦点を絞ったテストの実行
変更したモジュールに対応するテストをピンポイントで実行します：

```bash
# スキーマ可視化ワークベンチのテスト
uv run --no-sync pytest tests/unit/test_schema_viz.py

# CI プランニングロジックのテスト
uv run --no-sync pytest tests/unit/test_ci_plan.py
```

---

## 3. ドキュメントサイトのビルドとプレビュー

開発者ドキュメントサイト（本サイト）は、MkDocs Material と専用のステージングスクリプト `scripts/build_docs_site.py` によってビルドされます。

### ローカルでのサイトビルド
```bash
uv run --no-sync python scripts/build_docs_site.py
```

このコマンドは内部で以下を順次実行します：
1. `scripts/schema_viz.py --check` によるスキーマ鮮度の検証
2. 一時ステージングディレクトリへの公開許可ドキュメントの配置
3. 10 種類の Mermaid ER 図のブラウザ互換 SVG へのレンダリング
4. スタンドアロンスキーマビューアーおよび DBML ファイルの配置
5. `mkdocs build --strict` による静的サイト生成
6. 生成成果物に対する公開安全性検査（機密ファイル混入防止）およびリンク検証

### ローカルでのリアルタイムプレビュー
```bash
uv run --no-sync python scripts/build_docs_site.py --serve
```

ローカルサーバーが起動し、`http://127.0.0.1:8000/` でホットリロード付きのプレビューが可能です。

### 検証専用コマンド (非公開チェック)
```bash
uv run --no-sync python scripts/build_docs_site.py --check
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
