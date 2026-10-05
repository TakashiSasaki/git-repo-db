# コーディングエージェント向けガイド

このファイルはリポジトリ全体に適用する。ユーザーの最新の依頼と、変更対象に関係する設計書を確認してから作業する。

## 現在の状態と作業範囲

- `repo-catalog` は、Git構造・本文・GitHub PRと観測履歴をSQLiteへ保存し、取得元やcloneがなくても照会できるPython CLI。未リリースで、実行用DBはschema v2。
- 現在のハードニング工程は **独立P1 DDL・変換契約・synthetic検証まで**。本番用スキーマの置換、実データ変換、切替は未実施であり、この工程の完了に含めない。後続の依頼で実装範囲が拡大されたら、その範囲で進める。
- 調査基準は `9a4110185d7e7abffc291f9cfd118ca71587f998`。過去の結果を再利用する前に、作業ブランチ・HEAD SHA・基準との差分を確認し、検証記録へ残す。過去の件数やテスト成功を現在の証明にしない。
- 作業ブランチを使い、mainへ直接コミットしない。自動マージしない。既存のユーザー変更を上書きしない。

## 読むべき文書

まず [README.md](README.md) と [アーキテクチャ](docs/architecture.md) を読む。schemaハードニングでは次の順に読む。

1. [調査結果・再現条件・成果物の入口](docs/schema-hardening/README.md)
2. [不変条件と保証方法](docs/schema-hardening/invariants.md)
3. [新スキーマ案](docs/schema-hardening/schema-proposal.md)
4. [テーブル変換対応](docs/schema-hardening/table-conversion.md) と [全カラムの変換対応](docs/schema-hardening/column-conversion.csv)
5. [オフライン変換・検証・切替仕様](docs/schema-hardening/offline-conversion.md)
6. [実装順序・終了条件・未確定判断](docs/schema-hardening/implementation-plan.md)

[P1設計](docs/schema-hardening/p1-design.md)、[完全DDL](docs/schema-hardening/target-schema.sql)、[変換契約](docs/schema-hardening/conversion-contract.json)、[不変条件対応](docs/schema-hardening/invariant-contract.json)を新formatの正本とする。完全DDLは独立DB専用で通常migrationへ入れない。`proposal-core.sql`は中核断片の回帰検証用。converter/runtime接続はP2以降で未実装。

変更対象に応じて以下を参照する。

| 対象 | 文書・正本 |
|---|---|
| 現行v2の構造 | [データモデル](docs/data-model.md)、`src/repo_catalog/resources/migrations/001_initial.sql` と `002_repository_identity.sql` |
| リポジトリ識別・複数取得先 | [リポジトリ識別](docs/repository-identity.md) |
| CLI・公開JSON | [CLI仕様](docs/cli.md)、`src/repo_catalog/resources/schemas/cli-v1.schema.json` |
| cache・再開・backup/restore | [運用](docs/operations.md) |
| fixture・network guard・配布試験 | [検証方法](docs/testing.md)、`.github/workflows/tests.yml` |
| 過去の実装・pilot記録 | [実装状況](docs/implementation-status.md)。過去の検証範囲として読む |

現行挙動はコード・実構築したDDL・再現試験で確認する。旧文書の「番号付きmigrationの追記のみ」という方針は、今回の新format設計を制限しない。未リリースで旧アプリ・CLI・DBへの後方互換性は不要なため、初期DDL再編、分割・統合、改名、互換列削除も検討できる。ただし、旧DBのchecksum書換えで移行済みに見せることは禁止。

## リポジトリ構造と実装上の境界

