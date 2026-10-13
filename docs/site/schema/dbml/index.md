# DBML (Database Markup Language) エクスポート

`git-repo-db` のデータベーススキーマは、標準的な **DBML (Database Markup Language)** 形式でエクスポートされています。

VS Code の DBML 拡張機能やローカルの DBML ビューアーを利用することで、スキーマ定義の閲覧や ER 図の確認が可能です。

> [!NOTE]
> DBML ファイルはリポジトリの正式な DDL（SQLite）から `scripts/schema_viz.py` によって決定論的（Deterministic）に自動生成されています。

---

## 提供されている DBML ファイル一覧

以下の 4 種類のエクスポートファイルを提供しています：

| ファイル名 | 対象ストア | スキーマ | テーブル数 | 主な用途・利用指針 |
|---|---|---|---|---|
| [**core.dbml**](core.dbml) | Core Store | Schema 21 | 70 | 永続ドメインモデル、Git DAG、CAS、Change Request などのコアデータモデルを詳細に確認する場合に使用します。 |
| [**operational.dbml**](operational.dbml) | Operational Store | Schema 1 | 10 | ジョブ実行管理、試行進捗、トランスポートキャッシュの管理構造を確認する場合に使用します。 |
| [**search.dbml**](search.dbml) | Search Store | Schema 1 | 4 | FTS5 仮想テーブルの親となる検索ドキュメントプロジェクションや世代管理構造を確認する場合に使用します。 |
| [**combined.dbml**](combined.dbml) | 3ストア統合 (概念図) | 合計 | 84 | 全 84 テーブルの関係性を 1 つの図で概念的に把握する場合に使用します。 |

---

## 重要：combined.dbml の位置付け

> [!WARNING]
> **物理的な単一データベースではありません**:  
> `combined.dbml` は、システム全体に存在するテーブル群の関係性を俯瞰するための**概念的な表現（Conceptual Representation）**です。
> 
> [ADR 0002](../../adr/0002-three-store-boundary-architecture.md) に規定されているとおり、実際の本番環境では `catalog.sqlite3`、`operational.sqlite3`、`search.sqlite3` の **3 つの独立した SQLite ファイルに物理分離** されており、ストアをまたぐ物理外部キー制約は存在しません。

---

## 利用方法とツール連携

1. **ローカルエディタでの閲覧**:
   - VS Code 拡張機能「*vscode-dbml*」などを導入すると、構文ハイライトとプレビュー図が表示されます。
2. **dbdiagram.io などの外部ツールでの利用**:
   - ダウンロードした `.dbml` の内容をコピー＆ペーストしてダイアグラムを生成できます。
   - **セキュリティに関する注意**: 本リポジトリから外部サービスへの自動アップロードは行いません。必要に応じて開発者が手動でローカル利用してください。

---

## スキーマ整合性検証

DBML ファイルが現在の Python DDL と完全一致しているかは、以下のコマンドで常時検証されます：

```bash
uv run --no-sync python scripts/schema_viz.py --check
```
