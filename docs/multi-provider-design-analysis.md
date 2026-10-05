# 複数リポジトリサービスへの拡張分析

この文書の分析本文はschema v1の読取りに基づく設計提案です。
その後、schema v2でinstance、binding、endpoint、sourceの多対多対応を実装しました。
現在の仕様と操作例は[リポジトリ識別と取得先](repository-identity.md)を参照してください。

| 分析で提案した範囲 | v2の到達点 |
|---|---|
| 内部Repo UUID、instance、native IDの分離 | 実装。既存Repo IDを維持するmigrationを追加 |
| 複数Git URLとsourceへの対応 | 実装。マウント別名も明示登録でき、runの取得先を固定 |
| instance/sourceごとのGitHub API設定・token参照 | 実装。loopback fixtureで別instance/複数sourceを検証 |
| Git-only、対応API、API未実装の区別 | 実装。未実装サービスはPROVIDER_UNSUPPORTED/partial |
| 外部thread IDの衝突回避 | 新規GitHub thread IDを親PRでscope化。保存済みv1 IDは維持 |
| GitLab/Gitea inventory・MR/PR adapter、共通PR/MRモデル | 後続範囲 |

以下の「現行」は分析時点のv1を指します。v2実装後の制約は上記リンクと[実装状況](implementation-status.md)に記載します。

## 結論と対応範囲

Git履歴・ファイル・digestのカタログだけであれば、大きなスキーマ変更は不要。
現行の`local-git` sourceはURLをGitへ渡すため、fileだけでなくHTTPS、SSH URL、SCP形式のGit URLもコード上は登録できる。Git transportの既定許可はfile/https/ssh。
名称はlocal-gitだが、保存するGitオブジェクトはホスティング先に依存しない。
今回のpilotはGitHubとローカルfixtureであり、GitLab/Gitea/Gitolite/SSHの実接続を検証したという意味ではない。

サービスのrepo自動列挙やPR/MR・レビューまで含める場合は、識別・設定・収集adapter・共通照会モデルの拡張が必要。
変更の中心はサービス周辺とapplication層であり、GitのDAG/tree/Blob保存層を作り直す必要はない。

| 対象と機能 | 現行で再利用できる範囲 | 必要な拡張 |
|---|---|---|
| GitLab.com、オンプレGitLabのGitデータ | 明示Git URL、heads/tags、履歴、本文profile、digest | 接続設定。正確なサービス識別は下記の共通metadata拡張 |
| GiteaのGitデータ | 同上 | 同上 |
| Gitolite、SSH-only private Git | 同上。PRなしのGit-only対象として登録 | SSH認証・ホスト鍵・到達性。全repo列挙は明示リスト等の別取得経路 |
| GitLabのrepo一覧・MR・discussions | Git保存層、文書版と観測履歴、API page保存 | GitLab adapter、instance識別、MR共通モデル |
| Giteaのrepo一覧・PR・レビュー | 同上 | Gitea adapter、instance識別、サービスごとの機能判定 |

## 変更不要なGitの中核

以下はホスティング先によらず維持できる。

- `git_objects`: `(object_format, oid)`による識別。
- `commits`, `commit_parents`, `tree_entries`, `tag_objects`: Gitの構造。
- `contents`, `content_digests`, `blob_content_map`: 内容とraw digest。
- `snapshots`, `ref_observations`, `repository_object_sources`: 観測と取得根拠。
- `root_manifests`, `root_manifest_entries`: treeのパス展開。
- cache回収、固定rootの保存義務、job再開、バックアップ、原文照合検索の基本方式。

同じOIDのオブジェクトは異なるサービス間でも共有できるが、同じコミットを含むだけでrepoの同一性を推定しない。forkやmirrorは別repoとして識別する。
Gitデータのcomplete判定は指定範囲とアクセス可能な参照に対するもの。権限で隠された参照、LFS実体、submoduleの別repoまで自動的に完全保存したことにはならない。

現行fetchは`refs/heads/*`と`refs/tags/*`を対象にする。独自ref、notes、特殊なレビュー用refを追加で対象にする場合は、取得profile/refspecを拡張する。GitLab等のMR参照はサービスadapterが取得起点を供給する。

## 現行実装に残るGitHub依存

