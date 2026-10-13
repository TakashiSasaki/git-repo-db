# Three-Store Boundary アーキテクチャ詳解

`git-repo-db` のストレージ設計の中核を成すのが、**Three-Store Boundary（3ストア物理分離）** です。

本アーキテクチャは、リポジトリオーナーの合意決定（結合決定 **PF-P01〜PF-P17**）および [ADR 0002](../adr/0002-three-store-boundary-architecture.md) によって策定されました。

---

## 1. 物理分離の背景と動機

初期の `git-repo-db`（Schema 20 以前）は、ドメイン事実、ジョブの実行進捗、キャッシュリース、全文検索用の FTS5 テーブルをすべて単一の SQLite データベース（`catalog3.sql`）に混在させていました。

このモノリシック構成には以下の重大な運用上の問題がありました：
1. **バックアップとリストアの肥大化**: 永続化すべき不変のドメイン事実とともに、使い捨てのジョブ履歴や再構築可能な FTS5 インデックスがバックアップ対象に含まれていた。
2. **クラッシュ復旧の難易度**: 異常終了時に一時的なリースやジョブ状態が残存し、中核ドメイン事実のトランザクション回復と干渉した。
3. **FTS5 メンテナンスの干渉**: SQLite FTS5 のインデックス再構築に伴う大規模な書き込みロックが、ドメイン事実の読み書きトランザクションをブロックした。

これらを根本解決するため、**Core（中核ドメイン）**、**Operational（運用実行状態）**、**Search（検索派生データ）** の 3 つの SQLite ファイルへの物理分離が実施されました。

---

## 2. 3つのストアの責務とスキーマ配置

### 2.1 Core Store (`catalog.sqlite3`)
- **スキーマバージョン**: Schema 21
- **プロダクトテーブル数**: 70 テーブル
- **物理外部キー制約数**: 121 制約
- **バックアップ対象**: **はい**（唯一の正規バックアップ対象）
- **責務**:
  - すべての信頼できるドメイン事実（Domain Facts）、観測事実、エンティティ関係の保持。
  - Git DAG 構造（commits, trees, blobs, tags）および CAS ペイロード（生バイト列）。
  - GitHub Change Request、Review Thread、Issue リソースの最新状態および履歴。
  - カバレッジ範囲（Coverage Scopes / Claims）と取得完了マーカー。
  - Exchange ステージングと受け入れデータ。

### 2.2 Operational Store (`operational.sqlite3`)
- **スキーマバージョン**: Schema 1
- **プロダクトテーブル数**: 10 テーブル
- **物理外部キー制約数**: 9 制約
- **バックアップ対象**: **いいえ**（除外）
- **ライフサイクル**: 必要時に自動生成（PF-P12）。Core の `db_instance_id` にバインド。
- **責務**:
  - 非同期ジョブ（`jobs`）およびジョブ試行（`job_attempts`）の追跡。
  - トランスポートのキャッシュロケーター、アクティブエントリ、キャッシュリース、容量予約。
  - データ取得の進捗（`acquisition_progress`, `collection_progress`）。
  - インデックス再構築のパフォーマンス指標（`search_rebuild_metrics`）。

### 2.3 Search Store (`search.sqlite3`)
- **スキーマバージョン**: Schema 1
- **プロダクトテーブル数**: 4 テーブル
- **物理外部キー制約数**: 2 制約
- **バックアップ対象**: **いいえ**（除外）
- **ライフサイクル**: 明示的な `index rebuild` コマンドでのみ生成・更新（PF-P16, PF-P17）。
- **責務**:
  - 全文検索用 FTS5 仮想テーブル（`catalog_fts_<generation_id>`）。
  - 再構築可能な検索プロジェクション（`search_documents`）。
  - インデックス世代およびメンバーシップ管理（`index_generations`, `index_membership`）。

---

## 3. ストア間の結合度と論理依存関係

### 物理外部キーの境界規則
SQLite の物理外部キー制約（`REFERENCES`）は、**同一の SQLite ファイル内でのみ完結**します。データベースをまたいだ外部キー制約（例: `operational.sqlite3` から `catalog.sqlite3` への物理 FK）は一切存在しません。

### 論理依存関係（Logical Dependencies）
ストア間の関係性は、アプリケーションレベルで管理される明示的な論理依存関係としてモデル化されています：

