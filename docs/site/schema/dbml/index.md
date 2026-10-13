# DBML (Database Markup Language) エクスポートと外部ツール連携

`git-repo-db` のデータベーススキーマは、標準的な **DBML (Database Markup Language)** 形式でエクスポートされています。

公式リポジトリの SQLite DDL を正本（Single Source of Truth）とし、**dbdiagram.io**、**dbdocs.io**、**Eraser.io**、および VS Code などの外部ツールで容易に可視化・共有・分析できるように最適化されています。

> [!NOTE]
> DBML ファイルはリポジトリの正式な DDL（SQLite）から `scripts/schema_viz.py` によって決定論的（Deterministic）に自動生成されています。

---

## 提供されている DBML ファイル一覧

以下の 4 種類のエクスポートファイルを提供しています（直接ダウンロードして各ツールで利用可能）：

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
> [ADR 0002](../../adr/0002-three-store-boundary-architecture/) に規定されているとおり、実際の本番環境では `catalog.sqlite3`、`operational.sqlite3`、`search.sqlite3` の **3 つの独立した SQLite ファイルに物理分離** されており、ストアをまたぐ物理外部キー制約は存在しません。

---

## 外部ツールでの閲覧・活用ガイド

### 1. dbdiagram.io で見る方法（最も簡単・即座に可視化）

アカウント登録なしでも、ブラウザだけで即座にインタラクティブな ER 図を生成して閲覧できます：

