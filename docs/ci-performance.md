# CI 性能

[scripts/ci_profile.py](../scripts/ci_profile.py) は command の終了コードを保ち、wall time、実際の Python/SQLite、Git SHA、dirty-tree 状態、worker 数、JUnit を JSON と Markdown に保存します。`tests` の既定値は大きな集合で4 workers、小さな選択は逐次、`packaging` は2 workersです。並列実行は `worksteal` で空いたworkerに未実行ケースを割り振ります。`--workers N` で指定でき、1なら逐次です。選択済みlaneではケース数を超えるworkerを作りません。全試験を各 layer や別 SQLite binding で重ねて実行しません。

```bash
python scripts/ci_profile.py run --name focused --junit artifacts/ci-profile/focused.xml -- uv run --no-sync pytest tests/integration/test_catalog3_schema.py --junitxml artifacts/ci-profile/focused.xml
python scripts/ci_profile.py compare artifacts/ci-profile/focused.json
```

計測は補助情報です。速さだけで動作や保護境界を落としません。コマンドの経過実時間（`wall_seconds`）と、各テストワーカーの累積実行時間（`cumulative_test_seconds`）は厳密に区別して記録されます。
テスト実行イベントは append-only の JSON Lines (`.jsonl`) ジャーナルに記録され、`start`、`phase`（`setup`、`call`、`teardown` と `worker_id`）、`finish` の各フェーズを追跡します。これにより、テストセッションが途中で強制終了やタイムアウトした場合でも、クラッシュ前のイベントと経過時間が保全され、途中で中断されたテストが成功として誤認されることを防止します。

各実行には一意な `invocation_id`（`{name}-{timestamp}-{uuid[:8]}`）が付与され、上書きを防止するために `invocations/{invocation_id}.json` に個別プロファイルが非破壊的に保存されます。
CI artifact は plan、選択 ID、JUnit、command profile、`.jsonl` ジャーナル、最終の照合結果を保持します。DB、cache、token、取得した payload は upload しません。変更に応じた選択と、full / 部分実行 / 対象外の報告は [変更に応じた CI](change-aware-ci.md) を参照してください。

[旧性能結果](ci-performance-results.json)、[旧計測 baseline](ci-performance-baseline.json)、[旧選択結果](ci-selection-results.json) は `historical-only` の参考資料です。過去の phase・SQLite-minimum lane・試験件数・node ID は現行の下限や再実行要求ではありません。今回の最終実行結果は機能 handoff と新しい profile に記録し、未実行項目を明記します。

## テスト準備の共有

wheelとsdist由来wheel、locked requirementsはpytest実行ごとの一つのdirectoryで一度だけ生成します。OS file lockで他workerを待たせ、全部の生成とhash計算が成功してからreceiptをatomically公開します。失敗したprefixを成功扱いにせず、公開済み入力の破損も拒否します。導入先venv、HOME、DB、Git repository、HTTP serverはvariantごとに独立です。

Git fixtureのtree作成では、同じrepository内でGitが実際に書いた同じblobを再利用します。別repository/formatへは共有せず、loose objectがなくなった場合はGitで再生成します。直接の`blob()`呼び出しは従来通りGitを実行します。各試験のcatalog初期化、domain検証、FK/integrity、backup/restoreなどは維持します。

```bash
uv run --no-sync python scripts/ci_execute.py current --lane tests --workers 4
uv run --no-sync python scripts/ci_execute.py current --lane packaging --workers 2
```

workerを増やす効果はCPU quota、I/O、メモリに依存します。別worktreeの同じ環境で、baselineと変更後を同時実行せずに測定します。生profileは`artifacts`、実測と最終acceptanceは提出PRのbodyに記録し、一度の測定を性能保証として扱いません。

## 2026-11-07: Linux CI の重複と待ち時間

計測対象は [PR #254 の Pages](https://github.com/TakashiSasaki/git-repo-db/actions/runs/42325801128)、
[同じPRの Access](https://github.com/TakashiSasaki/git-repo-db/actions/runs/42325800842)、
[main の tests](https://github.com/TakashiSasaki/git-repo-db/actions/runs/42326003793) です。
Pages の build-and-validate は約106秒で、そのうち文書ビルド・試験・証跡生成の
一つのステップが約72秒でした。Access は約50秒で、source圧縮と証拠uploadが
それぞれ約9秒、所有権・スキーマ監査が約8秒でした。main の製品CIは並列に
動く2ジョブのうち長い方が約27秒でした。これらは別ジョブの実時間であり、
合算した時間を利用者の待ち時間とは扱いません。

- 文書pytestをPagesの実行時だけ2ワーカーで実行します。収集は従来どおり独立に
  行い、JUnitとのnode ID完全一致、失敗・skipの拒否、別の文書環境と証跡を維持します。
  手元の同一Linux環境で、逐次 `573cd15a` は118件・49.76秒、2ワーカー
  `1efa31ce` は同じ118件・26.97秒でした。JUnitのnode multisetは完全一致しています。
  後者は文書環境に `pytest-xdist` と `execnet` を追加した後の測定です。
  ローカルの直接実行は既定1ワーカーで、Pagesだけ `DOCS_PYTEST_WORKERS=2` を指定します。
- Pagesの独立した `schema_viz --check` は、続く必須サイトビルド内の
  `check_schema_freshness()` と同じIR・生成関数・比較先を使っていたため削除しました。
  ビルド内の実チェック、独立テスト、失敗時の拒否は残します。元のステップは
  GitHubの秒単位の計測で1秒未満であり、大きな時間短縮とは主張しません。
- Accessの成功した通常開発CIで、テスト・配布laneが選択されず、書式検査が
  完了した場合だけ、source archiveをRuff再現用の追跡済み入力に限定します。
  同じ `bde21124` のLinux計測では、全source archiveは208,098,527 bytes・11.95秒、
  対象を明記したarchiveは1,577,415 bytes・0.33秒でした。後者を展開し、保存対象の
  Ruff検査とformat検査の両方が成功することを実行確認しました。先に対象ファイルだけを
  抽出した試案は、依存するPython packageと `__init__.py` の不足でimport分類が変わり
  失敗したため採用していません。現在のarchiveはそれらの分類文脈も含みます。
  source-revisionには範囲・commit・tree・archiveの大きさとSHA-256・formatterの
  SHA-256を記録します。これは完全なオフライン試験再現用sourceではありません。
  失敗時、release、静的検査未実行、またはtest/packaging選択時は従来の全sourceを保持します。

測定は各々1回の観測で、GitHubとローカルの時間を直接比較しません。Accessの
formatter実行は製品CIと一部重複しますが、独立したAccess workflowの検査として残します。
Windows実機・Windows VM CIは通常開発では実行しません。
