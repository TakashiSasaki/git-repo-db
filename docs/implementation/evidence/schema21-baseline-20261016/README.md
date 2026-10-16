# Schema 21 ベースライン復元と P7 統合確認

指定された継承ランタイム障害 **228/228 件を解消**し、今回見つかった
main 固有の fencing テスト障害 1 件も解消した。ランタイムの残存障害は 0 件。
最終全体実行は **3495 passed / 1 failed / 0 errors**。残る 1 件は
Chrome 不足の文書描画試験であり、全リポジトリ成功・リリース受入完了とは扱わない。

全体実行ソースは `74f90adae40ae60076dca33629fa2edbf5763474`、tree は
`b11075b53eb0bda4febc710c46c059dc6edf4054`。後続コミットは証跡・手順の更新であり、
その HEAD で全試験を再実行したという意味ではない。

| PR | 結果・依存 | 確認した HEAD |
| --- | --- | --- |
| [#89](https://github.com/TakashiSasaki/git-repo-db/pull/89) | READY_FOR_OWNER_MERGE_AUTHORIZATION | `660178ff1a881e4482b7a3cde02b51dc50cf2603` |
| [#87](https://github.com/TakashiSasaki/git-repo-db/pull/87) | READY_FOR_OWNER_MERGE_AUTHORIZATION | `c058af3a1be9ba3e9a1b0ba649c789f5bdcd1d75` |
| [#88](https://github.com/TakashiSasaki/git-repo-db/pull/88) | READY_FOR_OWNER_MERGE_AUTHORIZATION、#87 に依存 | `e956cd50b1f25bd95427301cced4741bb68e24f8` |
| [#93](https://github.com/TakashiSasaki/git-repo-db/pull/93) | Collection・共有 fixture、main に依存 | `7dc31256907aff4412170bc3f3ce3069b2ad89f2` |
| [#91](https://github.com/TakashiSasaki/git-repo-db/pull/91) | Job/cache/Search、#93 に依存 | `1700ed37e82a6028cfa40c86b35db7621dd50404` |
| [#92](https://github.com/TakashiSasaki/git-repo-db/pull/92) | 残りの fixture・全体検証、本証跡、#91 に依存 | 実行ソース `74f90ada…`、最終証跡 HEAD は PR 本文に固定 |
| [#90](https://github.com/TakashiSasaki/git-repo-db/pull/90) | 統合準備文書、#88 に依存。Skill 競合解消を A が承認 | `7cbade2928467f3c3ab2350bdc84e275d7057622` |

推奨順は **#89 → #87 → #88 → #93 → #91 → #92 → #90**。
すべて merge commit を用いる。[所有者用手順](owner-merge-plan.md)と PR 本文の
最終 HEAD・実効 tree を再確認する。マージ・auto-merge・release・公開移行・実運用復旧は
実行していない。残る owner 判断は明示的なマージ承認であり、新しい設計判断の要求はない。

## 失敗の原因と修正

最初に見えた 228 件は、Operational を Core に問い合わせた 216 件、Search を
Core に問い合わせた 3 件、廃止済み `incremental_scans` 前提 2 件、未完了 Collection の
継続を必須とする前提 7 件だった。これは最初の例外の分類であり、排他的な最終原因とはしない。
参照先修正後に露出した再開・clock・Coverage 前提、旧 locator 前提も記録した。

本番変更は `src/repo_catalog/adapters/sqlite/index.py` のみ。旧索引世代の参照のために
残した過去文書が新世代にも混入する不具合を、旧本番コードで独立再現した。
新世代は固定 Core snapshot の現在の source key だけから構成し、旧世代の参照が
なくなった派生文書を Search 内で整理する。201 件のデータ、stale-only 200 行のバッチ、
キャンセル、反復・空の再構築、Core 本文履歴保持を検証した。

その他は既存の正しい物理 API を観測するテスト／fixture の修正である。
Core は `catalog.sqlite3`、Operational は `operational.sqlite3`、Search は
`search.sqlite3` のまま。Core に jobs/progress を復活させず、ATTACH・alias・互換 view・
重複テーブル・shadow data は導入していない。Core terminal を欠く未完了 Collection は
安全な新規取得へ戻り、確定済み資源を保持する。Operational の完了フラグだけで
Core 完了を認定しない。元の振る舞いの検証を維持し、skip/xfail は追加していない。

[228 件の分類 JSON](baseline-main/classification.json)には、元／置換 node ID、
元の例外・場所、実際と期待の物理ストア、原因の層、修正・保証、PR、baseline 再現、
最終 test function の場所とハッシュ、独立検証、残存状態を収録した。
[CSV](baseline-main/classification.csv.gz)も同じ内容である。
主たる修正 PR の割当は #93 が 191 件、#91 が 25 件、#92 が 12 件。

## 全体実行と環境の区別

| 実行・照合 | Selected | Passed | Failed | Errors |
| --- | ---: | ---: | ---: | ---: |
| 依頼で与えられた既存 P7 ソース実行 | 3748 | 3517 | 229 | 2 |
| 未変更 main の今回の初回全体実行 | 3491 | 2848 | 332 | 311 |
| 同一 main の複数実行を合わせた node 別照合 | 3491 | 3261 | 230 | 0 |
| 修復後 `74f90ada` の単一全体実行 | 3496 | **3495** | **1** | **0** |

未変更 main は `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`。
初回は `/tmp` の 8.8 GB を使い切ったため、失敗・エラーに環境要因が混入した。
415 node を十分な workspace temp で実行し 413 成功・既存 2 失敗、さらに元の例外が
隠れた 34 node を同一 main で再実行して全件の元の障害を再現した。
228 件は 193 件を初回、1 件を環境再実行、34 件を追加再実行の実際の例外に結び付けた。
照合後の 230 失敗は 228 継承 runtime + main 固有 fencing 1 + Chrome 文書 1。
これは単一の正常な全体実行ではなく、初回の結果を遡って成功に書き換えない。
既存記録の wheelhouse setup error 2 件は依存準備後の別実行で成功しており、
元の 3748 node 実行の結果は変更しない。

最終実行は workspace `TMPDIR` と専用 `--basetemp`、locked dev/docs dependencies、
準備済み offline wheelhouse を使用した。3496 unique starts、3496 JUnit nodes、
10488 phase records が一致し、全 node の setup/call/teardown が各 1 回である。
228 継承 node、main 固有 fencing、P1–P6／互換性 937 node、新規回帰 5 node はすべて成功。

最終失敗は `tests/unit/test_build_docs_site.py::test_staging_allowlist_and_transformation`。
不足するのは `chrome-headless-shell (155.0.8059.79)`。ブラウザーの取得・policy 回避は
行っていない。将来の #89 を含む結合 tree では、最適化後の文書 unit 8 件を別途実行して
全件成功した。74 publication input の一致も確認したが、これは結合 tree 全体の全試験成功
を意味しない。実 hosted Mermaid 10 図の描画証跡は #89 に保持されている。

既定マーカーで未実行の 2 node は次のとおり。

- `tests/e2e/test_github_sync.py::test_nested_pagination_stress_workload`
- `tests/live/test_smoke.py::test_selected_repository`

[D の最終判定](independent-d/FINAL-REVIEW-D.json)、[実行入力・生ログ](final-full/execution.json)、
[JUnit](final-full/full.xml.gz)、[journal](final-full/full-journal.jsonl.gz)、
[stdout](final-full/full.log.gz)を参照する。初回・中断・環境準備失敗も保存した。
`83d3c140` の探索的全体実行は、decoder テストの参照漏れ発見後に 1114 成功で中断しており、
受入結果には含めない。

## 独立レビューと配布物

| Reviewer | 結果と実行範囲 |
| --- | --- |
| A | Architecture 承認。Search/current/store 42、CI selection 90、追加境界検証。最終 decoder 修正・Skill・#90 競合解消も個別承認 |
| B | Lifecycle 20、最終結合 CLI 2、P7 255 + cross-stage compatibility 49 = 304、将来の文書 unit 8 が成功 |
| C | 全 228 継承 node + 新規 5 の独立検証。初回 233 は 211 成功・2 失敗・20 エラー、その後 22 件全成功。単一の 233 全成功とは扱わない |
| D | baseline の元の例外照合、残り 32 全成功、3496 全体結果・10488 phase・937 subset・配布物・分類・証跡を独立照合。APPROVED_FOR_OWNER_REVIEW |

[A](independent-a/ARCHITECTURE-REVIEW.md)、[A 最終補足](independent-a/ARCHITECTURE-FINAL-SUPPLEMENT-74f90ad.md)、
[B](independent-b/REVIEW-B.md)、[B 最終入力結合](independent-b/FINAL-SOURCE-SUPPLEMENT.md)、
[C](independent-c/review-c.json)、[D](independent-d/FINAL-REVIEW-D.json)に対象 SHA と限界がある。

clean git archive からの wheel と sdist 由来 wheel を checkout 外の別環境に導入し、
実 CLI 2 件と、両配布物それぞれで Search 回帰 2 件を実行して成功した。
wheel は両経路で同じ SHA-256
`acae0607661bff850b7c2d58d561edfcf12319f06a01e09ea3f604114468a235`。
120 packaged inputs（118 source/resource + project metadata/lock）は最終ソースまで同一。
sdist 全体は証跡の追加で変わり得るため、同一 artifact とは主張しない。
[配布物ハッシュ](independent-d/distribution-artifacts.json)と
[最終ソース結合](independent-d/distribution-final-binding.json)を参照する。
配布バイナリ・wheelhouse・catalog・backup・venv・cache は本証跡に収録しない。

現行の implementation-boundary、callsite-dependencies、P1 schema、publication-free
監査、Ruff check/format は成功した。追加で試した旧 `audit_phase2_dependencies.py` は
削除済み `exchange.EXCLUDED` を参照して停止する。script と exchange の blob が
main から未変更であることを記録し、成功した監査や runtime 障害に混ぜない。
Search の ready 公開後に cleanup が reader lock で失敗し得る診断反例も保存した。
全 rebuild phase の原子性の保証はなく、これは本番拡張を要求する契約違反とは判断しない。

## P7・統合の境界

#88 自身の最終 HEAD は凍結実行ソース
`178ddbaa8fa06f52aff4993730205c5a38da91f4`（tree
`9740ad1a91f367192bb31ce9777d039c2bb4729b`）と 368 executable input が一致する。
443 証跡 artifact と実行・配布物ハッシュも再照合済みである。
Development CI は完全 P7 受入の代用ではなく、実行していない runtime を成功扱いしない。
Linux の宣言済み復旧範囲を維持し、full Context salvage、空初期化からの完全 Search 再構築、
実ホスト電源断耐久性を新たに主張しない。public Schema 21 と opt-in P1–P7 を混同しない。

新しい公開 runtime 修正を含む結合候補は、#88 の元の「368 入力不変」主張を継承しない。
別途 B の実行した 304 node に対する 424 個の宣言済み runtime/helper/audit input、
全 124 production file の一致を照合した。変更した公開 decoder テスト・文書 unit・
文書 build script・Pages workflow はその限定結合の除外差分として明示した。

main は未変更で、現在の確認可能な設定は `protected=false`、required checks なし、
rulesets なし。現在の path-filtered Pages required-check deadlock は観測していない。
将来これを必須チェックにする場合の待機リスクと、base retarget・実効 tree・親 commit の
確認は [所有者用手順](owner-merge-plan.md)に残した。必要な CI 選択を欠く再現可能な
planner defect はなく、CI 修正 PR は作成していない。

## 証跡の保管

`artifact-index.json` は各 transport file の size/SHA-256 と、gzip 展開後の元の
size/SHA-256 を持つ。元の失敗・agent review・実行ログを改変していない。
過去の `.py` probe は `.py.txt` として保存し、実行対象と区別した。
自作 catalog、実 backup、秘密情報を含むデータは収録していない。

Agent Skill は `.agents/skills/three-store-invariants/SKILL.md` を更新し、正しい物理観測、
SQL 修正後に隠れた再開前提が露出すること、Search stale batch、workspace temp、
親子 CLI の環境結合を記録した。#90 の CI Skill は P7 と Pages の検証済み手順を
双方保持する通常マージで解消し、A が独立承認した。
