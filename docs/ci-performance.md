# CI 性能

[scripts/ci_profile.py](../scripts/ci_profile.py) は command の終了コードを保ち、wall time、実際の Python/SQLite、Git SHA、dirty-tree 状態、worker 数、JUnit を JSON と Markdown に保存します。`tests` の既定値は大きな集合で4 workers、小さな選択は逐次、`packaging` は2 workersです。並列実行は `worksteal` で空いたworkerに未実行ケースを割り振ります。`--workers N` で指定でき、1なら逐次です。選択済みlaneではケース数を超えるworkerを作りません。全試験を各 layer や別 SQLite binding で重ねて実行しません。

```bash
python scripts/ci_profile.py run --name focused --junit artifacts/ci-profile/focused.xml -- uv run --no-sync pytest tests/integration/test_catalog3_schema.py --junitxml artifacts/ci-profile/focused.xml
python scripts/ci_profile.py compare artifacts/ci-profile/focused.json
```

計測は補助情報です。速さだけで動作や保護境界を落としません。pytest の file 時間は setup/call/teardown の累計で、並列 lane の wall time とは異なります。異なる runner や binding の値を同じ性能保証として比較しません。`--reference` による warning は advisory で、合否条件ではありません。

CI artifact は plan、選択 ID、JUnit、command profile、最終の照合結果を保持します。DB、cache、token、取得した payload は upload しません。変更に応じた選択と、full / 部分実行 / 対象外の報告は [変更に応じた CI](change-aware-ci.md) を参照してください。

[旧性能結果](ci-performance-results.json)、[旧計測 baseline](ci-performance-baseline.json)、[旧選択結果](ci-selection-results.json) は `historical-only` の参考資料です。過去の phase・SQLite-minimum lane・試験件数・node ID は現行の下限や再実行要求ではありません。今回の最終実行結果は機能 handoff と新しい profile に記録し、未実行項目を明記します。

## テスト準備の共有

wheelとsdist由来wheel、locked requirementsはpytest実行ごとの一つのdirectoryで一度だけ生成します。OS file lockで他workerを待たせ、全部の生成とhash計算が成功してからreceiptをatomically公開します。失敗したprefixを成功扱いにせず、公開済み入力の破損も拒否します。導入先venv、HOME、DB、Git repository、HTTP serverはvariantごとに独立です。

Git fixtureのtree作成では、同じrepository内でGitが実際に書いた同じblobを再利用します。別repository/formatへは共有せず、loose objectがなくなった場合はGitで再生成します。直接の`blob()`呼び出しは従来通りGitを実行します。各試験のcatalog初期化、domain検証、FK/integrity、backup/restoreなどは維持します。

```bash
uv run --no-sync python scripts/ci_execute.py current --lane tests --workers 4
uv run --no-sync python scripts/ci_execute.py current --lane packaging --workers 2
```

workerを増やす効果はCPU quota、I/O、メモリに依存します。別worktreeの同じ環境で、baselineと変更後を同時実行せずに測定します。生profileは`artifacts`、実測と最終acceptanceは提出PRのbodyに記録し、一度の測定を性能保証として扱いません。
