# リポジトリ識別と取得先（catalog3）

Repo IDはURLから独立したUUIDv4です。別プロトコルやマウントpathを同じrepoの取得先として明示登録できます。
GitHub、GitLab、Gitea、Forgejo、Gitolite、plain Git、その他のサービスをinstance単位で表現します。

| 実体 | 識別・関係 |
|---|---|
| `repositories` | 内部UUIDv4。repoのカタログ上の同一性 |
| `service_instances` | 内部UUIDv4、kind、一意のname、任意のweb/API base URL |
| `repository_bindings` | repoとinstanceの対応。native IDは文字列またはNULL。`UNIQUE(instance_id, provider_repo_id)` |
| `repository_endpoints` | 内部UUIDv4、repo、Git URL、transport、label、優先指定。`UNIQUE(repo_id,url)` |
| `sources` | 発見・列挙の設定と任意のinstance参照。API tokenは環境変数名で参照 |
| `source_repositories` | sourceとrepoの多対多関係、最初と最後の発見時刻 |
| `git_acquisitions` | 取得・解析run。使用endpoint IDとURLを保持 |

```mermaid
erDiagram
    SERVICE_INSTANCES ||--o{ REPOSITORY_BINDINGS : identifies
    REPOSITORIES ||--o{ REPOSITORY_BINDINGS : has
    REPOSITORIES ||--|{ REPOSITORY_ENDPOINTS : accesses
    SOURCES ||--o{ SOURCE_REPOSITORIES : discovers
    REPOSITORIES ||--o{ SOURCE_REPOSITORIES : discovered_by
    SERVICE_INSTANCES o|--o{ SOURCES : configures
```

instance UUIDにより、同じhost上の別port/base pathや別オンプレ環境のnative IDを区別します。
URL、DNS alias、同じcommit、同じ内容はrepo統合の根拠にしません。forkや独立mirrorは別Repo IDで登録できます。
同じinstanceとnative IDを再発見した場合は既存Repo IDへ結び付けます。同じURLの別登録は、`--repo`等の明示指定がなければ別Repo IDになります。
Git-only登録を後からAPI管理repoへ結び付ける場合も、既存Repo IDへbindingを追加できます。

## SSH/HTTPSとローカルの別path

以下の`REPO_ID`と`ENDPOINT_ID`は各コマンドが返したUUIDに置き換えます。stateは初期化済みとします。

```bash
repo-catalog --state-dir /path/to/state sources add git-url \
  --name app --url git@code.example.net:team/app.git
repo-catalog --state-dir /path/to/state discover
repo-catalog --state-dir /path/to/state repos list
repo-catalog --state-dir /path/to/state endpoints add --repo REPO_ID \
  --url https://code.example.net/team/app.git --label https
repo-catalog --state-dir /path/to/state endpoints list --repo REPO_ID
repo-catalog --state-dir /path/to/state sync git --repo REPO_ID --endpoint ENDPOINT_ID
```

同じvolumeを別マウント経由で取得するときも同様です。

```bash
repo-catalog --state-dir /path/to/state endpoints add --repo REPO_ID \
  --url file:///mnt/network/team/app.git --label network-mount --preferred
repo-catalog --state-dir /path/to/state sync git --repo REPO_ID
```

相対pathは登録時の作業directoryから絶対file URIへ変換し、symlinkは解決しません。登録したマウントの表記を保持します。
`endpoints prefer`でも優先取得先を切り替えられます。初回endpointは自動的に優先され、repoに優先endpointは1件です。
新しいrunは開始時に取得先を固定するため、優先先を変更しても実行済み・中断済みrunの来歴は変わりません。
同じrepo内のキャッシュを再利用し、取得先が変わっただけでGit objectやdigestを複製しません。

別sourceとしても登録する場合は、既存Repo IDを指定します。

```bash
repo-catalog --state-dir /path/to/state sources add git-url --name network-view \
  --url file:///mnt/network/team/app.git --repo REPO_ID
repo-catalog --state-dir /path/to/state discover --source SOURCE_ID
repo-catalog --state-dir /path/to/state repos list --source SOURCE_ID
repo-catalog --state-dir /path/to/state sync git --source SOURCE_ID
```

Git URL sourceを指定したsyncはそのsourceのURLを使います。省略時はrepoの優先endpointを使います。
SSHの鍵・agent・host alias・非標準port・ProxyJump、HTTPSの認証は既存Git/OpenSSH/credential helper設定を利用します。
DBへ資格情報の秘密値を保存しません。

## サービス内の識別

```bash
repo-catalog --state-dir /path/to/state instances add gitlab --name corp-gitlab \
  --web-base-url https://code.example.net/gitlab \
  --api-base-url https://code.example.net/gitlab/api/v4
repo-catalog --state-dir /path/to/state repos bind --repo REPO_ID \
  --instance corp-gitlab --provider-repo-id 42
repo-catalog --state-dir /path/to/state repos show --repo REPO_ID
```

native IDが不明なら`--provider-repo-id`は省略可能です。同じinstance内で同じnative IDを別repoへ結び付ける操作は`IDENTITY_CONFLICT`として拒否します。
既存repoを合併するコマンドはありません。誤った対応を自動的に上書きしません。
kind/base URLの登録はAPI adapterの実装や実接続試験を意味しません。

GitHub API sourceはinstanceとtoken参照を選べます。

```bash
repo-catalog --state-dir /path/to/state instances add github --name corp-github \
  --web-base-url https://github.example.net \
  --api-base-url https://github.example.net/api/v3
repo-catalog --state-dir /path/to/state sources add github --owner team \
  --instance corp-github --token-env-var CORP_GITHUB_TOKEN
```

同一instanceを複数source・アカウントで列挙してもnative IDによりRepo IDを再利用します。
API通信設定とtoken参照はsourceごとに選択し、条件付きGET・増分checkpointを別sourceから混用しません。
GitHub互換APIのinstance分離はloopback fixtureで検証しています。実GHESやGitLab/Gitea/SSHの接続試験は別途必要です。
GitLab/Gitea/Forgejoの自動列挙・MR/PR収集adapterは未実装です。共通データモデルは binding/request-kind ごとの番号空間を持ちます。Git-onlyはPRを`not_applicable`、対応サービスのbindingがあるのに利用可能なAPI sourceがない場合は`PROVIDER_UNSUPPORTED`/partialを返します。
1つのRepo IDに複数GitHub instanceを結び付けた場合も、サービスごとのPR番号空間の分離は後続範囲なのでPR収集は`PROVIDER_UNSUPPORTED`とします。Gitの複数取得先は利用できます。

## 保存済み v2 の import

現在の製品ランタイムは catalog3 だけです。旧 decoder は packaged import support に分離されています。保存した v2 DB/cache から別の新規 state へ `import-v2` を行い、`db finalize` で重要な identity/owner と保存された current 選択を検査します。通常の初期化・照会・収集は古い migration を実行しません。

内部 ID、provider-native ID、endpoint/source の関係、元の observation 時刻、raw bytes は保持します。不明な値や矛盾は typed archive と帰属付き診断に残し、架空の identity や再観測を作りません。実データに対する dry run と切り替えは、この合成検証とは別の作業です。
