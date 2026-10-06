# 変更に応じた CI

CI は [現在の policy](../scripts/ci_dependencies.json) と有効な Git tree からチェックを選びます。通常の lane は `tests`、installed wheel / sdist は逐次 `packaging`、静的検査は `static`、SQLite 機能と doctor は `smoke` です。一つの Python/SQLite binding を使い、独立した SQLite-minimum lane、過去の phase lane、件数・node ID 下限、GitHub artifact の再利用判定を廃止しました。

PR の初回・再開などは merge-base から実際に試験する merge tree への差分を使います。`synchronize` は event の直前 head (`before`) から実際の merge tree への差分を使い、今回変わった入力を選びます。`before` が無効・欠落・取得不能、または現在の feature の祖先でなければ全体へ広げます。現在の base 由来の code が直前 head に含まれなければ、その差分も全体を選びます。main push は `before` から試験 tree への差分です。rename の両側と削除も NUL 区切りで読み、path を shell code として実行しません。

- 現在の leaf test の変更は、その file と静的検査を選びます。
- source、共通 fixture、依存 lock、CI policy、importer は現在の acceptance 全体を選びます。
- 現行 runtime/schema/import contract は `src/**`、CI contract は policy/shared inputs として全体を選びます。
- policy に明示した過去の schema-hardening SQL/JSON/CSV は report inputs です。実GitHub検証 JSON も evidence/report input のままです。拡張子だけで executable と扱いません。未分類の新規 SQL/JSON/CSV は全体へ広げます。
- 通常の prose だけの変更は、読み取りと非空検査を行います。
- 未知の依存、比較履歴の欠落・不正、explicit full は現在の acceptance 全体へ広げます。

main push だからという理由で無条件の full acceptance は行いません。manual full は明示的な選択です。既知の prose 以外を推測で除外しません。

現在の manifest は新しい catalog3 runtime と救出の動作試験を中心にし、検証済みの通常試験と保護境界を含みます。過去の phase export や古い DDL pin の試験は現行 acceptance の下限にしません。manifest の入れ替えは、残る動作と安全条件を現行試験が覆うように行います。

実行前に選択した file の node ID を収集し、結果の JUnit と exactly once で照合します。失敗、skip、欠落、重複、余分な ID、別 run / attempt / SHA の古い結果、版の違う binding は成功扱いにしません。確定した CI の証跡は clean tree と一致する必要があります。

`plan.json` は現在の対象、対象外の `excluded_files`、未実行の `unexecuted_files` を保存します。成功した選択実行も、現在の全 acceptance を実行していなければ `full_acceptance=false` です。過去の成功を今回実行した試験として数えません。`validation-manifest.json` はすべての選択チェックが照合できた場合だけ作ります。失敗時は raw JUnit/profile を artifact に残します。

`synchronize` の prose-only 成功は今回の prose 検査の成功であり、過去の runtime 試験が成功した証明ではありません。直前の CI が失敗・未実行・cancelled でも、その結果を再利用しません。仕上げの handoff は、完了した full acceptance の code SHA と run を明記してから更新し、その後の prose-only head は runtime 未実行として記録します。実行中に push すると concurrency 設定で前の run が取り消されるため、最終 full run が完了するまで待ちます。

```bash
uv run --no-sync pytest tests/unit/test_ci_plan.py tests/unit/test_ci_profile.py tests/integration/test_ci_execution.py -q
```

[過去の選択結果](ci-selection-results.json) は `historical-only` です。過去の件数・承認結果は現行の acceptance gate ではありません。