| パス | 役割 |
|---|---|
| `src/repo_catalog/cli/` | argparse、表示、JSON envelope、終了コード、SIGINT変換 |
| `src/repo_catalog/application/` | collection/query/job/maintenanceサービス、repository identity、DTO/contracts/ports。PR照会は `pr_queries.py` |
| `src/repo_catalog/domain/` | 共通モデル・エラー |
| `src/repo_catalog/adapters/sqlite/` | `store.py` の接続・transaction・migration、`index.py` の検索索引 |
| `src/repo_catalog/adapters/git/` | Git実行、固定rootの解析、object・digest・本文の保存 |
| `src/repo_catalog/adapters/github/` | API transport、ページ収集、正規化、再開・watermark |
| `src/repo_catalog/adapters/filesystem/` | cache世代、lock、lease、容量予約・回収 |
| `src/repo_catalog/resources/` | packageへ同梱するmigration、GraphQL、CLI JSON schema |
| `tests/` | `unit` / `integration` / `e2e` / `packaging`、任意実行の `live`、合成fixtureの `support` |
| `scripts/` | offline demo、schema診断・対応表生成・索引probe |
| `docs/schema-hardening/` | 今回の設計と再現結果。実行用資源とは別 |
| `artifacts/` | ignoredのstate・テスト結果・非公開診断・配布物。ソース管理へ含めない |

- 依存方向は `cli → application → domain/ports`。adapterはapplicationから利用する。applicationをCLI実行や表示処理へ依存させない。
- coordinatorはwriter OS lockを持つ単一writer。HTTP・Git・hash・待機・stdout出力中にwrite transactionを保持しない。
- SQLiteはローカルfilesystemに置き、全接続でFKを有効にする。既定はDELETE/EXTRA。WALは設定とruntime gateを確認する。
- 通常照会はDB読取りのみ。通信・Git実行・自動migration・原文再取得を追加しない。FTSは派生候補索引であり、原文照合とscan補完を維持する。

## データ保全と新設計で守ること

- Repo IDは既存UUIDv4を原則維持する。URL、mount path、native ID、sourceは別概念。同じOIDや本文だけでfork/mirrorや別登録を統合しない。PR/MR番号はサービスbindingと種別のscopeで扱う。
- 同じrepo/PR/documentに属する関係、current pointer、公開状態を保証する。FKだけでは保証できない条件もあるため、[不変条件一覧](docs/schema-hardening/invariants.md)に沿ってCHECK、scoped FK/UNIQUE、trigger、アプリ・監査の担当を決める。
- 本文の重複排除と観測事実の保存を区別する。digestは共有候補でありexact bytesを照合する。別観測やA→B→Aの履歴を本文共有により消さない。
- 観測時刻と移行・再解析時刻、取得事実とjob/進捗を分ける。NULL、不正値、未知state、部分取得を黙って補正せず、completeへ格上げしない。未知の意味・由来はそのまま保全して診断する。
- Git OIDはobject formatと組で扱う。path/ref/tree名はraw bytes、commit parentは順序を保つ。Git OIDとraw Blob digestを混同せず、原文不在を空bytesで埋めない。固定本文profileやcoverageを暗黙に変更しない。
- 再利用対象は正規化テーブルに限定しない。保存API本文・ページ、未関連payload、観測履歴、残存Git object、未完了取得と再開情報も対応付ける。
- 変換は **別の新規DB** を第一候補とし、旧・新formatを明確に識別する。source DBと必要なcacheを変更・削除しない。ID変更・統合には追跡可能なmapを残す。
- 変換・再解析・索引再構築・検証はGitHub APIとネットワークgit fetchなしで完了させる。開発依存やリポジトリの準備は別工程。旧sync、`content hydrate`、cache GC、通常restoreをconverterの代用にしない。ローカルGit読取りでもlazy fetchを禁止する。
- 検証にはbytes・ID・関係・順序・観測・coverage・resume scopeを含める。表の件数一致や違反ゼロだけで保全を証明しない。実DBがなければfixtureを使い、実データで未検証の事項を明記する。
- 最初の同期で全件再取得へ戻らないよう、完了済み範囲、partial、watermark、validator、ページ/cursorと主体・API/profile scopeを保持する。移行中の通信で欠落を埋めない。
- 複数DB統合・双方向同期・変更配信、GitLab/Gitea MR/PR API adapterの全面実装は今回の範囲外。Git-onlyの複数取得先と区別する。

