# 検証方法

catalog3 の通常動作と v2 のオフライン救出を、一つの Python/SQLite binding で検証します。最小 SQLite 版の独立 lane と過去の phase 互換性・試験件数・node ID 下限は廃止しました。実行時の版と機能を記録し、FK、recursive triggers、FTS、WAL の既知の修正条件など、必要な正しさの条件は維持します。

依存取得は試験より先に行います。

```bash
uv sync --locked --group dev
uv run --no-sync python scripts/prepare_wheelhouse.py
uv run --no-sync python -c 'import platform, sqlite3; print(platform.python_version(), sqlite3.sqlite_version)'
uv --version
```

編集中は変更した機能の試験を実行します。仕上げでは [現在の acceptance policy](../scripts/ci_dependencies.json) の機能試験を一度実行し、installed package を独立した逐次 lane で確認します。

```bash
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync python scripts/ci_execute.py current --lane tests
uv run --no-sync python scripts/ci_execute.py current --lane packaging
```

`current` は作業ツリーに存在する現在の manifest と `test_catalog3*.py` / `test_runtime*.py` を使います。編集中の結果は dirty-tree 状態を含む生の profile として保存し、確定した Git tree の CI acceptance manifest と区別します。全履歴の試験や phase export は再実行しません。現在の対象から外した試験は CI plan の `excluded_files` に列挙し、選択されなかった現在の試験は `unexecuted_files` に列挙します。

現在の acceptance は、新規初期化・探索・Git/PR 取得、増分取得と部分応答の再開、要求ログ、オフライン照会と検索、停止・保全・バックアップ、v2 から通常利用への救出を対象にします。same-owner 関係、完了 listing の封印、公開可能性、raw bytes、履歴、原本保護を検証します。DDL の正本は package 内の `resources/catalog3.sql` です。

通常の pytest は外部通信と実 token を遮断します。親と子 Python の guard は合成 HTTP fixture 用の loopback だけを許し、Git transport は file に限定します。v2 importer の source-write / acquisition guard は、fixture 通信より強い独立境界です。依存準備のために importer の guard を解除しません。すべての stateful command は disposable な `--state-dir` を指定します。

package 試験は lock と SHA で検証した wheelhouse を `--offline --no-index --find-links` で使います。wheel と sdist 由来 wheel を新しい venv に導入し、source 外の CWD から console script と `python -m` を実行します。catalog3 DDL、import contract と importer の同梱、新規 catalog3 初期化、取得・検索・再構築・整合性を確認します。

今回の作業環境は Python 3.12.14、SQLite 3.53.1、uv 0.12.19 です。これは実測値であり、下限版の保証ではありません。最終結果と未実行項目は機能 handoff に記録します。CI の選択と結果照合は [変更に応じた CI](change-aware-ci.md)、計測は [CI 性能](ci-performance.md) を参照してください。
