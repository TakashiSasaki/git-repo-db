# Architecture Decision Records (ADRs)

本ディレクトリには、`git-repo-db` の重要なアーキテクチャおよびインフラ方針を決定した **Architecture Decision Records (ADR)** が格納されています。

各 ADR は、課題の背景、検討された選択肢、および最終的に採択された設計方針を記録した**公式かつ権威ある設計合意**です。

---

## 採択済み設計決定 (Accepted Records)

| ADR | タイトル | 決定日 | ステータス | 概要 |
|---|---|---|---|---|
| [**ADR 0001**](0001-validation-lifecycle-architecture.md) | Development and Release Validation Lifecycle Architecture | 2026-10-12 | Accepted target design | 開発時の軽量ローカル検証（Development Validation）と、明示的なリリース受入（Release Acceptance）の分離。CI 実行時間最適化と証跡契約の策定。 |
| [**ADR 0002**](0002-three-store-boundary-architecture.md) | Three-Store Boundary Architecture (PF-P01–PF-P17) | 2026-10-12 | Accepted target design | 3ストア（Core, Operational, Search）への物理分離、障害復旧モデル、バックアップ境界の策定。結合決定 PF-P01〜PF-P17。 |

---

## 決定権限の階層ルール

リポジトリ全体の開発およびエージェントの作業指示において、決定の優先順位は以下のように定められています（`AGENTS.md`）：

1. **明示的な現在のオーナー指示（Current Owner Decisions）**
2. **採択済み ADR およびスコープを明示した上位決定（Accepted ADRs）**
3. **未改定の本番契約（Unsuperseded Production Contracts）**
4. **過去の検証証跡・報告書（Historical Evidence）**

過去の設計報告書や古いスキーマ図面と現在の ADR が矛盾する場合、**採択済み ADR が優先**されます。
