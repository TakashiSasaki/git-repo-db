# DBML (Database Markup Language) エクスポートと外部ツール連携

`git-repo-db` のデータベーススキーマは、標準的な **DBML (Database Markup Language)** 形式でエクスポートされています。

公式リポジトリの SQLite DDL を正本（Single Source of Truth）とし、**dbdiagram.io**、**dbdocs.io**、**Eraser.io**、および VS Code などの外部ツールで容易に可視化・共有・分析できるように最適化されています。

> [!NOTE]
> DBML ファイルはリポジトリの正式な DDL（SQLite）から `documentation/tools/schema_viz.py` によって決定論的（Deterministic）に自動生成されています。

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

## このDBML案内の対象：通常3スキーマのストア境界

この案内は、通常の Catalog3 の **Core Schema 21・Operational Schema 1・Search Schema 1** と、その可視化出力を扱います。[ADR 0002](../../adr/0002-three-store-boundary-architecture/) に従い、各スキーマの所属ストアと、ストアをまたがない物理外部キーを区別します。採択済みの[5責務設計の表示](/design/)は別のモデルです。

これは、すべての起動で3つのファイルが作成・オープンされるという意味ではありません。通常の初期化は Core を作成し、Operational は必要時に遅延オープンされ、Search は `index rebuild` などで明示的に作成されます。以下の比較は通常3スキーマの出力に限定し、実環境のファイル数を保証しません。

| 可視化ツール / 手法 | 複数データベース分離の反映方法 | 物理境界の保証 |
|---|---|---|
| **dbdiagram.io / dbdocs.io** | 個別ストアの DBML (`core`, `operational`, `search`) は完全分離。<br>全体図 (`combined.dbml`) では **`TableGroup core_store` / `operational_store` / `search_store`** の枠線コンテナで所属 DB を厳格に分離表示。 | 物理外部キー（実線）はストア境界を**絶対に越えない**。ストア間は論理依存（コメント）としてのみ表現。 |
| **Azimutt** | `catalog.sql` / `operational.sql` / `search.sql` を 3 つの独立データソース（Sources）として取り込み。<br>各テーブルノードに所属 DB のバッジと色分けが付与される。 | ストアをまたぐテーブル探査時も、どの物理データベースに属するテーブルかが一目で識別可能。 |
| **SchemaSpy** | `catalog.sqlite3` / `operational.sqlite3` / `search.sqlite3` ごとに完全に独立した HTML レポートディレクトリを出力。 | データベースファイル単位のメタデータ解析により、ストア間の物理的混濁がゼロ。 |
| **Eraser.io** | ダイアグラム内の `group` 構文およびカラーパレット（青 / 藍 / 緑）により、3 つの物理ストアを独立したコンテナで囲んで表示。 | ドキュメント上でも 3 つの物理境界が視覚的に分離。 |
| **インタラクティブビューアー** | 画面最上部のストア切り替えタブ（Core 70 / Operational 10 / Search 4）およびストア別アクセントカラー。 | 同一画面に混在させず、ストアごとにスコープされた探索ワークベンチを提供。 |
| **Mermaid ダイアグラム** | `subgraph CoreStore` / `OpStore` / `SearchStore` による明示的コンテナ分離。<br>ストア内は実線（物理 FK）、ストア間は点線（論理依存）。 | 図の構造自体が ADR 0002 の 3 ストア物理境界を表現。 |

---

## 重要：combined.dbml の位置付け

