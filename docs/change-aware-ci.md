# 変更に応じた CI

CI は [現在の policy](../scripts/ci_dependencies.json) と有効な Git tree からチェックを選びます。通常の lane は `tests`、installed wheel / sdist は逐次 `packaging`、静的検査は `static`、SQLite 機能と doctor は `smoke` です。一つの Python/SQLite binding を使い、独立した SQLite-minimum lane、過去の phase lane、件数・node ID 下限、GitHub artifact の再利用判定を廃止しました。

PR の初回・再開などは merge-base から実際に試験する merge tree への差分を使います。`synchronize` は event の直前 head (`before`) から実際の merge tree への差分を使い、今回変わった入力を選びます。`before` が無効・欠落・取得不能、または現在の feature の祖先でなければ全体へ広げます。現在の base 由来の code が直前 head に含まれなければ、その差分も全体を選びます。main push は `before` から試験 tree への差分です。rename の両側と削除も NUL 区切りで読み、path を shell code として実行しません。

- `tests/unit`、`tests/integration`、`tests/e2e`、`tests/packaging` 以下で、pytest の標準命名に合うすべての `test_*.py` / `*_test.py` を現在の acceptance として発見します。新規追加・rename に個別 allowlist 更新は不要です。`tests/live` は明示的な opt-in のままです。
- 他の test/helper module から import されていない leaf test の変更は、その file と静的検査を選びます。test module の絶対・相対・同階層 import を AST で検査し、import される test の変更は consumer を落とさないよう全体を選びます。`pytest_plugins`、動的 import や解析できない Python があれば全体へ広げます。共通 fixture の指定は leaf 判定より優先します。
- source、共通 fixture、依存 lock、CI policy、importer は現在の acceptance 全体を選びます。
- 現行 runtime/schema/import contract は `src/**`、CI contract は policy/shared inputs として全体を選びます。
- policy に明示した過去の schema-hardening SQL/JSON/CSV は report inputs です。実GitHub検証と synthetic 検証の JSON も evidence/report input です。非空の JSON object として検証し、不正な JSON、空 object、非有限数を拒否します。拡張子だけで executable と扱いません。未分類の新規 SQL/JSON/CSV は全体へ広げます。
- 通常の prose だけの変更は、読み取りと非空検査を行います。
- 未知の依存、比較履歴の欠落・不正、explicit full は現在の acceptance 全体へ広げます。

main push だからという理由で無条件の full acceptance は行いません。manual full は明示的な選択です。既知の prose 以外を推測で除外しません。

現在の manifest は catalog3 runtime と救出の動作試験を中心に、通常試験と保護境界を含みます。過去の phase export や古い DDL pin の試験は現行 acceptance の下限にしません。不要になった試験の削除も変更として扱い、残る acceptance 全体を選びます。件数の固定下限は設けません。

実行前に選択した file の node ID を収集し、結果の JUnit と exactly once で照合します。失敗、skip、欠落、重複、余分な ID、別 run / attempt / SHA の古い結果、版の違う binding は成功扱いにしません。確定した CI の証跡は clean tree と一致する必要があります。

`plan.json` は現在の対象、対象外の `excluded_files`、未実行の `unexecuted_files` を保存します。四つの通常 test directory の file はすべて対象なので `excluded_files` は空です。live は通常 acceptance の外です。成功した選択実行も、現在の全 acceptance を実行していなければ `full_acceptance=false`、`acceptance_status=selected_checks_only` です。完了した full だけが `acceptance_status=full_acceptance_passed` になります。summary でも選択チェックだけの成功は最終 acceptance の成立を示さないと明記します。過去の成功を今回実行した試験として数えません。`validation-manifest.json` はすべての選択チェックが照合できた場合だけ作ります。失敗時は raw JUnit/profile を artifact に残します。

`synchronize` の prose-only 成功は今回の prose 検査の成功であり、過去の runtime 試験が成功した証明ではありません。直前の CI が失敗・未実行・cancelled でも、その結果を再利用しません。実行中に push すると concurrency 設定で前の run が取り消されるため、最終 full run が完了するまで待ちます。source run が失敗・未完了のまま prose を push した履歴でも、後続の成功が `selected_checks_only` に留まることを回帰試験で確認します。

最終統合の確認は現在も手動です。通常 job の緑色だけではマージ準備の完了を意味しません。次の手順で最終入力と完了証跡を結び付けます。

1. 最終統合 tree を clean commit にし、manual workflow の `full=true`（ローカルなら `ci_plan.py --full`）で acceptance を選択・実行・照合します。失敗・取消・実行中の run は使いません。
2. `validation-manifest.json` の `full_acceptance=true`、`acceptance_status=full_acceptance_passed` と、対象 SHA / tree、run ID / attempt、実行結果を handoff に記録します。
3. plan / manifest の `acceptance_input_hash` を最終 tree の plan と比較します。この hash は prose と明示した report を除く Git tree entries（path、mode、object ID）から作り、runtime、tests、依存、CI policy、未知の入力の変更を検出します。通常 test と shared/executable contract の明示指定は除外より優先します。evidence-only follow-up は同じ hash を持ち、runtime は今回未実行として記録します。
4. base 更新を含む最終マージ候補で hash が異なる場合、その候補の full acceptance を完了させます。hash が一致しても、対応する完了済み full の SHA と run の明示的な確認が必要です。

この fingerprint は結果を自動取得・再利用する機能ではなく、完了証跡を手動で比較するための識別子です。リモート API や artifact の存在を推測して readiness を成立させません。

```bash
uv run --no-sync pytest tests/unit/test_ci_plan.py tests/unit/test_ci_profile.py tests/integration/test_ci_execution.py -q
```

[過去の選択結果](ci-selection-results.json) は `historical-only` です。過去の件数・承認結果は現行の acceptance gate ではありません。