## 開発と検証

Python 3.12+、Git 2.43+、uvを使用する。PythonにリンクされたSQLiteにはSTRICTが必要。FTS5 trigramの有無は `doctor` と関連試験で確認する。

```bash
uv sync --locked --group dev
uv run --no-sync python scripts/prepare_wheelhouse.py
uv run --no-sync repo-catalog --format json doctor
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync pytest tests/unit tests/integration tests/e2e tests/packaging \
  --strict-markers -m "not live and not benchmark"
```

まず変更に関係する試験を実行し、runtimeやschemaに関わる変更では上記標準gateを通す。検証範囲と未実行項目を報告する。文書のみの変更では参照先・コマンド・diffを確認する。

- 標準試験は合成loopback API、dummy credential、Git file transportを使う。`tests/conftest.py` と子Python用network guardを無効化して実APIへ逃がさない。
- `live`/pilot/benchmarkは通常gateに含めない。実行範囲・認証・対象・容量・要求予算が依頼で定まっている場合に実行する。
- 梱包試験は新規venvへoffline導入するため、lock/SHA検証済みwheelhouseをonline準備する。`--offline --no-index --find-links`で実行し、registry metadata cacheへ依存しない。準備段階とoffline試験を区別し、キャッシュ不足をschemaテストの失敗や成功として扱わない。
- CLIのglobal optionはsubcommandより前に置く。変更系コマンドの検証には明示的な `--state-dir` と新規/空のfixture領域を使い、既定のユーザーstateや残存pilotを使わない。

### ハードニング専用ツールと試験

- `scripts/schema_audit.py --fixture-schema` は一時stateへ現行migrationを実適用して構造を抽出する。`--database SEALED_COPY --hash-payloads` は読取り専用診断。WAL/SHM/journal sidecarがあれば拒否するため、削除して回避しない。診断の限界は設計READMEを読む。
- `scripts/schema_design_catalog.py` はfixture inventoryと変換規則から `table-conversion.md`、`column-conversion.csv`、`source-access.json` を生成する。機械可読契約を修正し、`scripts/schema_contract.py --generate`で再生成してtarget/逆方向必須列/規則/依存/全旧列試験を通す。`current-schema.json` は実構築したfixture構造。`source-access.json` は字句検索であり完全なcall graphではない。
- `scripts/schema_index_probe.py` は使い捨て合成DB専用。`index-probe.json` の結果を実データの速度・容量見積りとして扱わない。
- `test_v2_hardening_reproductions.py` の3件は **現行不具合を確認するcharacterization test**。成功しても不具合修正済みではない。同一OIDの複数ref衝突、PR commit/file一覧の途中再開による観測分断、保存collection再利用時のwatermark前進を扱う。後続修正時は望ましい不変条件の試験へ更新する。
- `test_v2_schema_audit.py` は診断のreadonly性・不正所属等、`test_schema_proposal_core.py` は独立DDLの制約、`test_schema_design_catalog.py` は全カラム対応を検証する。

## 非公開データの扱いと引き継ぎ

実データのDB・API応答、実token・鍵・認証header、私的リポジトリ内容・識別情報をcommitや公開レポートへ含めない。試験には合成fixtureとdummy credentialを使う。credentialをURL・引数・設定へ埋め込まない。ignored領域も公開してよいとは限らないため、commit/PRのdiffと対象ファイルを確認する。

変更理由・確定した判断・検証したSHA/条件・未確定事項を関連設計書へ反映する。fixture検証、実DBのreadonly診断、実データ変換、切替は別の実績として報告し、次のエージェントが未実施工程を判別できる状態で引き継ぐ。
