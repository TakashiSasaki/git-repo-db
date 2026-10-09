# CLI契約

共通指定は`--state-dir PATH --format table|json --timeout-seconds N`をsubcommandより前へ置きます。
stateの既定は`$XDG_STATE_HOME/repo-catalog`、未設定時は`~/.local/state/repo-catalog`です。
JSON modeのstdoutは結果専用です。public schemaは同梱`resources/schemas/cli-v1.schema.json`です。

| 分類 | コマンド |
|---|---|
| 初期化・診断 | init、doctor |
| 収集元・収集 | sources add、discover、sync git/pr/issue/all |
| サービス・接続 | instances add/list/show、endpoints add/list/prefer、repos bind |
| job | jobs list/show/resume/cancel |
| DB | db check/verify-payloads/repair-payload/backup/restore |
| cache・索引 | cache status/gc、index rebuild |
| Git照会 | repos list/show、snapshots list/show、refs list、tree list、file show、commits list/show/compare |
| 検索 | search path/code/commits/hash/pr/issue |
| PR照会 | pr list/show/documents/thread/timeline |
| 通常Issue照会 | issue list/show/comments |
| parser・補助通信 | parser status/register/verify/trust/invalidate/select-profile/select-fact/reparse/admit-decision/inspect-message/reparse-message |
| 交換 | exchange export/import/staging |
| 原文 | content show/hydrate |
| 状態 | coverage、status |
| 独立target照会 | target repos/commit/tree/file/pr/search |

各コマンドの引数は`repo-catalog COMMAND --help`または`repo-catalog COMMAND ACTION --help`で確認できます。
repo selectorはUUIDv4、一意な名前、host/owner/name、instance名/repo名です。曖昧な指定は拒否します。
複数repo対応の検索/syncは`--repo`を繰返せます。省略または単独allは登録済みrepo全件です。
OIDは`sha1:<40 hex>`または`sha256:<64 hex>`、refは完全名を指定します。

`sources add git-url --name NAME --url URL`は`local-git`の別名で、HTTPS/SSH/SCP/file URLとローカルpathを扱います。
`--repo REPO_ID`により既存repoへ明示的に結び付け、`discover --source SOURCE_ID`で対応とendpointを登録します。
`--instance INSTANCE --provider-repo-id NATIVE_ID`によりサービス内識別を指定できます。native IDの指定にはinstanceが必要です。
GitHub API sourceは`--instance INSTANCE`と`--token-env-var ENV_NAME`を指定でき、秘密値は保存しません。
`repos list/show --source SOURCE_ID`は追加sourceから見つかった既存repoも対象にします。
`endpoints add --repo REPO_ID --url URL [--label LABEL] [--preferred]`、`endpoints prefer --repo REPO_ID --endpoint ENDPOINT_ID`で取得先を管理します。
`sync git/pr/issue/all --repo REPO_ID --endpoint ENDPOINT_ID`はそのrepoの取得先を明示し、複数repo指定との組合せを拒否します。
操作例は[リポジトリ識別と取得先](repository-identity.md)を参照してください。

`sync issue` は通常Issueのopen/closedと各コメント、`sync all` はGit・PR・通常Issueを収集します。Issues APIに含まれるPRは通常Issueから除外し、PR会話コメントには従来の履歴保存を適用します。

```bash
repo-catalog --state-dir /tmp/disposable-catalog sync issue --repo REPO_ID
repo-catalog --state-dir /tmp/disposable-catalog issue list --repo REPO_ID --state closed
repo-catalog --state-dir /tmp/disposable-catalog issue show --repo REPO_ID --provider-issue-number 7
repo-catalog --state-dir /tmp/disposable-catalog issue comments --repo REPO_ID --provider-issue-number 7
repo-catalog --state-dir /tmp/disposable-catalog search issue --repo REPO_ID --literal 'saved text'
```

