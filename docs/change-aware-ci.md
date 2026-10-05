# 変更に応じた保守的CI

PR #1のP1/P2を作り直さず、既存`tests / offline` jobのstepを条件付きにする。main pushとmanual dispatchはfull acceptanceを維持する。PR/ref別concurrency、固定4 worker、逐次packaging、SQLite 3.46.1、offline guardは維持する。branch protection設定は変更しない。

## 正本と依存境界

正本は [`scripts/ci_dependencies.json`](../scripts/ci_dependencies.json)。[`ci_plan.py`](../scripts/ci_plan.py)はstdlibとlocal Gitでplanを作る。mapping/policyを変えた場合は新policyのfull acceptanceが必要で、旧policyの成功をそのまま使わない。

| lane | 入力・検証範囲 |
|---|---|
| legacy | 残りのunit/integration/E2E。CLI、Git/HTTP、DB、query、cache等 |
| schema | 完全DDL、断片DDL、契約、CSV/target inventory/生成Markdown、不変条件、v2 audit/design |
| p2 | foundationとprotocol。schema validator/audit、migration、fixture、workerへの推移依存も含む |
| ci | profiler/planner/evidence/gateとworkflow連携試験 |
| packaging | wheel/sdist由来wheelのoffline導入、CLIと同梱resources。逐次隔離 |
| minimum-schema / minimum-p2 | 従来の4 P1 filesと2 P2 files。audit対応SQLite 3.46.1で独立実行 |
| static / smoke / build / demo | Ruff、FTS/doctor、build/export、既存offline-recovery demo |

`src/**`、lock/build設定、`tests/support/**`、全階層conftest/init、SQLite preparation/driverは共有依存として広く再実行する。demoは`test_cache.expire`/`test_github_sync.configure`とCLI/Git/HTTP fixtureをimportするためlegacyとの依存を持つ。P2だけの変更にlegacy HTTP/Git E2E依存は見つからず、対応するschema/P2とminimumを選ぶ。leaf testは所属groupを選ぶ。未分類helper/新しい未知pathはfullへ倒す。新しいimport、file read、subprocess境界を追加する際はmappingもレビューする。

prose/reportは列挙したpathだけ。`docs/ci-performance-results.json`と`docs/ci-selection-results.json`は測定report、`p2-foundation.md`は実装・運用記録で、application/schema fixtureは本文を読まない。stdlibでJSON構造・有限数、非空本文、local Markdown linkを確認する。`ci-performance-baseline.json`はprofiler入力なのでproseではない。DDL/JSON/CSV/生成`table-conversion.md`はschema入力で、docs全体をskipしない。生成Markdownもgeneratorとのbyte一致を試験する。

sdistにreport bytesが同梱され得るが、installed CLIのresources/metadataやpackaging assertionはそれらを読まない。reportだけの更新では既存packaging成功を再利用できる。build設定・package resources・fixture/wheel準備を変えた場合は再実行する。

## 比較と証拠

PRはmerge-base→feature HEADの累積diffを`git diff --name-status -z --find-renames`で読む。renameは旧/新path、deleteも残す。HEAD^や直近pushだけを基準にしない。main pushはbefore/after、history欠落・複数merge-base・truncation・未知pathはfull。checkoutは全履歴を取得し、eventのbase/featureと実merge parentを照合する。local使用はbaseがfeatureのancestorの場合にfeature treeを使える。tree証拠を記録する際はcleanなcommit済みcheckoutを要求する。

再利用は次を全て満たす**一つのfull acceptance artifact**に限定する。

- 同じrepository/PRの`pull_request` run。fork、異なるworkflow、failed/cancelled/queued/partialは不可。
- `offline` jobと必須final gateがcompleted/success。run/attempt、feature/base、artifact所属、期限、download SHA-256、manifest bytesを確認する。
- 同じbase、prior featureが現在featureのancestor。force-push/unknown historyはfull。base更新も保守的にfull。
- Actionsの`pull_requests` linkのhead/base SHAはPR更新で変化するlive metadataなのでhistorical revisionに使わない。immutableな`run.head_sha`、manifest、実Git merge parentsを使う。
- tested merge treeから各laneのmode/type/blob OIDを再計算し、policy、lock/依存、Python ABI/version、native SQLite、OS/arch、runner image/compiler、uv pinを照合する。
- 全lane fresh/pass、complete collection、minimum coverage、selection digestが正しい。

現在のmerge SHA自体が過去と同じである必要はない。reportで変わるblobは該当application laneに含めず、実効入力が一致することを示す。累積PRにP2変更が残っていても、検証済み入力と一致すればreuseする。先行未検証codeがあればそのlane fingerprintが異なり再実行する。

