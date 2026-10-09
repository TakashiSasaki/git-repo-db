# repo-catalog

任意のGit取得先とGitHubのPRをSQLiteへ保存し、cloneやAPI接続がなくなった後も照会するCLIです。
Git構造・参照観測・Blob原文のMD5/SHA-1/SHA-256・対象本文・PR文書と観測履歴を永続化します。
通常ランタイムは catalog3 です。 現在の schema version は **11** で、entity ID と FK は `repository_uuidv4`、`git_object_id`、`document_observation_id` のように意味を明示します。保存する絶対時刻は Unix epoch からのマイクロ秒を INTEGER で保持し、`observed_at_us` のように単位を付けます。[現行データモデル](docs/data-model.md)と packaged DDL が正本です。旧 catalog3 開発 DB は対応しません。Linux のローカル filesystem で検証し、Python の必要構文・API は package metadata に記載しています。検証した環境・範囲は[実行引き継ぎ](docs/schema-hardening/runtime-handoff.md)に記録しています。

## 開発・導入

```bash
uv sync --locked --group dev
uv run --no-sync repo-catalog --help
uv run --no-sync repo-catalog --format json doctor
```

`doctor`は未初期化でもruntime能力を診断し、stateやDBを作成しません。
PythonへリンクされたSQLiteはSTRICT対応が必要です。FTS5 trigramは任意で、なくても原文scan検索が使えます。

通常利用向けには、checkoutでwheelを作り、Python 3.12以上の別venvへ導入します。依存は既存のlockに固定します。以下のbuild/installは依存の取得に通信を使う場合があります。導入後のCLIはcheckoutを必要としません。

```bash
uv build --wheel --out-dir artifacts/dist
uv export --locked --no-dev --no-emit-project --format requirements-txt \
  --output-file artifacts/runtime-requirements.txt
uv venv /path/to/venv --python 3.12
uv pip install --python /path/to/venv/bin/python \
  --constraint artifacts/runtime-requirements.txt \
  artifacts/dist/repo_catalog-0.2.0-py3-none-any.whl
/path/to/venv/bin/repo-catalog --state-dir /path/to/new-state doctor
/path/to/venv/bin/repo-catalog --state-dir /path/to/new-state init \
  --profile catalog-text-v1 --cache-max-bytes 67108864 --min-free-bytes 0
/path/to/venv/bin/repo-catalog --state-dir /path/to/new-state repos list
```

`/path/to/new-state`は確認用の新規保存先です。この容量設定は小さな動作確認用で、実データの容量は別途決めます。実データ試行の入力・許可とbackupの保管要件は[運用](docs/operations.md)を参照してください。

## 初期化と収集

global optionはsubcommandより前へ置きます。以下の容量は操作例であり、300repo向けの推奨値ではありません。

```bash
repo-catalog --state-dir /path/to/state init \
  --profile catalog-text-v1 --cache-max-bytes 5368709120 --min-free-bytes 2147483648
repo-catalog --state-dir /path/to/state sources add local-git \
  --name example --url file:///path/to/repo.git
repo-catalog --state-dir /path/to/state discover
repo-catalog --state-dir /path/to/state sync git
```

GitHubは` sources add github --owner OWNER`で登録します。APIの認証は既定の`GH_TOKEN`、または`catalog.toml`の`github.token_env_var`で指定した環境変数を利用します。Gitの認証は既存のSSH/credential helper/クラウドGit proxyを利用し、API認証とは独立です。資格情報は環境設定等で供給し、設定ファイル・URL・コマンド引数へ埋め込まないでください。

認証ユーザーの所有repoはprivate/fork/archivedを含め列挙し、PRは全状態を対象にします。少数対象のpilotは`--include-repo NAME`を繰り返して明示対象だけに限定できます。
GitHub sourceの`--clone-url-override REPO_ID=URL`は、明示的なテスト設定や既存ローカル取得元への接続に使えます。

catalog3 はRepo IDとサービスの `service_instance_uuidv4` 名前空間、native ID、取得URL、sourceを分離します。文書は自然キーで識別し、観測から本文のSHA-256を直接参照します。文書用のローカルIDと中間の版テーブルは持ちません。
SSHとHTTPS、ローカルとネットワークのマウントpathを同じRepo IDの取得先として明示登録できます。
Sourceにはローカルな `source_id` と恒久的な `source_registration_uuidv4` があります。`--source` はどちらでも指定でき、曖昧な場合は `local:ID` / `registration:UUID` で区別します。service名の重複は許容しますが、同名が複数あれば `--instance UUID` を指定してください。

