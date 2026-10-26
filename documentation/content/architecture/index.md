# アーキテクチャ概要 (Architecture Overview)

`git-repo-db` は、Git リポジトリおよび GitHub API から取得したデータを、高信頼かつ高効率に SQLite へ格納し、オフラインで自由なクエリを可能にするシステムです。

本ドキュメントでは、最新のアーキテクチャ（**Core Schema 21 / Operational Schema 1 / Search Schema 1**）に基づくシステムの全体設計、依存関係の方向性、および各コンポーネントの責務を解説します。

---

## 1. 設計原則とレイヤー依存関係

システムの依存関係は、オニオンアーキテクチャ / ポーツ＆アダプター（Hexagonal）パターンに従い、内側に向かって厳格に一方向です：

```
cli  -->  application  -->  domain / ports  <--  adapters (sqlite, git, http)
```

- **`cli`**: コマンドライン引数の解釈、環境検証（doctor）、出力フォーマット（JSON / 人間可読）を担当します。
- **`application`**: ユースケースの調整、トランザクション境界、複数ポートの協調動作を管理します。
- **`domain / ports`**: 中核となるビジネスエンティティ、不変条件、インターフェース規約を定義します。外部ライブラリや永続化メカニズム（SQLite、Git、HTTP）に依存しません。
- **`adapters`**: ポーツの実装。
  - `adapters/sqlite`: 厳密な SQLite DDL 組成、トランザクション、JSON ガード、整合性トリガー。
  - `adapters/git`: ローカル Git リポジトリのオブジェクト（Commit, Tree, Blob）直接読み出しと検証。
  - `adapters/http`: GitHub REST / GraphQL API との通信（レート制限遵守・トランスポート）。

---

## 2. Three-Store Boundary (3ストア物理分離)

[ADR 0002](../adr/0002-three-store-boundary-architecture.md) で合意された設計により、ストレージは単一の巨大データベースではなく、責務の異なる 3 つの SQLite データベースファイルに物理的に分離されています。

```
+--------------------------------------------------------------------------+
|                            git-repo-db State                             |
+--------------------------------------------------------------------------+
                                    |
     +------------------------------+------------------------------+
     |                              |                              |
     v                              v                              v
+-------------------------+  +--------------------------+  +-------------------------+
|   catalog.sqlite3       |  |   operational.sqlite3    |  |   search.sqlite3        |
|   (Core Store)          |  |   (Operational Store)    |  |   (Search Store)        |
|                         |  |                          |  |                         |
| - Schema 21             |  | - Schema 1               |  | - Schema 1              |
| - 70 Product Tables     |  | - 10 Product Tables      |  | - 4 Product Tables      |
| - 121 Foreign Keys      |  | - 9 Foreign Keys         |  | - 2 Foreign Keys        |
| - 永続ドメイン事実      |  | - 一時的実行状態         |  | - FTS5 仮想テーブル     |
| - Git DAG / CAS         |  | - ジョブ・キャッシュ     |  | - 再構築可能            |
| - バックアップ対象      |  | - 自動初期化可能         |  | - 明示的 rebuild        |
+-------------------------+  +--------------------------+  +-------------------------+
```

詳細な分離規則、ストア間の整合性モデル、およびフォールバック設計については、[Three-Store Boundary アーキテクチャ詳解](three-store-boundary.md) を参照してください。

---

## 3. 過去の Schema 20 と現行アーキテクチャの相違点

> [!IMPORTANT]
> **歴史的ドキュメントに関する注意事項**:
> リポジトリ内に残存する過去の記録（`docs/architecture.md` や `docs/data-model.md`）には、旧来の単一モノリシック設計（Schema 20 / 69〜71テーブル）に関する記述が含まれています。これらは設計変遷の検証証跡（Historical Evidence）として Git 履歴に保存されているものであり、**現在の動作仕様ではありません**。

現行アーキテクチャ（Core Schema 21 + Operational Schema 1 + Search Schema 1 = 計 84 テーブル）における主要な変革：

1. **Publication 機構の完全撤廃 (NO_INDEPENDENT_PUBLICATION)**:
   - 旧設計に存在した `publications`, `publication_bundles`, `publication_seals` などの出版管理テーブルを廃止。
   - エンティティごとの原子的コミットと、受信側ローカルカウンター `local_revision` によるシンプルな順序保証へ刷新。
2. **物理分離の実現**:
   - バックアップ時に不要な一時ジョブデータ（`jobs`, `job_attempts`）を `operational.sqlite3` に分離。
   - 肥大化する FTS5 インデックスおよび派生テーブルを `search.sqlite3` に分離。
3. **安全なフォールバック**:
   - `search.sqlite3` が存在しない、あるいは破損している場合でも、Core データの直接スキャンにより検索処理を継続（フェイルクローズではなく安全な縮退動作）。

---

## 4. データ整合性と安全性の保証

- **外部キーと再帰トリガー**: 全接続で `PRAGMA foreign_keys = ON;` および `PRAGMA recursive_triggers = ON;` を必須化。
- **物理外部キーの境界厳守**: SQLite の物理外部キー制約は、同一データベースファイル内でのみ閉じています。ストア間（Core と Operational、Core と Search）の参照は非制約の論理依存関係（Logical Dependency）として扱い、セカンダリ DB の破損や欠損が Core の整合性を破壊しない構造を維持しています。
- **CAS（Content-Addressable Storage）と Git 完全性**: Git オブジェクトの生バイト列は Git Canonical Object Format（ヘッダー + サイズ + ナル文字 + ペイロード）に従って検証され、ハッシュが一致する場合のみ格納されます。不正なバイト列は `payload_quarantine` テーブルに隔離されます。
