# アーキテクチャ概要 (Architecture Overview)

`git-repo-db` は、Git リポジトリおよび GitHub API から取得したデータを、高信頼かつ高効率に SQLite へ格納し、オフラインで自由なクエリを可能にするシステムです。

本ドキュメントでは、実装済み通常ランタイムの基盤（**Core Schema 21 / Operational Schema 1 / Search Schema 1**）と各コンポーネントの責務を解説します。採択された目標設計と、実装・起動時の動作は別々に確認します。

[ADR 0029](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/docs/adr/0029-independent-access-store.md) の採択設計には Core、Context、Access、Operational、Search の５つの責務境界があります。[P1 ファクトリー](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/src/repo_catalog/adapters/sqlite/p1_schema.py) の４項目はその部分集合で、Access は[別の opt-in ファクトリー](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/src/repo_catalog/adapters/sqlite/access_schema.py)です。

通常のカタログ `init` とは別に、[Access ワークフロー](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/src/repo_catalog/cli/access_workflow.py)と[取得用](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/src/repo_catalog/cli/access_acquisition.py)の opt-in CLI モジュールがあります。

通常の `init` は [初期化処理](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/src/repo_catalog/application/maintenance_service.py) で１つの Core カタログを作成します。[Store の実装](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/src/repo_catalog/adapters/sqlite/store.py)では Operational は必要時に開かれ、Search の作成は明示的です。これらはこの起動経路の説明であり、既存の利用者データベースの数や全構成の上限を示すものではありません。

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

## 2. 通常ランタイムの Three-Store 基盤

[ADR 0002](../adr/0002-three-store-boundary-architecture.md) に由来する通常ランタイムの実装では、Core、Operational、Search のそれぞれに独立した SQLite スキーマがあります。ファイルは実行経路に応じて作成・オープンされ、通常の初期化では Core のみを初期化します。

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
> リポジトリ内に残存する過去の記録（`docs/architecture.md` や `docs/data-model.md`）には、旧来の単一モノリシック設計（Schema 20 / 69〜71テーブル）に関する記述が含まれています。これらはリポジトリに保持された設計変遷の検証証跡（Historical Evidence）であり、**現在の動作仕様ではありません**。

履歴文書: [旧 CLI](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/docs/cli.md)、[旧データモデル](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/docs/data-model.md)、[実装監査](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/docs/implementation-status.md)、[過去の判断対応表](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/docs/model-integration-status.md)。現行ランタイム案内はリポジトリ内の `documentation/current-runtime-reference.md` にあり、このサイトへのコピーは公開対象に含めていません。サイトの文書 revision はトップページ末尾で確認できます。

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
- **CAS と Git 完全性**: この通常基盤には保持内容の整合性検査と履歴的な `payload_quarantine` 表現があります。採択済みの復旧目標は [ADR 0026](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/docs/adr/0026-stop-salvage-restore-merge-after-corruption.md) の停止・保全・新規復元・検証済みマージであり、隔離解除を新たな目標として扱いません。通常ファイル本文の新規アーカイブは [ADR 0014](https://github.com/TakashiSasaki/git-repo-db/blob/5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d/docs/adr/0014-history-and-notes-catalog-without-file-archive.md) で対象外です。
