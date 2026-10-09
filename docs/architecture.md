# アーキテクチャ

> **次期スキーマの確定方針（未実装）:** [通信原本非依存のコアDBとParser由来情報の簡素化](transport-independent-core-adr.md)を参照してください。API通信原本のコア永続保存・再解析依存とParser選択DAGを廃止する方針を固定しています。リソースの履歴／現行状態のライフサイクルは未決定です。以下は引き続き現行Schema 16の説明です。

依存方向は`cli → application → domain/ports`です。Git/GitHub/SQLite/filesystem adapterはapplicationから利用します。
CLIはargparse、presentation、終了コード、SIGINTの変換を担当します。
applicationは収集、照会、job、保守を担当し、terminalやHTTP handlerへ依存しません。

`CollectionRequest`、`QueryRequest`、`SearchQuery`、`PageRequest`をサービス入口に利用できます。
`QueryService.execute(request)`はCLIなしで使用でき、結果、coverage、page、実行状態を返します。
CLIが共通JSON envelopeと終了コードへ変換します。

```python
from repo_catalog.application.contracts import SearchQuery, PageRequest
from repo_catalog.application.query_service import QueryService

result = QueryService("/path/to/state").execute(
    SearchQuery(kind="code", literal="認証", page=PageRequest(limit=100))
)
```

初版のcoordinatorはforegroundでstateのwriter OS lockを保持し、SQLite更新接続を所有します。
Git/APIの処理は現在直列です。HTTP、Git、hash、待機、stdout出力中にwrite transactionを保持しません。
将来のWeb adapterは同じDTO/serviceを呼び、CLIのshell実行や複数Web workerの独立writerを導入しません。

Git snapshot順序、物理cache generation、job attemptは別に管理します。
Git fetchはrun固有namespaceへ取得し、解析対象のrootを固定します。
immutable objectを小transactionで保存し、必要な構造・digest・本文の保存後に不変の公開・選択記録を追加します。
古いrunの正当な再開は履歴として公開でき、現在採用する解析結果は明示選択とそのDAGから導出します。

PRの文書ページは独立して公開し、collection終端、watermark、コード対応の完了を分離します。
通常Issue/コメントとレビュー/レビューコメントは、各リソースの最新受理状態を共有物理テーブルへ保存します。PRタイトル・本文・PR会話コメントとGit・独立スレッドの観測履歴は維持します。
検索は原文literalが正本です。contentless trigram FTSは候補検索に使い、原文で最終照合します。
索引が欠落・未索引・利用不能ならscanで補完します。

SQLiteはローカルfilesystemに置きます。既定DELETE/EXTRA、全接続foreign_keys=ON、有限busy_timeoutです。
WALは明示設定かつ修正済みruntimeのgateを通した場合のみ有効にできます。


通常の初期化・収集・照会・保守は catalog3 の同じ packaged schema を共有します。読み取りは `mode=ro` と通常の SQLite transaction snapshot を使い、変更中の DB に `immutable=1` を指定しません。derived FTS/statistics は format identity を変更せず、照会のたびに全 schema/source archive を hash 検証しません。

旧v2 importerとfinalizeは廃止済みです。初期化は新規catalogを直接作成し、通常操作は変換workspaceを開きません。D2は `not_applicable / retired` ですが、不明なidentityや観測時刻を捏造しない契約は維持します。歴史的なreceiptは現行ランタイムの前提ではありません。

Active catalog3 schema identity is version **16**. [Data model](data-model.md) and [schema composition](../src/repo_catalog/adapters/sqlite/schema.py) define portable UUIDv4 service namespaces, natural resource keys, SHA-256 text identity and signed integer epoch microseconds. Historical documents have no surrogate ID or version table. Composite FK ownership and explicit historical selection remain enforced. There is no development-database migration or compatibility layer.

## 現在状態と通信記録の境界

`issue_resources` は通常Issueとコメント、`review_resources` はレビュー概要とレビューコメントの共有ストアです。local収集とexchangeは同じ受理処理を使います。同一内容は冪等に扱い、比較可能なprovider更新時刻など順序の証拠がある場合だけ差分を受理します。順序不明の差分・未到着の親は診断/stagingへ保存し、競合を確定した最新状態として表示しません。`observed_at_us`、`last_checked_at_us`、`provider_updated_at_us`、`parsed_at_us` はそれぞれ観測、確認、provider更新、解析の時刻です。

同じ行の `field_evidence_json` は、現在値とmetadataの各pathに取得時刻・clock・profile・scopeを対応付けます。未提供の値は元の根拠を保持し、古い完全応答の後着で未観測項目を補完できます。同時刻に実際に観測した異なる値は競合のままです。根拠mapは保持中の項目数に対応し、以前の値や編集回数に応じた履歴行を追加しません。同内容でも強い根拠が届けば競合を再評価します。

現在のIssue所属と取得時のscopeは独立しています。移動時は子のrepository/binding/番号だけを更新し、元endpoint・Source・取得時刻・項目別根拠を保持します。交換先に移動元の登録がない場合も、取得scopeの識別子をsnapshotとして保存します。実在する登録との整合性は検査します。`last_checked_at_us` は事前revisionとscopeが一致した正常live取得の初回・編集・同内容確認で進み、import/replayは受信側の確認時刻を作りません。

可変現在行は、不変 `parsed_results` の封印された出力には所属しません。正確な本文、型付き親、repository/service/bindingと検証済みparser/profileへの帰属はdomain datastoreに残します。レビュー所属・返信先・独立スレッド所属は別々の関係です。code listingに必要な不変参照は固定し、後のレビュー編集で以前のGit/code snapshotを変更しません。

HTTP transportは `MessageRecorder` へ補助記録を渡し、recording adapterが保存とarchive読取りを所有します。`github.record_messages` は既定でfalse、有効時は `transport-archive/` を利用します。recorder障害は許可された32文字以下のコード、観測時刻、試行番号だけを診断へ渡し、transport内で最新100件を保持します。警告表示はbest-effortで、warnings-as-errorsや表示hookの失敗でも正常応答の解析・domain保存を続けます。取消し・通信・解析・必須domain証拠の失敗は通常どおり扱います。記録するbytesはHTTP content-decoding後の正確なbytesです。資格情報を除くメタデータ許可リストと読取り上限は[通信記録](latest-state-transport.md)に記載しています。

現在状態のcollectionは、取得scope、ページ順、メンバーidentity/digest、次ページと終端の最小限の不変証拠をdomain側へ保存します。補助archiveの有無はcollection完全性を変えません。Exchangeとbackup/restoreもarchiveを必須依存に含めません。保存メッセージのinspect/reparseは明示選択したbytesを読むだけで、元の観測時刻を保持し、domain状態を自動受理しません。

Coverage claims are immutable evaluations identified by scope, observation time and state. Domain helpers define admission and derivation; SQLite performs admission atomically and derives `current_coverage` from the latest-time claim set. Unknown is weak only within that selected time; disagreement among determinate states yields a derived conflict. Runtime producers preserve actual source observation times across replay and keep job execution state separate. Query adapters return the derived scope with each selected claim and its own advisory details. See the [coverage contract](data-model.md#coverage-claims-and-current-state).

構造変更は[対応記録](current-state-schema-closure.md)、[列の用途](current-state-schema-liveness.md)と[完全schema一覧](current-state-schema-inventory.md)、設計決定と旧契約の適用範囲は[実装対応表](latest-state-transport-implementation.md)を参照してください。最終受入は実装完了後の正確なtreeに対する試験で判定し、過去の合格receiptとは区別します。
