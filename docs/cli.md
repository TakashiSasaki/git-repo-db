# CLI契約

共通指定は`--state-dir PATH --format table|json --timeout-seconds N`をsubcommandより前へ置きます。
stateの既定は`$XDG_STATE_HOME/repo-catalog`、未設定時は`~/.local/state/repo-catalog`です。
JSON modeのstdoutは結果専用です。public schemaは同梱`resources/schemas/cli-v1.schema.json`です。

| 分類 | コマンド |
|---|---|
| 初期化・診断 | init、doctor |
| 収集元・収集 | sources add、discover、sync git/pr/all |
| サービス・接続 | instances add/list/show、endpoints add/list/prefer、repos bind |
| job | jobs list/show/resume/cancel |
| DB・旧形式救済 | import-v2、db finalize/check/backup/restore |
| cache・索引 | cache status/gc、index rebuild |
| Git照会 | repos list/show、snapshots list/show、refs list、tree list、file show、commits list/show/compare |
| 検索 | search path/code/commits/hash/pr |
| PR照会 | pr list/show/documents/thread/timeline |
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
`sync git/pr/all --repo REPO_ID --endpoint ENDPOINT_ID`はそのrepoの取得先を明示し、複数repo指定との組合せを拒否します。
操作例は[リポジトリ識別と取得先](repository-identity.md)を参照してください。

`current`は全heads先端、`history`は選択snapshotのheads/tagsから到達する履歴、`recorded`は過去の公開rootも含みます。
PR rootはhistory/recordedで`--pr`または`--ref-kind pr-head|pr-related`により明示します。
PR rootとsnapshot、recordedとsnapshot等の不正な組合せは拒否します。

literalはcase-sensitiveで、Unicode正規化や改行/Markdown変換をしません。
UTF-8 byte offsetは0始まり・終端非包含、lineはLF区切り・1始まりです。コミットメッセージは正本bytesで照合し、message_b64とraw byte offsetを返します。非UTF-8部分の置換表示を一致とは扱いません。
raw pathの正本はpath_b64で、UTF-8不正時のpath_utf8はnull、安全表示はpath_displayです。
`search path --path-b64 BASE64`と`file show --path-b64 BASE64`により任意のraw pathを指定できます。`file show --repo REPO_ID --commit sha1:HEX --path PATH`は保存textと原文の有無を返し、未保存のbodyはnullとpartial coverageになります。

PR検索はtitle/body/issue-comment/review/review-commentを区別します。
PR番号は `--provider-change-request-number`、種別は `--change-request-kind pull_request|merge_request` で指定します。正規化された結果でも `provider_change_request_number` と `change_request_kind` を使い、raw payload 内のprovider固有キーは変更しません。
`pr thread` は `--repo REPO_ID --provider-change-request-number NUMBER --provider-resource-id PROVIDER_RESOURCE_ID` でChange Requestを先にscopeし、その中のreview threadを選択します。`provider_resource_id` 単独のprovider全体一意性は仮定しません。
`--document-observations current|all`で現在採用している観測と保存済みの全観測を選びます。既定は `current` です。
`--document-kind` と `--provider-change-request-document-id` で文書自然キーの構成要素を指定でき、`--observation INTEGER` で保存観測を選択します。
結果は `document_kind`、`provider_change_request_document_id`、`document_observation_id`、`text_body_sha256`、`document_observed_at`、`document_current_selected` 等を返します。文書ID・版IDは返さず、旧オプションの互換別名もありません。
取得開始前や観測間の未観測編集、非公開/削除済みで取得不能な履歴は保証しません。

list/searchは`--limit`（既定100、上限1000）と`--cursor`を持ちます。
ページが続くことと取得範囲がpartialであることは別です。
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

## catalog3の通常運用と旧形式救済

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

backupはSQLite backup APIでDB内の取得履歴・変換原文・診断を含むsnapshotを作り、checksum/configurationを別manifestへ保存します。cache内容はbackupの正本に含めません。restoreは明示した新規または空の`--state-dir`だけへ行い、DB instance IDを変更して元catalogのcursorを無効にします。過去のjobs/leases/reservationsとcacheを稼働状態へ戻しません。

v2救済は明示した別stateへ、offlineのguard付きworkerで実行します。元DB/cacheの書換えと取得を禁止し、source bytes、ID、nullable値、履歴と診断をcatalog内へ保持します。中断後は同じ引数で再実行します。

```bash
repo-catalog --state-dir /tmp/disposable-import import-v2 --source /tmp/disposable-v2/catalog.sqlite3 --source-cache /tmp/disposable-v2/cache --batch-size 100 --max-batches 2
repo-catalog --state-dir /tmp/disposable-import import-v2 --source /tmp/disposable-v2/catalog.sqlite3 --source-cache /tmp/disposable-v2/cache --batch-size 100
repo-catalog --state-dir /tmp/disposable-import db finalize
repo-catalog --state-dir /tmp/disposable-import repos list
```

不完全なimportとcriticalなidentity/owner破損はfinalizeを拒否します。保存されたcurrent選択を同じownerの適切な完了済み観測へ結び付けられない場合は未解決として残し、現在照会はpartialを返します。取り込んだ過去のprocess状態をresumeで再稼働しません。欠落原文・partial pageの有用な記録は取得済み範囲として照会できます。

## catalog3診断読み取り

`target --database PATH`は未finalizeのcatalogを調べる診断入口です。`building`には`--allow-building`が必要でpartialを返し、`rejected`は読めません。通常のSQLite read-only接続とsnapshotを使い、初期化・migration・取得・索引更新を行いません。通常操作と同じSQLite bindingの能力を使います。

```bash
repo-catalog --format json target --database /tmp/disposable-import/catalog.sqlite3 --allow-building repos
repo-catalog --format json target --database /tmp/disposable-import/catalog.sqlite3 --allow-building pr --repo REPO_ID --provider-change-request-number 7
```

`target`はrepository IDの完全一致を要求し、`--limit`と`--offset`で保存履歴行を個別にページ化します。PRの`record_kind`はidentity、観測、文書、文書観測、review/thread/comment/event、code listing履歴を区別します。診断結果だけでruntime readinessやcurrent pointerを変更しません。