Issue show/commentsは一つのrepoと `--provider-issue-number` または `--provider-resource-id` を指定します。番号がbinding間で曖昧な場合は `--binding BINDING_UUID` で区別します。`--source`、`--state all|open|closed`、`--author`、`--document-author`、`--parser-profile` で選択を絞れます。Issueの恒久識別はserviceとprovider IDで、現在のrepo番号とは別です。各Issue/commentの最新受理本文を返し、競合・未到着親・profile不適格をpartialとして公開します。

`current`は全heads先端、`history`は選択snapshotのheads/tagsから到達する履歴、`recorded`は過去の公開rootも含みます。
PR rootはhistory/recordedで`--pr`または`--ref-kind pr-head|pr-related`により明示します。
PR rootとsnapshot、recordedとsnapshot等の不正な組合せは拒否します。

literalはcase-sensitiveで、Unicode正規化や改行/Markdown変換をしません。
UTF-8 byte offsetは0始まり・終端非包含、lineはLF区切り・1始まりです。コミットメッセージは正本bytesで照合し、message_b64とraw byte offsetを返します。非UTF-8部分の置換表示を一致とは扱いません。
raw pathの正本はpath_b64で、UTF-8不正時のpath_utf8はnull、安全表示はpath_displayです。
`search path --path-b64 BASE64`と`file show --path-b64 BASE64`により任意のraw pathを指定できます。`file show --repo REPO_ID --commit sha1:HEX --path PATH`は保存textと原文の有無を返し、未保存のbodyはnullとpartial coverageになります。

