# repo-catalog

GitとGitHubのPRをSQLiteへ保存し、cloneやAPI接続がなくなった後も照会するCLIです。
Git構造・参照観測・Blob原文のMD5/SHA-1/SHA-256・対象本文・PR文書と観測版を永続化します。
初版はLinux/WSL2のローカルfilesystem、Python 3.12+、Git 2.43+を対象にしています。

## 開発・導入

```bash
uv sync --locked --group dev
uv run --no-sync repo-catalog --help
uv run --no-sync repo-catalog --format json doctor
```

`doctor`は未初期化でもruntime能力を診断し、stateやDBを作成しません。
PythonへリンクされたSQLiteはSTRICT対応が必要です。FTS5 trigramは任意で、なくても原文scan検索が使えます。

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

## 照会

```bash
repo-catalog --state-dir /path/to/state repos list
repo-catalog --state-dir /path/to/state refs list --repo REPO_ID
repo-catalog --state-dir /path/to/state tree list --repo REPO_ID --ref refs/heads/main
repo-catalog --state-dir /path/to/state search code --literal 認証
repo-catalog --state-dir /path/to/state search pr --literal 認証 --document-versions observed
repo-catalog --state-dir /path/to/state --format json search hash \
  --algorithm raw-sha256 --digest ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

`current`は最新公開snapshotのheads先端、`history`は選択snapshotのheads/tagsから到達する履歴、`recorded`は過去の公開取得rootも含む範囲です。
PR rootは明示選択します。通常照会はDBの読取りだけで完結し、通信・Git実行・自動migration・原文再取得を行いません。

`catalog-text-v1`は全heads先端のUTF-8 strict・NULなし・8 MiB以下の本文を可逆保存します。
全取得対象Blobのdigestはbinaryや巨大Blobも含め記録しますが、全履歴・全binaryの原文保存ではありません。
履歴の未保存本文は検索coverageに不足として出し、原文不在を空bytesへ置換しません。

## テスト・再現demo

```bash
uv run --no-sync pytest tests/unit tests/integration tests/e2e tests/packaging \
  --strict-markers -m "not live and not benchmark"
uv run --no-sync python scripts/demo.py \
  --work-dir artifacts/demo-run-001 --scenario offline-recovery
```

標準試験は実Git、loopback合成API、dummy credential、SQLite実ファイル、実CLI subprocessで行います。
実アカウントを不要にし、親pytestと子Pythonプロセスの外部通信を遮断します。Gitはfile transportに限定します。
demoは新規/空directoryにfixtureを生成し、収集、更新、clone実回収、offline照会、再索引、backup/別state復元を検証します。

詳細は[CLI仕様](docs/cli.md)、[アーキテクチャ](docs/architecture.md)、[データモデル](docs/data-model.md)、[運用](docs/operations.md)、[テスト](docs/testing.md)、[実装状況](docs/implementation-status.md)を参照してください。
