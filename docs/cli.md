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
| DB | db migrate/check/backup/restore |
| cache・索引 | cache status/gc、index rebuild |
| Git照会 | repos list/show、snapshots list/show、refs list、tree list、commits list/show/compare |
| 検索 | search path/code/commits/hash/pr |
| PR照会 | pr list/show/documents/thread/timeline |
| 原文 | content show/hydrate |
| 状態 | coverage、status |

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
`search path --path-b64 BASE64`により任意のraw pathを指定できます。

PR検索はtitle/body/issue-comment/review/review-commentを区別します。
`--document-versions latest|observed`で現在の文書版と保存済み観測版を選びます。
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

取消しはforegroundへSIGINTを送ります。jobs cancelはqueued/waitingだけに適用し、runningを成功扱いにしません。
content showは保存rawのみ、既定64 KiB、最大1 MiBの範囲をbase64で返します。
hydrateは明示的な再取得で、保存profile対象外や取得元から失われた原文は復元できません。