1. **`operational_identity.catalog_db_instance_id` -> Core `database_identity.db_instance_id`**  
   Operational DB がどの Core Catalog に属しているかを厳格に識別。異なるカタログでの誤用を防止（PF-P11）。
2. **`search_identity.catalog_db_instance_id` -> Core `database_identity.db_instance_id`**  
   Search DB の所有カタログを識別。
3. **`jobs.source_uuidv4` -> Core `sources.source_uuidv4`**  
   ジョブが対象とする Source の UUID。
4. **`search_documents.document_identity` -> Core 各種ドキュメントエンティティ**  
   検索対象のドメインエンティティへの参照。

これらの論理依存関係は、インタラクティブスキーマビューアーにおいて破線（Dashed Line）および論理バッジとして明確に区別して表示されます。

---

## 4. 障害と復旧モデル（Failure & Recovery Model）

| 障害シナリオ | 動作・影響 | 復旧・回復手順 |
|---|---|---|
| **Operational DB 欠落** | 運用操作実行時に、現在の Core `db_instance_id` にバインドされた新しい Operational DB を自動生成（PF-P12）。Core の読み取り操作は影響を受けずに継続動作。 | 自動回復（追加操作不要）。 |
| **Operational DB 破損** | フェイルクローズ（`DATABASE_CORRUPT` または `WRONG_CATALOG_OWNER`）。ファイルを暗黙的に削除・上書きしない。 | 管理者が破損ファイルを手動削除またはリネーム後、再実行で新規生成。 |
| **Search DB 欠落** | 検索リクエストは直ちに **Core データの直接スキャンにフォールバック**（PF-P15）。エラーで異常終了しない。 | 管理者が明示的に `index rebuild` を実行して再生成。 |
| **Search DB 破損 / 不整合** | インデックス経由の検索が失敗した場合、直ちに Core 直接スキャンにフォールバックし、診断メッセージ（`stale_or_corrupt_index`）を出力。 | 管理者が明示的に `index rebuild` を実行。 |
| **書き込み中断（クラッシュ）** | Core へのコミットは単一トランザクションで原子的。直後の Operational への記録更新がクラッシュで失われても、Core のドメイン事実は確定。 | 次回実行時に未完了ジョブとして安全に再取得。状態の捏造は行わない。 |
| **バックアップとリストア** | バックアップは `catalog.sqlite3` のみを含む（PF-P08）。 | リストア時は Core を配置し、Operational DB は初回起動時に空で自動生成。Search DB は必要に応じて `index rebuild` で再構築。 |

---

## 5. 設計決定レジスタ（PF-P01〜PF-P17 サマリー）

- **PF-P01**: 後続のインベントリにないリポジトリを直ちに除外しない（既知の正の関連性を維持）。
- **PF-P02**: 過去の API 収集リスト全体の無制限な遡及クエリは不要。
- **PF-P03**: インクリメンタル取得は最適化であり、基準が無効なら安全なフル取得へフォールバック。
- **PF-P04**: ジョブ再開はベストエフォート。文脈が失われた場合は安全な新規取得を行う。
- **PF-P05**: 本タスクではドメインテキストの自動 GC は実装しない（追記型を維持）。
- **PF-P06**: 運用状態をコア DB から物理分離（Core と Operational の分離）。
- **PF-P07**: コアと運用の間で分散 2 相コミットを行わない（Core の原子性を優先）。
- **PF-P08**: 通常のバックアップはコア DB のみを含む。
- **PF-P09**: HTTP キャッシュはトランスポート層のアダプターに属し、Core に持ち込まない。
- **PF-P10**: ドメイン属性は具体的な必要性に基づいてのみ型と来歴を明示して追加する。
- **PF-P11**: 各コア Catalog は専用の Operational DB を 1:1 で所有し、共有しない。
- **PF-P12**: 欠損した Operational DB は必要時に自動生成するが、破損時は暗黙削除せずフェイルクローズ。
- **PF-P13**: ジョブ履歴の自動 TTL 削除は行わず、管理者が明示的に保守する。
- **PF-P14**: 各 Catalog は FTS5 用に専用の Search DB を分離所有し、バックアップから除外する。
- **PF-P15**: Search DB が利用不能な場合は Core データの直接スキャンに安全にフォールバックする。
- **PF-P16**: 検索インデックスの更新・再構築は明示的な操作によってのみ実行する。
- **PF-P17**: 通常の読み取りや検索クエリが Search DB の作成・置換・修復を行わない。
