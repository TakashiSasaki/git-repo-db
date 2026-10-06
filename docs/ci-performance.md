# CI 性能

[scripts/ci_profile.py](../scripts/ci_profile.py) は command の終了コードを保ち、wall time、実際の Python/SQLite、Git SHA、dirty-tree 状態、worker 数、JUnit を JSON と Markdown に保存します。`tests` は大きな集合で固定 4 workers、小さな選択は逐次、`packaging` は常に逐次です。全試験を各 layer や別 SQLite binding で重ねて実行しません。

```bash
python scripts/ci_profile.py run --name focused --junit artifacts/ci-profile/focused.xml -- uv run --no-sync pytest tests/integration/test_catalog3_schema.py --junitxml artifacts/ci-profile/focused.xml
python scripts/ci_profile.py compare artifacts/ci-profile/focused.json
```

計測は補助情報です。速さだけで動作や保護境界を落としません。pytest の file 時間は setup/call/teardown の累計で、並列 lane の wall time とは異なります。異なる runner や binding の値を同じ性能保証として比較しません。`--reference` による warning は advisory で、合否条件ではありません。

CI artifact は plan、選択 ID、JUnit、command profile、最終の照合結果を保持します。DB、cache、token、取得した payload は upload しません。変更に応じた選択と、full / 部分実行 / 対象外の報告は [変更に応じた CI](change-aware-ci.md) を参照してください。

[旧性能結果](ci-performance-results.json)、[旧計測 baseline](ci-performance-baseline.json)、[旧選択結果](ci-selection-results.json) は `historical-only` の参考資料です。過去の phase・SQLite-minimum lane・試験件数・node ID は現行の下限や再実行要求ではありません。今回の最終実行結果は機能 handoff と新しい profile に記録し、未実行項目を明記します。
