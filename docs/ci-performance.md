# CI計測と実行構成

調査開始featureは `84416f90cd1d06b87c605545ecf730cbda75165b`、mainは `9a4110185d7e7abffc291f9cfd118ca71587f998`。P1の同じ248件を固定してbefore/afterを測定し、その後P2を含む全required testsを別に測った。計測JSONの正本は[ci-performance-results.json](ci-performance-results.json)。ローカルの修正中worktreeと、確定SHAのActions結果を区別する。

## 計測方法

`scripts/ci_profile.py run`はcommandのwall clockとexit status、JUnit testcaseのsetup/call/teardown込みduration、file集約、Python/SQLite、CPU count/affinity/cgroup quota、SHA/feature SHA、worker数/modeをJSON/Markdownへ出す。古いJUnitを削除し、欠落/不正なJUnitで成功を装わない。command failureの終了コードは維持する。`compare`はseries/mode/workerごとに中央値・範囲・sample数・failure数を出す。

```bash
uv run --no-sync python scripts/ci_profile.py run --name tests --mode xdist --workers 4 \
  --junit artifacts/ci-profile/tests.xml -- uv run --no-sync pytest \
  tests/unit tests/integration tests/e2e -n 4 --strict-markers \
  -m "not live and not benchmark" --junitxml artifacts/ci-profile/tests.xml --durations=20
uv run --no-sync python scripts/ci_profile.py run --name packaging \
  --junit artifacts/ci-profile/packaging.xml -- uv run --no-sync pytest tests/packaging \
  --strict-markers -m "not live and not benchmark" --junitxml artifacts/ci-profile/packaging.xml
uv run --no-sync pytest tests/unit tests/integration tests/e2e tests/packaging \
  --strict-markers -m "not live and not benchmark" --collect-only -q > artifacts/ci-profile/required-tests.txt
python scripts/ci_profile.py coverage --expected artifacts/ci-profile/required-tests.txt \
  artifacts/ci-profile/tests.json artifacts/ci-profile/packaging.json
python scripts/ci_profile.py compare artifacts/ci-profile/trial-*.json
```

JUnitのfile秒数の合計は並列時のwall timeとは異なる。待機/overlapも含むので、CPU timeやrunner-minutesと読み替えない。CIは主要command/各laneも別profileにし、step summaryと30日保存artifactへ出す。artifactはtiming JSON/Markdown/JUnit/required IDsだけで、DB/cache/payloadはuploadしない。

## 開始時のbaseline

P1 PR run [37345555942](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37345555942) は248 passed / 194.76秒、最小SQLite 161 passed / 4.16秒、demo約9秒。run作成→終了は223秒、job開始→終了は218秒。同じSHAのpush run [37345549896](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37345549896) もsuccess、feedback179秒、runner175秒。後者のtest logは今回取得できず、pytest時間を推定しない。この一組のrunner実測合計は393秒＝6.55 runner-minutes。両方が同時実行され、負荷差もあり、単一hosted logを統計baselineと扱わない。

最近3revisionで同じSHAのpush/PR二重runを確認した（84416f9、62692a8、c8818c）。両方を必須にするrepository ruleは見つからなかった。pull_requestとmain pushを維持し、feature pushの全suite重複を除く。PR番号またはref別concurrencyでsuperseded commitをcancelする。別PR/別branch/mainを同じgroupにしない。これはrunner消費の削減で、queue/CPU競合がfeedbackへ与える改善は独立測定なしに断定しない。

local環境はPython 3.12.14、SQLite 3.53.1、visible CPU/affinity 5、quota `400000 100000`（4 CPU相当）。baselineのP1 tracked test filesを固定し、各configurationを3回実行した。全trialで248 passed、skip/failureなし。