PR検索はtitle/body/issue-comment/review/review-commentを区別します。
PR番号は `--provider-change-request-number`、種別は `--change-request-kind pull_request|merge_request` で指定します。正規化された結果でも `provider_change_request_number` と `change_request_kind` を使い、raw payload 内のprovider固有キーは変更しません。
`pr thread` は `--repo REPO_ID --provider-change-request-number NUMBER --provider-resource-id PROVIDER_RESOURCE_ID` でChange Requestを先にscopeし、その中のreview threadを選択します。`provider_resource_id` 単独のprovider全体一意性は仮定しません。選択threadのコメント一覧の終端を保存証拠から確認できない場合は、保存済み本文がすべて存在してもpartialになります。
`--document-observations current|all` はPR title/body/PR会話issue-commentの現在採用観測と保存済み全観測を選びます。既定は `current` です。review/review-commentはどちらの指定でも各リソースの最新受理状態です。レビュー編集前の本文は通常検索に出しません。
`--document-kind` と `--provider-change-request-document-id` で文書自然キーの構成要素を指定でき、`--observation INTEGER` で保存観測を選択します。
PR履歴文書の結果は `document_kind`、`provider_change_request_document_id`、`document_observation_id`、`text_body_sha256`、`document_observed_at_us`、`document_current_selected` 等を返します。current-stateの結果はprovider更新/観測/最終確認/解析時刻とparser/profile帰属を持ち、履歴観測の代替IDを捏造しません。Issue系は `resource_kind`、`provider_resource_id`、`provider_issue_number` を使います。詳細は[application JSON契約](application-json-contracts.md)を参照してください。
`last_checked_at_us` は受信側で事前revision/scopeが一致した正常live取得の最終確認です。初回・編集・同内容確認で更新し、import/replayでは進みません。部分取得の未提供値は元の根拠を保持し、後着した古い完全応答が未知の項目を補完できます。Issue移動後の現在repo/番号と元の取得scopeは別に保持します。項目別根拠の保存契約は[データモデル](data-model.md#shared-latest-state-resources)を参照してください。
取得開始前や観測間の未観測編集、非公開/削除済みで取得不能な履歴は保証しません。

list/searchは`--limit`（既定100、上限1000）と`--cursor`を持ちます。
ページが続くことと取得範囲がpartialであることは別です。
PR照会の完全性は、同じ読み取りスナップショット内で要求したrepository・PR番号・種別・bindingの範囲を評価し、返却ページの切り出しから独立させます。`--limit`、返却バイト数、cursorの位置によって完全性の判定は変わりません。未保存の情報が検索条件に一致する可能性があるため、本文・author等の条件だけでは不足を除外しません。
文書専用の`pr documents`と`search pr`は、`pr-code`、`pr-commits`、`pr-files`等のコードだけの不足やtimelineだけの不足を完全性に含めません。commit/path条件を指定した場合はコードも評価します。API観測後にコード取得前で中断した場合や、必要な公開済みGit参照が欠ける場合は、通常照会の`missing`に不足を示します。照会によってclaimを追加・更新することはありません。
公開更新後のcursorはSTALE_CURSORになります。timeout時は確定できないページを捨て、飛ばしcursorを発行しません。
`--all`による一括exportはありません。PR list/showとrepos showの入れ子配列は各100件まで表示し、`nested_collections`に保存総数と省略の有無を返します。外側cursorは入れ子配列の続きを示しません。endpointの全件参照にはendpoints listのcursorを使えます。JSONには全フィールドを、tableには主要なscalar列を安全表示します。

| exit | 意味 |
|---:|---|
| 0 | complete、正当な0件、通常の次ページあり |
| 2 | 不正引数・設定・非対応profile |
| 3 | partial、容量/writer/rate limitの待機 |
| 4 | 指定対象/保存rawなし、古いcursor、識別の衝突、running cancel、任意索引利用不能 |
| 5 | 運用・DB・整合性エラー |
| 130 | SIGINTによる中断 |

取消しはforegroundへSIGINTを送ります。jobs cancelはqueued/waiting/failed/interruptedに適用し、runningを成功扱いにしません。
content showは保存rawのみ、既定64 KiB、最大1 MiBの範囲をbase64で返します。
hydrateは明示的な再取得で、保存profile対象外や取得元から失われた原文は復元できません。

## catalog3の通常運用

`init`は同梱catalog3 DDLから直接作成します。通常の収集・照会・検索・保守はcatalog3だけを扱い、旧形式のmigrationを実行しません。read-only照会は通常のSQLiteロックとトランザクションsnapshotを使い、更新中のDBやWALをimmutableとして扱いません。照会は取得・Git実行・索引修復を行わず、派生FTSやANALYZEの存在でschema全体のhashを毎回比較しません。

```bash
repo-catalog --state-dir /tmp/disposable-catalog init --profile catalog-text-v1 --cache-max-bytes 67108864 --min-free-bytes 0
repo-catalog --state-dir /tmp/disposable-catalog sources add local-git --name fixture --url /tmp/disposable-fixture.git
repo-catalog --state-dir /tmp/disposable-catalog discover
repo-catalog --state-dir /tmp/disposable-catalog sync git
repo-catalog --state-dir /tmp/disposable-catalog repos list
repo-catalog --state-dir /tmp/disposable-catalog file show --repo REPO_ID --ref refs/heads/main --path src/app.py
repo-catalog --state-dir /tmp/disposable-catalog search code --literal 'saved text'
repo-catalog --state-dir /tmp/disposable-catalog db check --full
repo-catalog --state-dir /tmp/disposable-catalog db backup --output /tmp/disposable-backup.sqlite3
repo-catalog --state-dir /tmp/disposable-restored db restore --input /tmp/disposable-backup.sqlite3
```

schema 15を直接初期化します。v2 importerとfinalizeは廃止済みで、旧DBの移行や互換引数はありません。D2は `not_applicable / retired` です。

backupはSQLite backup APIでdomainの現在状態・必要な本文・PR/Git/スレッド履歴・coverageを含むsnapshotを作り、checksum/configuration/identityと `quarantined_payload_count` を隣接manifestへ保存します。件数はactive物理隔離行数の非負JSON整数（bool除外、最大 `9223372036854775807`）です。restoreは未作成の `--state-dir` だけへ行い、checksum/identityの後、診断前に件数を照合して全bytesを検証します。正の一致件数を許容し、件数不一致や未説明の破損は失敗stageを保持して拒否します。cacheと任意通信archiveはbackupへ含めません。DB instance IDを変更して元catalogのcursorを無効にし、過去のjobs/leases/reservationsを稼働状態へ戻しません。[運用](operations.md)に制限を記載しています。

## 交換と補助通信の読取り

```bash
repo-catalog --state-dir /tmp/disposable-catalog exchange export --repo REPO_ID --output repository.json
repo-catalog --state-dir /tmp/disposable-catalog exchange export --repo REPO_ID --collection COLLECTION_UUID --output selected.json
repo-catalog --state-dir /tmp/disposable-receiver exchange import --input repository.json
repo-catalog --state-dir /tmp/disposable-receiver exchange staging
repo-catalog --state-dir /tmp/disposable-catalog parser inspect-message ARCHIVE_REF --max-bytes 1048576
repo-catalog --state-dir /tmp/disposable-catalog parser reparse-message ARCHIVE_REF --context projection.json --max-bytes 1048576
```

全repository交換と履歴用 `--fetch FETCH_UUID` / `--collection COLLECTION_UUID` の選択を維持します。current-stateも必要な親・本文・scope/completion証拠を伴って選択します。任意archiveを必須依存へ含めず、親の後着、同一再import、順序不明の差分は共通受理/stagingへ渡します。

同内容の再importでも新しいclock等の根拠を再評価し、順序を証明できれば保留競合を解消します。複数のcurrent競合はその分類のまま保持します。移動済みIssueコメントの元取得scopeは、移動元repo/Sourceの登録を受信側へ要求せずsnapshotとして保存します。

`github.record_messages` はbooleanで既定falseです。有効時のarchiveは `STATE_DIR/transport-archive/` に保存します。recording障害は許可された32文字以下のコードへ制限し、transport診断は最新100件を保持します。警告表示はbest-effortで、warnings-as-errorsでも有効な収集を続けます。domain状態の照会やcoverageとは別です。`inspect-message` はcanonical UUIDv4の参照を一つ読み、`reparse-message` は保存された成功JSONを現在resource parserへ渡して投影を返します。両方とも通信とdomain書込みを行わず、reparseも新しい観測を作りません。`--max-bytes` は既定1 MiB、0から32 MiBまでです。reparseは最大1000メンバーで、context JSONには `resource_kind` と所有者・acquisition_scopeを含む `context` が必要です。Issueコメントには `parent_provider_resource_id` も明示します。archiveがない場合は補助読取りエラーになりますが、独立に保存された現在状態は利用できます。[通信記録仕様](latest-state-transport.md)と[実装対応表](latest-state-transport-implementation.md)を参照してください。

## catalog3診断読み取り

`target --database PATH` は明示したcatalogを調べる診断入口です。`building`には`--allow-building`が必要でpartialを返し、`rejected`は読めません。通常のSQLite read-only接続とsnapshotを使い、初期化・migration・取得・索引更新を行いません。通常操作と同じSQLite bindingの能力を使います。

```bash
repo-catalog --format json target --database /tmp/disposable-catalog/catalog.sqlite3 repos
repo-catalog --format json target --database /tmp/disposable-catalog/catalog.sqlite3 pr --repo REPO_ID --provider-change-request-number 7
```

`target`はrepository IDの完全一致を要求し、`--limit`と`--offset`で保存履歴行を個別にページ化します。PRの`record_kind`はidentity、観測、文書、文書観測、review/thread/comment/event、code listing履歴を区別します。通常照会は現在のコード観測を評価し、`target`の診断照会は保存された過去のコード観測にも同じ取得対象の欠落チェックを行います。診断結果だけでruntime readinessや現在の選択を変更しません。

歴史的なimport/finalization手順や検証receiptは過去の資料です。現行CLIの操作はこの契約と `--help` を参照してください。

schema 15の変更範囲は[対応記録](current-state-schema-closure.md)、[列の用途](current-state-schema-liveness.md)と[完全schema一覧](current-state-schema-inventory.md)に記載します。