1. ブラウザで [**dbdiagram.io** (https://dbdiagram.io/d)](https://dbdiagram.io/d) を開きます。
2. 上記リンクから目的のファイル（例: [core.dbml](core.dbml) または [operational.dbml](operational.dbml)）をダウンロードします。
3. dbdiagram.io のエディタ画面で以下のいずれかを行います：
   - **ドラッグ＆ドロップ**: ダウンロードした `.dbml` ファイルをエディタ上にドラッグ＆ドロップ。
   - **コピペ**: `.dbml` の中身を全選択して左側コードペインに貼り付け。
4. 右側ペインにインタラクティブな ER 図が即座に描画されます。テーブルをドラッグして見やすい位置に再配置したり、外部キーのリレーションをハイライトできます。

---

### 2. dbdocs.io で見る方法（Web ドキュメントポータル生成）

[**dbdocs.io**](https://dbdocs.io/) を使用すると、スキーマ定義から検索可能な Web データディクショナリおよびホストされた ER 図ポータルを生成できます。

#### CLI によるビルド・公開手順

1. **dbdocs CLI の導入**:
   ```bash
   # npm の場合
   npm install -g dbdocs

   # bun の場合
   bun add -g dbdocs
   ```

2. **ログイン（初回のみ）**:
   ```bash
   dbdocs login
   ```

3. **スキーマの構文検証**:
   ```bash
   dbdocs validate docs/schema/dbml/core.dbml
   dbdocs validate docs/schema/dbml/operational.dbml
   ```

4. **Web ポータルのビルド＆公開**:
   ```bash
   # Core Store を公開
   dbdocs build docs/schema/dbml/core.dbml --project git-repo-db-core

   # Operational Store を公開
   dbdocs build docs/schema/dbml/operational.dbml --project git-repo-db-operational

   # Search Store を公開
   dbdocs build docs/schema/dbml/search.dbml --project git-repo-db-search
   ```
   実行が完了すると、`https://dbdocs.io/<username>/git-repo-db-core` のような公開 URL が発行されます。パスワード保護（`dbdocs password --set <password>`）も設定可能です。

---

### 3. Eraser.io で見る方法（モダンな開発者キャンバス＆Diagram-as-Code）

[**Eraser.io** (https://www.eraser.io/)](https://www.eraser.io/) は、開発者向けのシステム設計キャンバスおよび Diagram-as-Code ツールです。ERD ダイアグラムブロック機能により、DBML を美しくレンダリングできます。

#### 方法 A: DBML からの直接インポート（推奨）

1. [Eraser.io](https://app.eraser.io/) にアクセスし、新しいドキュメントまたはキャンバスを開きます。
2. キャンバス上または Markdown ノート内で ERD ブロックを追加します：
   - **Canvas の場合**: ツールバーの `Insert` → `Diagram` → `Entity Relationship Diagram` を選択。
   - **Markdown ノートの場合**: ````diagram:erd```` ブロックを挿入。
3. ダイアグラムの設定メニュー（または上部バー）から **「Import」** を選択します。
4. **「Import from DBML」** を選び、ダウンロードした `core.dbml` などの内容を貼り付けて「Import」を実行します。
5. テーブル群とリレーションシップが自動的にレイアウトされ、Eraser のダークモード／ライトモードやカラーテーマが適用されたモダンな ER 図が生成されます。

#### 方法 B: SQL DDL からの直接インポート

Eraser.io は SQLite DDL の直接インポートにも対応しています：
1. Eraser の ERD ブロックで **「Import」** → **「Import from SQL」** を選択。
2. `src/repo_catalog/resources/sql/` またはリポジトリの SQLite DDL を貼り付けることで、テーブル構造を直接図に変換できます。

#### 方法 C: Eraser Diagram-as-Code 構文によるドキュメント内埋め込み

Eraser の ERD 構文は DBML と高い互換性を持っています。例えば、Search Store のような小規模スキーマを Eraser ドキュメントに直接埋め込むことも可能です：

````markdown
```diagram:erd
search_documents [icon: database, color: emerald] {
  search_document_id integer pk
  kind text
  source_key text
  body text
  metadata text
}

index_generations [icon: layers, color: blue] {
  index_generation_id integer pk
  kind text
  state text
  table_name text
  target_max_search_document_id integer
}

index_membership [icon: link, color: purple] {
  index_generation_id integer pk
  search_document_id integer pk
  input_version text
}

index_membership.index_generation_id > index_generations.index_generation_id
index_membership.search_document_id > search_documents.search_document_id
```
````

---

### 4. SchemaSpy で見る方法（詳細な HTML レポート・関係性解析・異常検出）

[**SchemaSpy** (https://schemaspy.org/)](https://schemaspy.org/) は、データベースメタデータを解析して、インタラクティブな Graphviz ER 図や孤立テーブル・制約アノマリーを含む包括的な HTML ドキュメントを生成するオープンソースツールです。

`git-repo-db` の SQLite データベースに対して SchemaSpy を実行する手順は以下の通りです：

#### ステップ 1: 正本 DDL から実体 SQLite データベースをエクスポート

SchemaSpy は実際のデータベースファイル（JDBC 接続）を必要とするため、リポジトリ付属のエクスポートツールで 3 つの SQLite ファイルを生成します：

```bash
uv run --no-sync python scripts/export_sqlite_databases.py
```
これにより、`.build/databases/` に以下の空の正本データベースが生成されます：
- `catalog.sqlite3` (Core Store Schema 21 / 70 テーブル)
- `operational.sqlite3` (Operational Store Schema 1 / 10 テーブル)
- `search.sqlite3` (Search Store Schema 1 / 4 テーブル)

#### ステップ 2: Docker で SchemaSpy を実行する（最も手軽・推奨）

Docker を利用すると、Java や Graphviz をローカルに導入することなくワンライナーでレポートを出力できます：

```bash
# Core Store のレポートを生成
docker run --rm \
  -v "$PWD/.build/databases:/db" \
  -v "$PWD/schemaspy-report/core:/output" \
  schemaspy/schemaspy:latest \
  -t sqlite-xerial \
  -db /db/catalog.sqlite3 \
  -s catalog \
  -o /output \
  -cat %

# Operational Store のレポートを生成
docker run --rm \
  -v "$PWD/.build/databases:/db" \
  -v "$PWD/schemaspy-report/operational:/output" \
  schemaspy/schemaspy:latest \
  -t sqlite-xerial \
  -db /db/operational.sqlite3 \
  -s operational \
  -o /output \
  -cat %
```

#### ステップ 3: ネイティブ Java / CLI で実行する場合

ローカル環境に Java (JRE 11+) と Graphviz (`dot`) がインストールされている場合：

1. **SchemaSpy JAR と SQLite JDBC ドライバーのダウンロード**:
   ```bash
   curl -L -o schemaspy.jar https://github.com/schemaspy/schemaspy/releases/download/v6.2.4/schemaspy-6.2.4.jar
   curl -L -o sqlite-jdbc.jar https://repo1.maven.org/maven2/org/xerial/sqlite-jdbc/3.45.1.0/sqlite-jdbc-3.45.1.0.jar
   ```
2. **レポートの実行**:
   ```bash
   java -jar schemaspy.jar \
     -t sqlite-xerial \
     -dp sqlite-jdbc.jar \
     -db .build/databases/catalog.sqlite3 \
     -s catalog \
     -o ./schemaspy-report/core \
     -cat %
   ```

#### ステップ 4: 生成された HTML レポートの閲覧

`schemaspy-report/core/index.html` をブラウザで開くと、以下の情報が閲覧できます：
- **Relationships**: Graphviz によるテーブル間リレーション図（大・中・小のズーム、テーブル個別リレーション）
- **Tables**: 全 70 テーブルのカラム定義、型、デフォルト値、コメント
- **Constraints**: 主キー、外部キー制約、CASCADE ルール一覧
- **Anomalies**: 外部キーを持たない孤立テーブル、NULL 許容制約の分析

---

### 5. ローカル VS Code で見る方法

外部クラウドサービスを使用せず、完全ローカルで DBML を閲覧・編集することも可能です：

1. VS Code の拡張機能マーケットプレイスで **`vscode-dbml`** または **`DBML ERD`** をインストール。
2. `docs/schema/dbml/*.dbml` ファイルを開く。
3. エディタ右上の「プレビュー」ボタンをクリックすると、ローカルで ER 図が表示されます。

---

## スキーマ整合性検証

DBML ファイルが現在の Python DDL と完全一致しているかは、リポジトリのテストスイートおよび CI により常時検証されています：

```bash
uv run --no-sync python scripts/schema_viz.py --check
```