| 248件のconfiguration | Before中央値（範囲） | fixture最適化後中央値（範囲） | 各sample数 |
|---|---:|---:|---:|
| sequential | 133.91（133.44–136.96）秒 | 112.80（111.89–115.58）秒 | 3 / 3 |
| xdist fixed 2 | 70.55（69.77–70.84）秒 | 60.55（60.42–61.02）秒 | 3 / 3 |
| xdist fixed 4 | 44.93（43.52–45.94）秒 | 36.93（35.54–37.70）秒 | 3 / 3 |

9 before + 9 after trialで同じtest ID集合も照合する。fixed4単独の改善は逐次baseline比66.4%、helperも含む最終P1比較は72.4%。helperだけの逐次改善は15.8%。localをhostedの倍率として保証しない。P2追加後の全suite/最終CI値はJSONと末尾記録へ分ける。

## ボトルネックと採用変更

逐次baselineのfile集約中央値はGitHub sync 39.56秒、repository identity 9.88秒、git sync 9.42秒、queries 7.45秒。focused計測でGitHub syncは181 CLI呼出し（応答検証込み28.92秒）、1,708 local Git fixture commands（3.23秒）、14 server shutdown（4.77秒）、181 schema再検査+応答検証（1.64秒）。重なったcategoryなのでこれらを足してtotalとしない。cProfileはoverhead/threadsでcumulative値が歪むため、判断はfocused wall計測と繰り返しsuite trialに基づく。

- CLI JSON schemaはprocessごとに一度check/constructし、**全responseを毎回validate**する。invalid envelope拒否も試験する。実CLI subprocessをmockにしない。
- local HTTP fixtureの`serve_forever` idle pollを0.5→0.01秒にし、shutdown待ちを短縮する。HTTP/API/認証/page/cap/rate-limit境界は実serverのまま。transportのretry/backoffを削除していない。
- pytest-xdistはdev依存だけに追加し、固定4 workerを採用。同じconfigurationがbefore/after各3回成功。state/DB/Git repo/portは既存per-test tmp+port0を維持し、workerごとのHOME/XDG configも隔離する。source fixtureのsession共有はしない。
- CIは1 jobのまま。packaging2件は独立逐次stepにし、lock/hash検証wheelhouse、新venv、offline/no-indexの実配布試験を維持する。
- JUnit/test IDの全required集合照合で、normal/packagingの抜け・重複・skip・failureを拒否する。最小SQLite laneは追加の独立coverageとして全P1 constraintsとP2を実行する。

xdist4はsame runnerでCPUを多く使うが、4 jobsを増設しない。runner-minutesはjob wallで評価する。CPU-secondとpeak memoryの増加はrunner時間削減と別で、この計測はCPU profilerではない。

GitHub syncの逐次file中央値は30.08秒になったが、多数の実CLI起動・DB init・Git fixtureが残る。最適化後xdist4のfile集約は34.40秒で、parallel競合によりcase単体は遅くなり得る。coverageを保つためCLI/Git境界の置換・fixture使い回しは採用しない。remaining slow filesはJSONに保存する。

## 採用しなかった構成と追加コスト

`-n auto`は使わない。worker2も安定したが、このquotaではworker4より約24秒遅い。xdistが安定し十分なgainを得たため、別job shardingの実装は採用しない。file-weightで2 shardsを検討してもGitHub sync単独が約30秒の下限になり、setup/build/wheelhouse/min-laneの重複やjob startupを増やす。単純なfile数分割や多くのtiny jobsは避ける。将来xdistで共有state問題が出た場合はJUnit file weightでlargest-firstに分配し、両shardのtest ID和集合を同じcoverage gateで検証する。

Ruff/FTS/doctor/build等の短いstepは削らない。SQLite 3.46.1 lane、offline demoも維持する。doc path filterは導入しない（SQL/契約はdocs配下）。retry/xfail/skipによる速度改善はしない。