| 箇所 | 現行の制約 | 変更方針 |
|---|---|---|
| `resources/migrations/001_initial.sql:3` | source kindはlocal-git/githubのCHECKのみ | Git URLの登録とprovider API列挙を分ける |
| 同`:5` | repo識別は`UNIQUE(provider_host,provider_repo_id)`、sourceは1個 | instanceを識別し、repoとsourceの対応を複数保持 |
| `application/collection_service.py:82` | local以外のdiscoverはGitHubCollectorへ渡す | adapter registryによる明示dispatch |
| 同`:203` | local以外のPR syncはGitHubCollectorへ渡す | provider/capabilityに基づくdispatch |
| `adapters/github/collector.py:153` | provider hostをgithub.comに固定 | instanceから取得 |
| `config.py`、`adapters/github/transport.py` | API設定・token選択はglobalなgithub section | instance/source別API設定・認証参照 |
| `application/query_service.py:215` | inventory coverageをgithub sourceだけ検査 | 列挙方式を持つ全sourceへ一般化 |
| `application/pr_queries.py` | 状態・投稿者・URL・thread判定がGitHub payload形式 | 共通の正規化された観測情報を照会 |
| `adapters/github/collector.py:775` | PR headは`refs/pull/<number>/head` | providerごとに取得起点を構成 |

`local-git`によるGit-only登録を継続する間はスキーマ変更ゼロでも利用できる。ただしhost=`local`、provider ID=source UUIDとして保存されるため、実際のサービスの識別や、同じrepoを別sourceで登録した際の重複防止には不十分。
`github`のkindを`gitlab`等に変更して既存collectorを使う方法では対応できない。

## サービス、取得対象、接続を分離する

推奨する区分は次の4つ。

1. サービスの種類: GitHub / GitLab / Gitea / Gitolite / plain Git。
2. サービスのinstance: github.com、gitlab.com、社内GitLab A、社内GitLab Bなど。
3. 列挙・取得対象: owner/group/namespace、明示repo一覧、URL、directory等。
4. Git/API接続: HTTPS/SSH、接続先、利用する認証profile。

GitLabをSSHでcloneすることと、GitoliteをSSHでcloneすることは接続方式が同じでも異なるservice設定。
オンプレとSaaSで別のGitデータモデルは不要。同じGitLab adapterにinstanceごとのAPI endpoint、version/capability、認証・信頼設定を与える。

テーブル名は案だが、次の形なら既存repoの内部UUIDを維持して段階追加できる。

| 追加・拡張案 | 主な項目と制約 |
|---|---|
| `service_instances` | 内部instance UUID、provider kind、表示名、web/API base URL |
| `repository_bindings` | repo UUID、instance UUID、provider repo ID。API管理repoは`UNIQUE(instance_id, provider_repo_id)` |
| `repository_endpoints` | repo UUID、Git接続URL、用途、認証profileへの参照。HTTPS/SSHを複数保持可能 |
| `source_repositories` | source UUIDとrepo UUIDの対応、観測時点。複数の列挙sourceが同じrepoを発見可能 |
| `sources`の拡張 | discovery方式、instance参照、対象scope、API認証profile参照 |

hostnameだけでは同じhost上の別port・別base pathのinstanceを区別できない。APIとSSHのhostnameが違う場合もある。
instance UUIDと接続URLを別にし、hostnameやURL変更によって自動的に別repoを作らない。
GitLabのproject IDはinstance内のID、MRのiidはproject内の番号として扱う。GitLabの階層groupをGitHubのowner名検証へ通さない。

APIを持たないplain Gitにはproviderの不変IDがない。内部repo UUIDを発行し、明示登録したendpoint/aliasを結び付ける。SSH aliasやURL表記だけから同一性を断定しない。
URLによる仮識別は改名・移転に弱い。Git-only登録を後からAPI管理repoへ結び付ける場合は、同じ内部repo UUIDへ明示的にbindingを追加できる設計にする。

認証profileには秘密値ではなく参照だけを保存する。GitのSSH agent/config/credential helperと、サービスAPI tokenは独立に選択する。
同一instanceを異なるアカウントで列挙するsourceも想定し、API tokenをinstanceだけに固定しない。

## PR/MRモデルの一般化

`pull_requests`というテーブル名だけを変える必要はない。既存のrepo内番号、文書実体、本文版、観測履歴のモデルはMRにも再利用できる。
`UNIQUE(repo_id, number)`はGitLabのproject内iidにも対応できる。
追加が必要なのはprovider固有の意味を表す項目と、共通に照会する項目の分離。

- request kind: pull_request / merge_request。
- providerのresource IDとrepo内番号を区別。GitHub node IDは任意のprovider属性として保持。
- 正規化されたtitle/state/draft/author/web URL。ユーザーIDやログイン名はinstanceの範囲で識別。
- head/baseのOIDに加え、必要に応じてsource/target repoとbranchの参照。forkからのMRは取得remoteが異なる場合がある。
- thread/discussionの共通属性とprovider固有属性。GitHubのレビュー判定とGitLabのapproval等を同一の意味として強制変換しない。

生のAPI payloadは現行同様に保持し、正規化された観測値を別column/補助tableへ追加する。既存のraw payloadをGitHub互換の架空payloadへ書き換えない。
queryは共通観測値を読むことでproviderを横断する。未提供・未取得の属性はunknown/unsupportedとして扱い、falseや空集合で置き換えない。

