# 検証方法

Catalog3 Core Schema 21 / Operational Schema 1 / Search Schema 1 の通常動作とPhase 1のAPI原本依存機能廃止、および Three-Store 境界（Core, Operational, Search）を、一つの Python/SQLite binding で検証します。v2 importerと救出workspaceは廃止済みです。最小 SQLite 版の独立 lane と過去の phase 互換性・試験件数・node ID 下限は廃止しました。実行時の版と機能を記録し、FK、recursive triggers、FTS、WAL の既知の修正条件など、必要な正しさの条件は維持します。

依存取得は試験より先に行います。

```bash
uv sync --locked --group dev
uv run --no-sync python scripts/prepare_wheelhouse.py
uv run --no-sync python -c 'import platform, sqlite3; print(platform.python_version(), sqlite3.sqlite_version)'
uv --version
```

編集中は変更した機能の試験を実行します。ADR 0001（Development and Release Validation Lifecycle Architecture）に基づき、開発時の検証（Development Validation）とリリース受入（Release Acceptance）を明確に分離します。開発時の pull request や通常編集では、局所的な対象試験（focused tests）および軽量な静的検査（Ruff check/format、構成検証、schema audit、CLI doctor smoke）を実行し、編集ごとに全試験（full-suite）の網羅実行を要求しません。リリース検証を完了する際のみ、クリーンな作業ツリーで完全な受入試験を実施し、ローカル release receipt を生成・照合します。

```bash
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync python scripts/ci_profile.py profile tests/unit/test_ci_plan.py
uv run --no-sync python scripts/ci_execute.py current --lane tests
uv run --no-sync python scripts/ci_execute.py current --lane packaging
```

局所的な編集・検証では `scripts/ci_profile.py profile <pytest-args>` を使うことで、独立した出力先と一意な `invocation_id` を持った実行プロファイルおよび append-only JSONL ジャーナルを生成できます。
また、リリース検証を完了する際は、作業ツリーをコミットして clean な状態にした上で、次のコマンドでローカル release receipt を生成・照合します。

```bash
# クリーンな作業ツリーでローカル release receipt を生成
python scripts/ci_execute.py receipt --output-dir artifacts/ci-profile

# ホスト CI の validation-manifest.json と照合して complete_release_passed を確立
python scripts/ci_execute.py reconcile-release \
  --local-receipt artifacts/ci-profile/local-receipt.json \
  --hosted-manifest artifacts/ci-profile/validation-manifest.json
```

`current` は作業ツリーに存在する現在のpolicy・manifestから対象を選択します。実際のselected/executed node IDsを照合し、新しいretirement試験が選ばれていない場合も隠しません。編集中の結果は dirty-tree 状態を含む生の profile として保存し、確定した Git tree の CI acceptance manifest と区別します。全履歴の試験や phase export は再実行しません。現在の対象から外した試験は CI plan の `excluded_files` に列挙し、選択されなかった現在の試験は `unexecuted_files` に列挙します。

現在の acceptance は、新規初期化・探索・Git/PR/Issue取得、増分取得と部分応答のlive再開、任意通信記録、オフライン照会と検索、停止・domain保全・交換・backup/restoreを対象にします。typed same-owner関係、個別resourceの独立利用、scope/member/terminal/child証拠、canonical Git bytesと原子的intrinsic構造、正確なdomain本文、missing/conflictとExchange closureを検証します。DDLの正本は `adapters/sqlite/schema.py` が全同梱SQLから組み立てる `schema_sql()` です。

API原本・Publication/profile/selection/certificateの本番経路不在、closed modeled JSON、値と項目別根拠の同時更新・COMMIT失敗・revision fence、10,000回更新後の現在状態と未参照shared text、Sourceのpartial scan非削除、latest Coverage候補、empty/nested/foreign scope、stale head A/B、Git SHA-1/SHA-256・途中失敗・missing targets、Exchangeの再送/反転/後着/current drift、CAS共有bytes・CAS-41・no-overwrite restoreを検証します。廃止した機構だけのテストと存続する振る舞いの対応は[exact node対応表](phase2/publication-free-test-disposition.json)に記録します。除去したparser certificateとbootstrapは受入条件ではありません。

四範囲の独立サブエージェント検証（architecture/DDL、acquisition/completeness、Git/Exchange/CAS/scale、最終統合）は、大規模な Schema 20 再設計など明示的に要求されたタスクまたはリリース受入（Release Acceptance）時に適用され、通常の開発 PR（Development PR）ごとに機械的に義務付けられるものではありません。開発 PR では変更の影響範囲に応じた独立レビューを実施し、finding は再現・root-cause修正・回帰テスト・再検証を繰り返します。異なる名前のself-reviewを独立レビューとは扱いません。

通常の pytest は外部通信と実 token を遮断します。親と子 Python の guard は合成 HTTP fixture 用の loopback だけを許し、Git transport は file に限定します。依存準備と合成fixture通信を、実Source取得の許可とは扱いません。すべての stateful command は disposable な `--state-dir` を指定します。

package 試験は lock と SHA で検証した wheelhouse を `--offline --no-index --find-links` で使います。wheel と sdist 由来 wheel を新しい venv に導入し、source 外の CWD から console script と `python -m` を実行します。complete packaged DDL、JSON guardとgeneratorの一致、新規catalog初期化、取得・検索・再構築・交換・Git再解析・整合性・backup/restoreを確認します。廃止された公開操作と依存がdistributionからも利用できないことを検証します。

以前のcheckpoint環境は Python 3.12.14、SQLite 3.53.1、uv 0.12.19 でした。今回の実行環境はコマンドで改めて測定し、下限版の保証と区別します。最終結果・失敗・skip・未実行項目は [Three-Store Boundary ADR 0002](adr/0002-three-store-boundary-architecture.md)、[Schema 20実装記録](phase2/publication-free-implementation.md)、および exact-revision receipts に記録します。CI の選択と結果照合は [変更に応じた CI](change-aware-ci.md)、計測は [CI 性能](ci-performance.md) を参照してください。

Phase 2のexact-tree受入と独立reviewの対象・修正・再検証は[実装記録](phase2/publication-free-implementation.md)、提出PRとそのCI artifactsに記録します。Schema 18の調査snapshotは書き換えません。
