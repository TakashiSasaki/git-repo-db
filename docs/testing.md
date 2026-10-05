# 検証方法

依存準備は`uv sync --locked --group dev`、`uv run --no-sync python scripts/prepare_wheelhouse.py`、最小SQLite lane用の`uv run --no-sync python scripts/prepare_sqlite_minimum.py`です。後者はLinux CPython 3.12とC compilerが必要です。取得とテスト実行を分離します。
標準試験は実アカウントや実tokenを不要にし、外部通信を遮断します。
親pytestと子Pythonにはloopbackだけを許可するsocket guard、Gitにはfile-only transportを適用します。
未知の合成API要求、API版やdummy認証headerの欠落はfixtureが拒否します。

```bash
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync pytest tests/unit tests/integration tests/e2e --strict-markers -m "not live and not benchmark" -n 4
uv build --out-dir artifacts/dist
uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file artifacts/runtime-requirements.txt
uv run --no-sync pytest tests/packaging --strict-markers -m "not live and not benchmark"
uv run --no-sync python scripts/run_sqlite_minimum_tests.py
uv run --no-sync python scripts/demo.py --work-dir artifacts/demo-run-001 --scenario offline-recovery
```

Git fixtureはplumbingで生成し、author/committer/time/parent順を固定します。
alpha/beta/empty、S1/S2、force-push・branch削除、9→7出現、SHA-256 repo、空/巨大/binary/改行差/非UTF-8を検証します。
期待値は固定仕様、元bytes、外部digestコマンドから作り、アプリimporterをオラクルにしません。

API fixtureは全PR状態・文書種別、101 thread/101 replies、REST/GraphQL統合、A→B→A、独立watermark、cap、rate limit、ETag、部分応答を含みます。
停止試験は明示的に有効化したhookの到達通知で位置を確定し、sleepで停止地点を推測しません。
SQLITE_FULLは一時DBのmax_page_countで再現し、ホストのディスクを埋めません。

package試験はlock/SHA検証済みwheelhouseを`--offline --no-index --find-links`で使い、wheelとsdist由来wheelを新規venvへ導入してsource外CWDから起動します。既存uv cacheのregistry metadataがなくても実行できます。
import元を確認し、console scriptとpython -mの両入口、migration/schema/GraphQL等の同梱資源を利用します。
FTS対応CIでは再構築の成功、利用不能構成では明示操作のexit 4とscanの同値性を検証します。

live/pilot/benchmarkは標準試験とは別です。実認証、対象、容量/要求予算が設定された後に明示実行します。
実行結果・未実行項目・残件はimplementation-status.mdに記録します。

独立target DDL/機械契約の下限laneはSQLite 3.46.1。online準備で`uv run --no-sync python scripts/prepare_sqlite_minimum.py`を行い、`uv run --no-sync python scripts/run_sqlite_minimum_tests.py`をoffline実行します。通常アプリのSQLiteやmigration runnerを差し替えません。

CIのJUnit/JSON/Markdown計測、全required test ID照合、worker隔離、基準更新は[CI性能](ci-performance.md)を参照します。P2 converterの全通信禁止は、通常試験のloopback guardより強い専用workerのseccomp/audit policyです。