GitLab/Gitea/GitoliteなどのGitデータは` sources add git-url`で登録できます。GitLab/Giteaの自動列挙・MR/PR API adapterは後続範囲です。
保存済み開発 v2 データは、新規 state へオフライン import します。登録例は[リポジトリ識別と取得先](docs/repository-identity.md)を参照してください。

## 照会

```bash
repo-catalog --state-dir /path/to/state repos list
repo-catalog --state-dir /path/to/state refs list --repo REPO_ID
repo-catalog --state-dir /path/to/state tree list --repo REPO_ID --ref refs/heads/main
repo-catalog --state-dir /path/to/state search code --literal 認証
repo-catalog --state-dir /path/to/state search pr --literal 認証 --document-observations all
repo-catalog --state-dir /path/to/state --format json search hash \
  --algorithm raw-sha256 --digest ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

`current`は明示選択された公開snapshotのheads先端、`history`は選択snapshotのheads/tagsから到達する履歴、`recorded`は過去の公開取得rootも含む範囲です。
PR rootは明示選択します。通常照会はDBの読取りだけで完結し、通信・Git実行・自動migration・原文再取得を行いません。

`catalog-text-v1`は全heads先端のUTF-8 strict・NULなし・8 MiB以下の本文を可逆保存します。
全取得対象Blobのdigestはbinaryや巨大Blobも含め記録しますが、全履歴・全binaryの原文保存ではありません。
履歴の未保存本文は検索coverageに不足として出し、原文不在を空bytesへ置換しません。

保存された coverage は scope ごとの最新観測時刻にある claim 集合から導出します。保存状態は `complete`、`partial`、`unknown`、`not_applicable` です。同時刻の `unknown` は他の状態を妨げませんが、他の状態が複数あれば `conflict` と表示します。新しい `unknown` から古い `complete` へは戻りません。`coverage`、`status`、snapshot の JSON は各 claim とその `details_json` を個別に返します。重複・古い claim の登録は NO-OP で、既存の claim と詳細を変更しません。

## 解析履歴・交換・完全性

新規 DB を対象とした統合モデルです。旧 DB の移行機能はありません。通常の current は、明示選択した検証済み parser/profile と不変の選択 DAG から導出します。独立した選択が競合した場合は未解決となり、時刻や受信順で一方を選びません。

```bash
repo-catalog --state-dir /path/to/state parser status
repo-catalog --state-dir /path/to/state parser reparse FETCH_UUID
repo-catalog --state-dir /path/to/state exchange export --repo REPO_UUID --output repository.json
repo-catalog --state-dir /path/to/receiver exchange import --input repository.json
repo-catalog --state-dir /path/to/receiver exchange staging
repo-catalog --state-dir /path/to/state db verify-payloads
repo-catalog --state-dir /path/to/state db repair-payload --sha256 HEX --input verified-bytes.bin
repo-catalog --state-dir /path/to/state db backup --output catalog-backup.sqlite3
repo-catalog --state-dir /path/to/new-state db restore --input catalog-backup.sqlite3
```

再解析では取得 UID と取得時刻を保持し、新しい解析結果を追加します。通常参照へ切り替える場合は明示的な選択が必要です。交換単位は一つの repository と必要な依存・payload bytes です。Source 全体の inventory、ローカル trust、隔離状態、運用設定は通常の交換へ含めません。

破損した物理 bytes は永続診断と隔離で扱い、明示修復だけが隔離を解除します。バックアップは隔離済み bytes と診断も保持します。復元先は未作成のパスを指定し、失敗した stage は保存します。実装・判断対応・検証結果は [統合 handoff](docs/model-integration-handoff.md)、[独立監査](docs/model-integration-audit.md)、[判断対応表](docs/model-integration-status.md) を参照してください。

## テスト・再現demo

```bash
uv run --no-sync python scripts/prepare_wheelhouse.py  # 依存のonline準備
uv run --no-sync python scripts/ci_execute.py current --lane tests
uv run --no-sync python scripts/ci_execute.py current --lane packaging
uv run --no-sync python scripts/demo.py \
  --work-dir artifacts/demo-run-001 --scenario offline-recovery
```

標準試験は実Git、loopback合成API、dummy credential、SQLite実ファイル、実CLI subprocessで行います。
実アカウントを不要にし、親pytestと子Pythonプロセスの外部通信を遮断します。Gitはfile transportに限定します。
demoは新規/空directoryにfixtureを生成し、収集、更新、clone実回収、offline照会、再索引、backup/別state復元を検証します。

詳細は[CLI仕様](docs/cli.md)、[アーキテクチャ](docs/architecture.md)、[データモデル](docs/data-model.md)、[運用](docs/operations.md)、[テスト](docs/testing.md)、[実装状況](docs/implementation-status.md)を参照してください。
