# 検証方法

Catalog3 schema 18 の通常動作とPhase 1のAPI原本依存機能廃止を、一つの Python/SQLite binding で検証します。v2 importerと救出workspaceは廃止済みです。最小 SQLite 版の独立 lane と過去の phase 互換性・試験件数・node ID 下限は廃止しました。実行時の版と機能を記録し、FK、recursive triggers、FTS、WAL の既知の修正条件など、必要な正しさの条件は維持します。

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

`current` は作業ツリーに存在する現在のpolicy・manifestから対象を選択します。実際のselected/executed node IDsを照合し、新しいretirement試験が選ばれていない場合も隠しません。編集中の結果は dirty-tree 状態を含む生の profile として保存し、確定した Git tree の CI acceptance manifest と区別します。全履歴の試験や phase export は再実行しません。現在の対象から外した試験は CI plan の `excluded_files` に列挙し、選択されなかった現在の試験は `unexecuted_files` に列挙します。

現在の acceptance は、新規初期化・探索・Git/PR/Issue取得、増分取得と部分応答のlive再開、任意通信記録、オフライン照会と検索、停止・domain保全・交換・backup/restoreを対象にします。same-owner関係、完了listingの封印、公開可能性、Git raw bytes、正確なdomain本文、歴史的公開/証明closureを検証します。DDLの正本は `adapters/sqlite/schema.py` が全同梱SQLから組み立てる `schema_sql()` です。

Phase 1では`reparse-message`のdispatch/help/API不在と無副作用、archiveからdomain parserへの間接到達の不在、現在状態のreplay拒否、全面拒否された未commit API応答のcoreでのraw/Base64/hex/JSON marker非保持を検証します。parser/CAS拒否、malformed root/nested応答、error-only rate-limitを別々に実行し、partialの真の観測時刻とoperational retry期限を区別します。原本だけのexchange export/import/promotion、fresh DDLの削除列/FK/index/generated guard、direct SQLの無効なstaging/診断挿入も検証対象です。成功したhistorical publication、errorを含む部分受理済みGraphQL root、live restart/304、domain証明、provider JSONに残るmarkerはPhase 2境界として開示し、全repositoryで原本ゼロとは主張しません。

新しい試験ではGit/domain共用digestの明示修復、API-only修復拒否、全物理bytesのhash scan・隔離・CAS-41、current値/項目別provenance/transfer/競合/receiver-local check、live部分collection・検索・交換・backup/restoreの既存回帰を維持します。historical parser証明はpre-run exact-definition snapshotと成功した関連試験からだけ再生成し、最終acceptanceはbootstrapなしで実行します。

通常の pytest は外部通信と実 token を遮断します。親と子 Python の guard は合成 HTTP fixture 用の loopback だけを許し、Git transport は file に限定します。依存準備と合成fixture通信を、実Source取得の許可とは扱いません。すべての stateful command は disposable な `--state-dir` を指定します。

package 試験は lock と SHA で検証した wheelhouse を `--offline --no-index --find-links` で使います。wheel と sdist 由来 wheel を新しい venv に導入し、source 外の CWD から console script と `python -m` を実行します。complete packaged DDL、JSON guardとgeneratorの一致、新規catalog初期化、取得・検索・再構築・交換・Git再解析・整合性・backup/restoreを確認します。廃止された公開操作と依存がdistributionからも利用できないことを検証します。

以前のcheckpoint環境は Python 3.12.14、SQLite 3.53.1、uv 0.12.19 でした。今回の実行環境はコマンドで改めて測定し、下限版の保証と区別します。最終結果・失敗・skip・未実行項目は[Phase 1実装記録](phase1-api-original-retirement-implementation.md)と機能handoffに記録します。CI の選択と結果照合は [変更に応じた CI](change-aware-ci.md)、計測は [CI 性能](ci-performance.md) を参照してください。
