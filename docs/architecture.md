# アーキテクチャ

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
immutable objectを小transactionで保存し、必要な構造・digest・本文の保存後に公開pointerを切り替えます。
古いrunの正当な再開は履歴として公開できますが、新しいcurrent pointerを巻き戻しません。

PRの文書ページは独立して公開し、collection終端、watermark、コード対応の完了を分離します。
検索は原文literalが正本です。contentless trigram FTSは候補検索に使い、原文で最終照合します。
索引が欠落・未索引・利用不能ならscanで補完します。

SQLiteはローカルfilesystemに置きます。既定DELETE/EXTRA、全接続foreign_keys=ON、有限busy_timeoutです。
WALは明示設定かつ修正済みruntimeのgateを通した場合のみ有効にできます。


通常の初期化・収集・照会・保守は catalog3 の同じ packaged schema を共有します。読み取りは `mode=ro` と通常の SQLite transaction snapshot を使い、変更中の DB に `immutable=1` を指定しません。derived FTS/statistics は format identity を変更せず、照会のたびに全 schema/source archive を hash 検証しません。

v2 救出は専用 guarded child process で typed archive と domain recipe を atomic batch に保存する一つの importer です。歴史的な phase receipt と predecessor compatibility はランタイムの前提ではありません。`db finalize` は保存された current assertion と同じ owner の公開事実を検査し、readiness decision を target 内へ記録します。

Active catalog3 schema identity is version 5. [Data model](data-model.md) is the current identifier contract: portable UUIDv4 service namespaces, natural document keys and observations pointing directly to SHA-256 text identity. Documents have neither a surrogate ID nor a version table. Composite FK ownership and explicit current-observation selection are retained. There is no old-catalog3 migration or alias layer.
