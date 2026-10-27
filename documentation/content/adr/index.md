# Architecture Decision Records (ADRs)

この公開ページは ADR 0001・0002 の限定された概要です。すべての採択済み決定を一覧するものではありません。現行の状態、適用範囲と後続決定は[リポジトリの ADR 正本索引](https://github.com/TakashiSasaki/git-repo-db/blob/main/docs/adr/README.md)を参照してください。

各 ADR は、課題の背景、検討された選択肢、および最終的に採択された設計方針を記録した**公式かつ権威ある設計合意**です。

---

## 公開されている基盤記録の概要

| ADR | タイトル | 決定日 | ステータス | 概要 |
|---|---|---|---|---|
| [**ADR 0001**](0001-validation-lifecycle-architecture.md) | Development and Release Validation Lifecycle Architecture | 2026-10-12 | Accepted target design | 開発時の軽量ローカル検証（Development Validation）と、明示的なリリース受入（Release Acceptance）の分離。CI 実行時間最適化と証跡契約の策定。 |
| [**ADR 0002**](0002-three-store-boundary-architecture.md) | Three-Store Boundary Architecture (PF-P01–PF-P17) | 2026-10-12 | 歴史的基盤・一部置換 | 配置とフルバックアップは採択済み [ADR 0029](https://github.com/TakashiSasaki/git-repo-db/blob/main/docs/adr/0029-independent-access-store.md) による後続決定を参照。その他の未置換条項は維持。 |

---

## 決定権限の階層ルール

リポジトリ全体の開発およびエージェントの作業指示において、決定の優先順位は以下のように定められています（`AGENTS.md`）：

1. **明示的な現在のオーナー指示（Current Owner Decisions）**
2. **採択済み ADR およびスコープを明示した上位決定（Accepted ADRs）**
3. **未改定の本番契約（Unsuperseded Production Contracts）**
4. **過去の検証証跡・報告書（Historical Evidence）**

過去の設計報告書や古いスキーマ図面と現在の ADR が矛盾する場合、**採択済み ADR が優先**されます。