`review_threads.id`は現在GitHubのGraphQL IDを直接主キーにしている。別instanceを追加するとIDの一意性を保証できないため、内部IDまたはinstance/parentでscopeを付けたIDへ変更する。文書・イベント・ユーザーの外部IDも同様にscopeを点検する。

`acquisition_roots`、`pr_git_links`は接続点として再利用する。`pr_number`、`observation_id`等のPR前提の意味をMRにも定義し、取得起点に利用するrepo/endpointと期待OIDの来歴を保持する。head/base、実merge結果、一時的mergeテスト結果の違いは維持する。
GitLabの`refs/merge-requests/<iid>/head`等はadapterが構成し、利用可否を確認する。Gitサーバーが任意OID fetchを許可するとは限らないため、直接OID取得だけに依存しない。

## adapter、機能判定、接続設定

provider adapterの入口は、repo inventory、change request一覧、文書/レビュー、コード関連、取得起点、capability reportを分ける。
GitImporterにはGit取得起点とendpointを渡し、providerのAPI形式やref命名を解釈させない。
現行GitImporterの`pr_roots`引数はrole/numberを前提にするため、サービス中立なacquisition requestへ整理する。

Git-only repoではPR取得はnot_applicable。
GitLab/GiteaでPR/MR機能はあるがadapter未実装ならunsupported、認証不足ならaccess不明/partialとする。どちらも「PRが0件」とは扱わない。
同じproviderでもオンプレversion、設定、認証権限でAPI機能が異なる。GitHubのpagination、ETag、GraphQL、件数上限、rate limit処理をそのまま他providerへ適用しない。
checkpoint・条件付きGETのscopeにはrepo/instance、認証主体、対象範囲、API版を含め、別sourceの結果を混用しない。

SSHにはAPI一般に通用する「全repo一覧」操作がない。Gitoliteの一覧取得機能が利用できる場合は専用adapter、それ以外は明示repo一覧・manifest等を用いる。
取得範囲を「この認証主体から見えるrepo」「明示したrepo」等として記録し、サーバー上の全repoを列挙したとは主張しない。

SSH-only private repoの運用ではSSH鍵/agent、known_hosts、非標準port、ProxyJump等を既存OpenSSH設定へ委ねられる。
Gitの`GIT_TERMINAL_PROMPT=0`だけではSSHのすべての対話を抑止できないため、無人運用ではSSH BatchModeとホスト鍵を事前設定する経路が必要。
オンプレAPIには社内CAとVPN/DNS/到達性の設定が必要な場合がある。TLS検証・SSHホスト鍵検証を無効化する設計にはしない。
HTTP transportのtimeout・bounded response・安全なredirect等は共通化できるが、認証headerと許可originはinstance/source単位に維持する。

## 段階的な移行

1. Git-only登録を活用し、`local-git`の意味を文書で明確にする。対象repoの実SSH/HTTPS接続を別途検証。
2. instance、repo binding、endpoint、sourceとの対応を追加。既存github.comを1 instanceへ移行し、repo/object/contentの内部IDを維持。
3. adapter dispatch、instance/source別認証、inventory coverageを一般化。GitLab、Giteaのinventoryを追加。
4. PR/MR共通観測値・thread ID scope・Git取得起点を整備し、サービスごとのPR/MR adapterを追加。

既存`001_initial.sql`の書換えやDBの作り直しは不要。番号付きmigrationを追加し、バックアップとmigration後のFK検査で既存データを保持する。
SQLiteの既存CHECKを変更する場合は対象tableの再構築が必要になる。変更対象はmetadata tableに限定でき、Gitの再fetch/再hashは不要。

ただし現行migration engineにも複数versionへの準備が必要。
`adapters/sqlite/store.py`の検証は`{version}_initial.sql`というファイル名を前提にする。意味のある別suffixのmigrationを追加するならversionからresourceを解決する方式へ修正する。
また、新規DBで複数migrationを適用する際は、最初のmigration後にcatalog_metaの初期化済み状態を反映する必要がある。現在のループは開始時のexisting判定を使い続けるため、そのままversionを増やすと再INSERTする経路が生じる。
現行version 1のpilotが失敗しているという指摘ではなく、version 2以降を導入する際の必要な修正。

移行後に必須となる検証は、同じnative IDを持つ別instance、同じrepoを発見する複数source、SSHとHTTPSの二重登録、改名/移転、GitLab階層group、forkのMR、機能非対応、権限不足、v1からのmigration、新規DBで全migration適用、backup/restore、clone削除後のprovider横断オフライン検索。
サービスAPI fixtureでの検証と、各サービス・SSHでの実接続試験は区別する。