metadataは最新5 runの中から同PRの最新successを候補にし、最大1 artifact・4 API callsと必要なら1 Git commit fetchだけを使う。APIはGET/read権限だけ。signed downloadへのredirectでAuthorizationを外し、archiveを展開せずmanifestだけ読む。不足/期限切れ/不一致はfull。legacy artifactは新gateのmanifestを持たないので性能baselineとしてのみ利用する。reuse-only runを次のanchorへ連鎖させないため、連続report更新や候補外の古いfull証拠では再びfullになる場合がある。一般的なremote result cacheは作らない。

## coverageと準備

plan JSON/Markdownにselected/reused、path/推移依存、selection digest、lane-input fingerprint、prior run、fallback理由を出す。reports/final gateは毎回実行する。dependencies/wheelhouse/minimum bindingは必要なselected laneがある時だけ準備し、不要ならnot_applicableと記録する。binding/build cacheはtest evidenceと扱わない。

fresh testがあれば、実行前に**全required collection**を取得してgroupへ分ける。selected集合を先に固定し、JUnit/profileでpassedをexactly once照合する。skip/xfail、失敗、欠落、重複、余分なID、別run/attemptの古い出力は拒否する。full modeは全collectionを実行する。既存`ci_profile.coverage`もselected集合に対して使用する。追加試験を含めたcollectionを取得し、検証済み321 required IDs / 228 minimum IDsを[`ci_required_baseline.json`](../scripts/ci_required_baseline.json)でcoverage下限にする。改名/整理する場合はbaselineとpolicyの明示レビューが必要。

20件未満のnative/minimum selectionは逐次、20件以上は固定4 worker。packagingは常に逐次。selected stepのifが誤ってskipされた場合も`always()`のfinal gateが出力欠落を拒否する。workflow自体はpaths-ignoreで消さず、required check名を維持する。

minimum bindingの冷準備はreviewed CIで24.882秒だった。まず不要なcompileを完全に除く方式を採用し、ABI/toolchain/source hash/auditを検証するpersistent binary cacheは今回は追加しない。selected時は従来のhash固定ソースから再現可能にbuildし、実version/audit、P1/P2能力を試験する。従ってbinary cache hitの互換性を主張せず、planのcache statusは`not-enabled`。

## local使用

開発中はsynthetic planner testsを先に実行する。外部API不要。

```bash
uv run --no-sync pytest tests/unit/test_ci_plan.py tests/unit/test_ci_evidence.py \
  tests/integration/test_ci_execution.py tests/unit/test_ci_profile.py -q
```

commit済みclean checkoutのfull planを作る。

```bash
python scripts/ci_plan.py --full --output artifacts/ci-profile/local-plan
python scripts/ci_execute.py reports --plan artifacts/ci-profile/local-plan/plan.json
# 通常の依存/wheelhouse/minimum準備を先に行った場合:
python scripts/ci_execute.py collect --plan artifacts/ci-profile/local-plan/plan.json
python scripts/ci_execute.py run --lane tests --plan artifacts/ci-profile/local-plan/plan.json
python scripts/ci_execute.py run --lane packaging --plan artifacts/ci-profile/local-plan/plan.json
python scripts/ci_execute.py run --lane sqlite-minimum --plan artifacts/ci-profile/local-plan/plan.json
```

`--context JSON`はevent/repository/pr/feature_sha/base_sha/tested_sha/run_id/run_attempt/head_repository/full/before_sha/diff_completeを指定できる。paths/statusはそのGit historyから完全に抽出する。local reuse検証ではdownloadとmetadataを検証した`--evidence JSON`を指定する。synthetic metadataをhosted evidenceとして扱わない。

final gateにはworkflowと同じ`ci_profile run`で記録した準備/static/smoke/build/demo/cheap commandの出力も必要。任意の一部commandだけを実行してfull acceptanceと報告しない。CIではcheckout以外のexpensive stepをplan outputsで制御し、最後に`python scripts/ci_execute.py gate`を必ず実行する。

## 計測と範囲

JUnit testcase aggregate秒とcommand wall秒を分ける。metadata lookup、planning、report validationもwall/profileを残し、selection内部時間、fresh/reused/minimum counts、準備cache statusをmanifestへ記録する。job runner時間とrun queue/feedbackはActions timestampsから別に算出する。比較記録は[CI性能](ci-performance.md)と`ci-selection-results.json`に置く。異なるfresh test集合や1 sampleから改善率を作らない。

実DB/旧cache、converter runtime、P1 DDL/契約、通常migration経路は変更しない。P2 archive_completeはvalidated/activeではない。FTS/ANALYZE derived source認識、P2→P3 phase handoff、normalized conversion、offline replay、新runtime/first sync、実データdry-run/切替は[実装計画](schema-hardening/implementation-plan.md)のP3〜P7へ残す。