P2のwrite guard試験で旧pysqlite3 bindingに接続auditがないことを発見した。最小laneはCPython stdlib binding＋固定SQLite amalgamationをhash確認してbuildする準備へ変更した。cold準備通信/compileの追加コストと、P2 fault/guard試験を増やしたlane時間をCIで明示測定する。これはbinding保証を維持するための追加で、旧4秒laneと同じcoverage/timeとは主張しない。通常app/packageのSQLite providerは変更しない。

## regressionの見方

CI artifacts/step summaryを毎run残す。`--reference docs/ci-performance-baseline.json`は同じruntime/lane/worker contextなら中央値比+50%のadvisoryを出し、異なるrunnerなら生データを残して比較しない。hard timing gateはない。基準更新はPython/SQLite/CPU、coverage変更、複数normal runの中央値/範囲を記録して行う。単一hosted runだけで成功/回帰を確定しない。

最新hosted値・最終local full suite値は結果JSONへ追記する。PR CIはmerge refのSHAとfeature SHAを両方保存し、最終feature commitのchecksを確認する。P2 validationは実データmigrationの証明ではない。

pre-push全suiteはnormal316件+packaging2件を3回実行し、全318 IDsを各回照合した。normal+packagingの中央値は 40.889秒、範囲 [40.18, 41.18]秒。P1の248件比較とはcoverageが異なる。最終guard/capacity調整と確定SHAのgate/CIは別に確認する。

## P2の最初のhosted結果と最小SQLite追加実験

feature `003f8e487773cf1d7b941786985759a978390d5c` の[run 37366302524](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37366302524)は全成功。同じfeature SHAのrunはPR用の1件だけだった。Python 3.12.14、native SQLite 3.45.1、CPU/affinity 4で、次を測った。

| 区間 | P1比較run | 最初のP2 run |
|---|---:|---:|
| 通常pytest | 194.76秒（packaging込み248件） | 81.69秒（316件） |
| packaging | 上記に含む | 3.79秒（2件、逐次） |
| 最小SQLite試験 | 4.16秒（161件） | 40.21秒（225件、逐次） |
| SQLite binding準備 | 旧wheel準備 | 17.19秒（pinned source compile） |
| offline demo | 約9秒 | 8.16秒 |
| job開始→終了 | 218秒 | 167秒 |
| run作成→終了 | 223秒 | 205秒（queue 38秒） |

比較runは各1 sampleで、coverageとbinding準備も異なる。hosted中央値や並列化単独の効果として扱わない。normal pytestの短縮とrunner消費の減少は確認できたが、feedbackにはqueueが含まれる。二重runのP1実測合計393秒に対しP2は167秒だった。run数の半減とjob自体の短縮を分けて評価する。

新たなボトルネックとなった225件の最小SQLite laneも、同じtest ID集合を保ち、逐次/2/4 workerを各3回測定した。各workerはtest import前にprepared CPython bindingを明示loadし、実際のSQLite versionが3.46.1であることをassertする。親processのversion表示だけでminimum保証としない。

| 225件、SQLite 3.46.1 | local中央値 | 範囲 | samples / failures |
|---|---:|---:|---:|
| sequential | 17.372秒 | 17.177–18.033秒 | 3 / 0 |
| fixed 2 | 10.000秒 | 9.551–10.209秒 | 3 / 0 |
| fixed 4 | 6.248秒 | 5.829–6.814秒 | 3 / 0 |

fixed4を採用し、minimum laneの全225件を維持する。local中央値では64.0%短縮、追加jobやsetup重複はない。worker binding bootstrapが唯一の追加isolation処理。CIのcold準備17秒は保証のため維持し、ネットワークguardやpackagingには変更を加えない。最小laneを省く構成、強制retry、別job分割は採用しない。