> [!WARNING]
> **物理的な単一データベースではありません**:  
> `combined.dbml` は、システム全体に存在するテーブル群の関係性を俯瞰するための**概念的な表現（Conceptual Representation）**です。
> 
> 通常3スキーマの対応ファイル名は `catalog.sqlite3`、`operational.sqlite3`、`search.sqlite3` ですが、作成・利用の時点は各ランタイム経路によります。ストアをまたぐ物理外部キー制約は存在せず、`TableGroup` は通常スキーマの所属ストアを区別します。

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
   dbdocs validate documentation/schema/dbml/core.dbml
   dbdocs validate documentation/schema/dbml/operational.dbml
   ```

4. **Web ポータルのビルド＆公開**:
   ```bash
   # Core Store を公開
   dbdocs build documentation/schema/dbml/core.dbml --project git-repo-db-core

   # Operational Store を公開
   dbdocs build documentation/schema/dbml/operational.dbml --project git-repo-db-operational

   # Search Store を公開
   dbdocs build documentation/schema/dbml/search.dbml --project git-repo-db-search
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
2. `src/repo_catalog/adapters/sqlite/schema.py` が `src/repo_catalog/resources/` 配下の SQL から合成する DDL を貼り付けることで、テーブル構造を直接図に変換できます。

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
scripts/local-run.sh python scripts/export_sqlite_databases.py
```
安全対策として、出力先は存在しないディレクトリを指定します（既存の空ディレクトリも拒否します）。親はリンクをたどらずに作成します。再生成は別の新規出力先を指定してください。既存データベースや SQL ファイルは削除・上書きしません。Linux/glibc のローカル実行環境で、6 ファイルを検証してから一括公開します。他 OS は未検証で、安全な公開が利用できなければ失敗します。

SQLite ファイルやサイドカーの検査は出力先の直近の親に限られます。さらに上のディレクトリにカタログがないことは保証しません。また、このチェックアウト自身の祖先は他のチェックアウトを示すマーカーの検査対象外です。カタログやソースから分離した新規出力先を選んでください。

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

### 5. Azimutt で見る方法（大規模スキーマのための探索型ビジュアルキャンバス）

[**Azimutt** (https://azimutt.app/)](https://azimutt.app/) は、数十〜数百テーブルを持つ複雑なデータベーススキーマを、情報過多に圧倒されることなく段階的に探索（Exploration）するために設計されたオープンソースの次世代 ERD ツールです。

全 70 テーブルを持つ `git-repo-db` の Core Store のような大規模スキーマでは、すべてのテーブルを一度にキャンバス上に並べると線が交錯して解読が難しくなりますが、Azimutt は **「関心のあるテーブルを検索して配置し、外部キーのリレーションを + ボタンで辿って必要なサブセットだけを展開・可視化する」** という極めて優れたワークフローを提供します。

#### 方法 A: Azimutt Web に SQL DDL をインポートする（最も手軽・推奨）

1. **正本 SQL DDL の出力**:
   ```bash
   scripts/local-run.sh python scripts/export_sqlite_databases.py
   ```
   `.build/databases/` に `catalog.sql`（Core 70テーブル）、`operational.sql`、`search.sql` が出力されます。
2. ブラウザで [**Azimutt Web** (https://azimutt.app/new)](https://azimutt.app/new) を開きます（アカウント不要で利用可能）。
3. プロジェクト作成画面で **「Import SQL」**（または SQLite）を選択します。
4. `.build/databases/catalog.sql`（または `operational.sql`、`search.sql`）をドラッグ＆ドロップまたは貼り付けます。
5. スキーマが即座に読み込まれます。

#### 方法 B: Azimutt Web に DBML をインポートする

1. [https://azimutt.app/new](https://azimutt.app/new) で **「Import DBML」** を選択します。
2. 本サイトからダウンロードした [core.dbml](core.dbml) などのファイルをアップロードまたは貼り付けます。

#### 方法 C: Azimutt Local Gateway によるローカル SQLite への直接接続

Azimutt 公式の CLI Gateway を使用すると、ブラウザ上の Azimutt からローカルの `.sqlite3` ファイルに安全に直接接続して探索できます：

```bash
# 1. データベースファイルをエクスポート
scripts/local-run.sh python scripts/export_sqlite_databases.py

# 2. Azimutt ゲートウェイを起動（npm または bun）
npx azimutt@latest gateway --allow-origin "https://azimutt.app"
```
ブラウザの Azimutt で「Database Connection」を選び、`sqlite://.build/databases/catalog.sqlite3` を指定することで、リアルタイムにスキーマを解析・可視化できます。

#### Azimutt でのおすすめの探索方法

- **テーブル検索**: キャンバス上部の検索バーに `stored_bytes` や `change_requests` と入力してテーブルをダブルクリック配置。
- **リレーション辿り**: テーブルノード上の外部キー列の横に表示されるバッジ（参照元・参照先テーブル数）をクリックすると、接続されたテーブルが自動的にキャンバスに展開されます。
- **マルチレイアウト**: 「Git DAG 構造」「Change Request & Review 構造」「CAS・整合性構造」などの目的に応じた複数のレイアウトを作成して切り替えられます。

---

### 6. ローカル VS Code で見る方法

外部クラウドサービスを使用せず、完全ローカルで DBML を閲覧・編集することも可能です：

1. VS Code の拡張機能マーケットプレイスで **`vscode-dbml`** または **`DBML ERD`** をインストール。
2. `documentation/schema/dbml/*.dbml` ファイルを開く。
3. エディタ右上の「プレビュー」ボタンをクリックすると、ローカルで ER 図が表示されます。

---

## スキーマ整合性検証

DBML の鮮度を検証します。事前に選択した製品ソースから完全な IR を生成してください。手順は [documentation/README.md](https://github.com/TakashiSasaki/git-repo-db/blob/main/documentation/README.md) を参照してください：

```bash
env -u UV_PROJECT_ENVIRONMENT uv run --project documentation --no-sync python documentation/tools/schema_viz.py --ir documentation/.build/inputs/inventory.json --check
```
