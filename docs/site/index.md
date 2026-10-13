# git-repo-db 開発者ドキュメント

ようこそ、`git-repo-db`（`repo-catalog`）の開発者向け技術ドキュメントへ。

`git-repo-db` は、Git リポジトリおよび GitHub の Pull Request / Issue / Code データをローカルの SQLite データベースへ構造化・永続化し、オフライン環境で高速に横断検索・関係解析を可能にするデータベースエンジンおよび CLI ツールです。

---

## プロジェクト概要と解決する課題

### 解決する課題
GitHub API を利用した継続的分析やローカルでの詳細なコードレビュー履歴の検証には、以下の構造的課題が存在します：

1. **API レート制限とネットワーク依存**: 大規模リポジトリの Pull Request、コメント、レビュー履歴を都度 API で問い合わせると、レート制限の消費とレイテンシが発生し、オフラインや制限付き環境での再現性が失われます。
2. **Git オブジェクトと API 概念の断絶**: GitHub の Change Request（PR）や Review Thread と、基盤となる Git の Commit DAG、Tree、Blob オブジェクトが別々に扱われ、両者を統合した整合的クエリが困難でした。
3. **外部 DB サーバーの運用コスト**: PostgreSQL や MySQL などの重量級 RDBMS を必要とする設計では、ローカル開発環境や CI における軽量かつ決定論的な検証が困難になります。

### git-repo-db のアプローチ
`git-repo-db` は、**サーバーレスな SQLite** をストレージエンジンとして採用し、以下の設計原則に基づいて課題を解決します：

- **真実の複製（Truthful Capture）**: GitHub API の観測事実と Git Canonical Object（コミット、ツリー、ブロブ）を改変・捏造することなく忠実に記録。
- **Three-Store Boundary（3ストア物理分離）**: 永続的なドメイン事実、一時的な実行管理、再構築可能な検索インデックスを 3 つの SQLite データベースに物理分離（[ADR 0002](adr/0002-three-store-boundary-architecture.md)）。
- **完全オフライン対応**: 依存性のないスタンドアロン SQLite ファイルとして完結し、外部ネットワークなしで高度なクエリを実行可能。

---

## 現在の開発状況 (Development Status)

> [!IMPORTANT]
> **アクティブ開発中**: 本プロジェクトは継続的なアーキテクチャ刷新と検証の途上にあります。
> 
> - **現行スキーマバージョン**: 
>   - **Core Store**: Schema 21 (70 Product Tables, 121 Foreign Keys)
>   - **Operational Store**: Schema 1 (10 Product Tables, 9 Foreign Keys)
>   - **Search Store**: Schema 1 (4 Product Tables, 2 Foreign Keys)
> - **開発 CI とリリース受入の分離**: [ADR 0001](adr/0001-validation-lifecycle-architecture.md) に基づき、通常の PR / 開発コミットに対する軽量な静的・スモーク検査（Development Validation）と、完全な検証（Release Acceptance）は明確に区別されます。マージ済みの実装は自動的に「リリース受入完了」を意味するものではありません。

---

## 主要なアーキテクチャ概念

### 1. Three-Store Boundary (3つの物理ストア分離)
[ADR 0002](adr/0002-three-store-boundary-architecture.md)（結合決定 PF-P01〜PF-P17）により、単一の肥大化した SQLite データベースから以下の 3 つの物理ファイルへの完全分離が確立されています：

| ストア | 物理ファイル名 | スキーマ | テーブル数 | 主な責務と性質 |
|---|---|---|---|---|
| **Core Store** | `catalog.sqlite3` | Schema 21 | 70 | 永続的なドメイン事実、Identity、Change Request、Git DAG、CAS バイト列、Exchange 連携。バックアップ対象。 |
| **Operational Store** | `operational.sqlite3` | Schema 1 | 10 | ジョブ実行管理、試行回数、キャッシュリース、容量予約。揮発性・自動初期化可能。 |
| **Search Store** | `search.sqlite3` | Schema 1 | 4 | FTS5 仮想テーブル、再構築可能な検索プロジェクション。明示的 rebuild のみ、破損時は Core スキャンへフォールバック。 |

### 2. Publication-Independent Reconstruction
過去の Schema 20 で存在した機械的な `Publication` テーブル群やバンドルシール機構を全廃し、個別エンティティの原子性と `local_revision` カウンターに基づく独立した整合性モデルを採用しています。

---

## 主なドキュメントとツールへのナビゲーション

以下のリンクから、各機能や設計詳細に直接アクセスできます：

### データベーススキーマと可視化ツール
- 🔍 [**インタラクティブ スキーマビューアー**](schema/viewer/) (`/schema/viewer/`)  
  スタンドアロン HTML で動作するスキーマ探索ワークベンチ。Core / Operational / Search の 3 ストア切り替え、テーブル・カラム検索、外部キーのインタラクティブ辿り、SVG 近傍グラフ表示が可能。
- 📊 [**Mermaid ER ダイアグラム**](schema/mermaid/) (`/schema/mermaid/`)  
  Three-Store の全体俯瞰、Core モジュール別（Identity、Current State、Coverage、Git、CAS、Exchange）、Operational、Search の 10 種の ER 図。
- 📥 [**DBML エクスポートとダウンロード**](schema/dbml/) (`/schema/dbml/`)  
  `core.dbml`, `operational.dbml`, `search.dbml`, `combined.dbml` のダウンロードと解説。
- 📑 [**スキーマ概要とテーブル一覧**](schema/) (`/schema/`)  
  全 84 プロダクトテーブルの分類と外部キー制約の全体サマリー。

### アーキテクチャと設計決定
- 🏛️ [**全体アーキテクチャ概要**](architecture/) (`/architecture/`)  
  `cli -> application -> domain/ports -> adapters` のレイヤリングとデータフロー。
- 🧱 [**Three-Store Boundary アーキテクチャ**](architecture/three-store-boundary/) (`/architecture/three-store-boundary/`)  
  ADR 0002 および決定 PF-P01〜PF-P17 に基づく物理分離の詳細。
- 📜 [**Architecture Decision Records (ADRs)**](adr/) (`/adr/`)  
  - [ADR 0001: 開発・リリース検証ライフサイクル](adr/0001-validation-lifecycle-architecture/)
  - [ADR 0002: Three-Store Boundary アーキテクチャ](adr/0002-three-store-boundary-architecture/)

### 開発・テスト・コントリビューション
- 🛠️ [**開発およびテストガイド**](development/) (`/development/`)  
  環境構築（Python 3.12 / uv）、ローカル検証コマンド、変更対応 CI（Change-Aware CI）、ドキュメントサイトのビルド手順。
- 🐙 [**GitHub リポジトリ**](https://github.com/TakashiSasaki/git-repo-db)  
  ソースコード、Issue、Pull Request。