上記benchmarkの後、既存hardlink aliasによるsource/cache write回避を3件の回帰試験で塞いだ。最終configurationはnormal319件を4 worker、packaging2件を逐次、minimum228件を4 workerで同一jobに実行する。225件/318件の過去sampleを新件数へ書き換えない。確定feature SHAの最終hosted測定は[PR #1のchecks](https://github.com/TakashiSasaki/git-repo-db/pull/1/checks)、step summary、`ci-profile-<run-id>-<attempt>` artifact、PRのvalidation記録を参照する。JSONには第一P2 runと複数local trialを保持する。単一hosted sampleによるhard thresholdは設けない。

追加修正後の全321件も3回成功し、元の318 IDsが全て残ることと新しい3 IDsを毎回照合した。normal + packagingの中央値39.824秒（38.176–40.266）、minimum228件は5.998秒（5.630–6.337）。`ci-performance-baseline.json`はこの319件normal laneの3 trial、Python/SQLite/CPU条件を使って更新した。過去225件の逐次/2/4比較と最終228件を同じcoverageの比較として扱わない。

`a0f5b8b`のrun 37368121717 attempt 1/2は、[GitHub Actions runner割当遅延incident](https://stspg.io/c11dc9nb1zdq)と同じ時間帯にrunner未取得で終了した。annotationは`The job was not acquired by Runner of type hosted even after multiple attempts`、runner ID 0、step 0件で、test failure sampleではない。各待機約15分をrunner実行時間やpytest時間として計上しない。retry/skipでテスト失敗を隠す処理は追加していない。失敗/再実行/最終HEADをPR検証記録へ残す。

## 最終実装のhosted計測

hardlink修正を含むcode SHA `ff4de5ff64451cd12e7252f18a7f89e1ffd14d54` の[run 37372043596](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37372043596)は全成功。merge checkoutは`ce21544d439253f19887a3f1acf988f558cdd9d1`。Python 3.12.14 / native SQLite 3.45.1 / CPU・affinity 4で、minimum workerは全て3.46.1を確認した。P1からの全required testsを含む321 IDs照合、packaging、minimum228件、demo、timing artifactまで成功した。

| 区間 | P1比較 | 最初のP2 | 最終実装 |
|---|---:|---:|---:|
| normal pytest（coverageは各段階で異なる） | 194.76秒 / 248件、packaging込み | 81.686秒 / 316件 | 64.545秒 / 319件 |
| packaging | 上記に含む | 3.791秒 / 2件 | 2.877秒 / 2件 |
| minimum SQLite | 4.16秒 / 161件 | 40.211秒 / 225件、逐次 | 15.039秒 / 228件、4 worker |
| binding準備 | 旧wheel準備 | 17.190秒 | 14.882秒 |
| offline demo | 約9秒 | 8.161秒 | 6.588秒 |
| job実行 | 218秒 | 167秒 | 121秒 |
| feedback（run作成→終了） | 223秒 | 205秒 | 172秒 |
| queue | 約5秒 | 38秒 | 51秒 |

各列は異なるrevisionのhosted sample 1件で、統計的中央値ではない。minimum並列化単独の効果には、同じ225件のlocal 3+3 trialsを使う。runner差/負荷によるnormal laneの揺れをminimum並列化の効果へ加算しない。

実行critical pathは218→121秒（44.5%短縮）、このrevisionのfeedbackは223→172秒（22.9%短縮）だった。P1二重runの実測6.55 runner-minutesに対し、最終revisionは1 run / 2.02 runner-minutes。job数・setup数は増えず、packagingの逐次性とminimum互換性も保つ。4 test workersは逐次より同時process数/peak memoryを増やすが、CPU-seconds/peak memoryそのものは測定していない。失敗した旧revisionの割当待ちを含む開発全体が172秒で終わったという意味ではない。

残るfile集約上位はGitHub sync 58.291秒、P2 foundation 55.492秒、repository identity 13.632秒、git sync 13.083秒。並列時の集約秒数はoverlapする。main lane64.545秒が依然最大で、実CLI/Gitと各P2 fresh workerの起動・DDL/proof検証が残る。ここから先の最適化は新しい測定に基づいて判断する。
