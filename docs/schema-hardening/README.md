# Schema v2ハードニング：統合オフライン変換と target クエリ

**現在の成果物:** [統合変換・読み取り専用クエリ](integrated-handoff.md)、[P3B identity](p3b-handoff.md)、[P3A source admission・phase handoff](p3a-handoff.md)、[P2基盤・範囲と検証](p2-foundation.md)、[CI計測](../ci-performance.md)、 [P1設計とCI修復](p1-design.md)、[完了一覧・正当な補完経路の仕上げ](p1-lifecycle.md)、[完全target DDL](target-schema.sql)、[機械可読変換契約](conversion-contract.json)、[I01〜I31対応](invariant-contract.json)。通常migration経路と実DBは変更していない。以下の調査・88件成功は前工程の記録。最新HEADの結果は PR checks/本文と統合 handoff で確認する。

対象: `TakashiSasaki/git-repo-db`。調査日: 2026-10-05 UTC。
作業ブランチ: `design/schema-v2-hardening`。
fetchしたremote main、ローカル調査HEAD、過去の基準はすべて`9a4110185d7e7abffc291f9cfd118ca71587f998`。基準とのsource差分は0。
この文書群・診断・fixtureテストを追加する。**実行中のDDL、collector、CLI、migrationは変更しない。新DBへの実データ変換・切替は未実施。**

## 成果物と読み順

1. [不変条件と保証方法](invariants.md)
2. [新スキーマ案](schema-proposal.md)と[実行可能な中核DDL断片](proposal-core.sql)
3. [53テーブルの変換対応](table-conversion.md)、[287列の変換対応CSV](column-conversion.csv)
4. [オフライン変換・検証・切替仕様](offline-conversion.md)
5. [実装計画と未確定判断](implementation-plan.md)
6. [実構築したv2構造JSON](current-schema.json)、[SQL読取り・書込みの参照一覧](source-access.json)
7. [索引候補のsynthetic probe](index-probe.json)

後方互換性は設計要件にしない。取得済みデータと観測事実の保全を要件にする。
新規DBへの変換を第一候補とし、DDL checksumの書換えを変換として扱わない。

## 実構築と抽出

`scripts/schema_audit.py --fixture-schema`で新規一時stateを初期化し、同梱001/002 migrationを本来のrunnerで適用した。
schema_migrationsを含む53 STRICT tables、287 columns、71 FK rows、60 indexes（SQLite自動索引を含む）、2 triggers。
PK/NULL/defaultは`table_xinfo`、FKとdelete/update/deferred以外のpragma属性は`foreign_key_list`、UNIQUE/partial/column/collationは`index_list/index_xinfo`、CHECK・deferred・triggerの正本は`sqlite_schema.sql`に保存した。
PRAGMAの`notnull`単独で論理的NULL可否を判断しない（INTEGER PRIMARY KEYのNULL入力は自動採番）。
空fixtureの構造fingerprintは`8cacdc381210ec34baa88997b1e01d1f8182cb58ed1d2ffe8bb9984df8928f83`。
FTSの仮想table/shadow/indexは実行時に追加され、空fixtureの53には含まれない。実DBではこれらも抽出できるようWITHOUT ROWIDの非登録autoindexを扱った。

`current-schema.json`にはfixture DDLのみを含む。実DBの行・URL・ID・API本文は含めない。
`source-access.json`はSQL文字列の字句検索。動的table名・Python呼出し・filesystemアクセスの完全なcall graphではない。

## 現行経路の照合

| 経路 | 実装と読み書き・保全上の意味 | 関連試験 |
|---|---|---|
| schema作成・移行 | `adapters/sqlite/store.py:migrate/verify_migrations`。FKはconnectionごとにON、v2 rebuild時だけOFF→transaction内FK check。通常queryは自動移行しない。v2 version/checksumだけでは実構造の改変を保証しない | `test_database`、`test_identity_migration`、新audit inventory |
| discovery/identity | `application/collection_service.py:_discover`、`repository_identity.py`。bindingを正本とするがrepoの互換列も残る。API metadata/nameは上書き、nameはdistinct-name集合。M:N membership時刻にはv2 backfill時刻も含む | `test_repository_identity` |
| Git取得/保存 | `adapters/git/importer.py:sync/import_objects/save_blob/manifests`。cacheにintake refsを作り、OID実証後に構造/digest/本文を保存。公開はattempt fenceと保存義務の確認後。同じblob contentは原文一致で確認、SHA候補だけで統合しない | `test_git_objects`、`test_git_sync`、`test_digests`、新ref再現 |
| REST/GraphQL | `adapters/github/collector.py:collection/graphql_response/document`。bodyを共有してもページ・resource observationは別。ページの正規化とcursor更新は同一transaction。一部GETはETagがある場合だけraw responseを保存。inventory/user応答すべてが保存されているわけではない | `test_github_sync`、`test_http_compression` |
| 再開 | `application/job_service.py:resume`はattemptを上書き増分。PR code observationは再開ごとに新規、部分collectionの過去pageはreplayされない。完了collectionはreplay=Trueなら再解析するが通信しない | `test_recovery`、`test_jobs`、新page/watermark再現 |
| 照会 | `query_service.py`、`pr_queries.py`。published roots/current pointers、code observation、coverage、FTS+raw照合を読む。部分取得と0件は分離。DBに通るcross-owner pointerは照会結果を誤らせ得る | `test_queries/search/offline/cli_more`、新pointer再現 |
| backup/restore | `maintenance_service.py:database/restore/check`。backup APIとmanifestを使う。restoreは別stateでdb_instance_id変更、cache/lease/予約を無効化し、旧running jobをinterruptedにする。これは新formatへの意味変換ではない。checkは全てのparent ownershipを調べない | `test_backup`、`test_identity_migration`、新pointer再現 |
| cache | `filesystem/cache.py/capacity.py`。lease、保存義務、locks、予約、quarantine削除を扱う。`content hydrate`は必要ならfetchするため変換手段に使えない。移行で旧cache GC/pressure処理を呼ばない | `test_cache`、`test_content`、`test_recovery` |
| 検索索引 | `sqlite/index.py:rebuild`はDB本文のみで再生成。job/FTS世代を更新しretired tableを削除するため、旧DB上では呼ばない | `test_search_index`、`test_offline`、packaging tests |

コードの現行関数と各tableの具体的な行参照は`source-access.json`。自由文字列をJSONと決め付けず、特に`resource_observations.collection_run`と`pr_events.run_id`は本物のrun FKではない。

## 既知候補の再現結果

`tests/integration/test_v2_hardening_reproductions.py`は**不具合を修正済みとするテストではなく、調査基準の誤動作を記述するcharacterization test**。将来の実装で望ましい不変条件へ置き換える。

| 候補 | 条件・結果 | 根拠・保存済みデータからできること |
|---|---|---|
| 複数refが同じOID | alphaのmainとaliasを同じcommit Nにする。`sync git`はDATABASE_ERROR/exit 5。`UNIQUE(run_id,oid,role)`で衝突。ref/root保存transactionはrollbackし、runはfetching、jobはfailedのまま | `GitImporter.sync` refs capture。共有walk seedとref由来を分離する。失われたDB ref事実を捏造せず、残存intake refsがあれば別の派生証拠として回収 |
| commits/files途中再開 | PR #41の2-page一覧。page 1保存、page 2を503×5で失敗させ、同じjobを再開。latest code observationはcompleteだがordinal=10000のpage 2だけ。page 1は旧code observation、raw 4 pagesは残存 | `GitHubCollector.sync/collection(replay=True)`。部分collection再開は既存pageをreplayしない。全保存pageを同じ安定listingへ再解析できるが、head/baseとscopeを別途照合する |
| collection再利用時watermark | 同じjob/endpointの完了incremental collectionを翌日に再利用。request数は増えず、watermarkだけ翌日へ更新される | `incremental_comments`がcollectionのreturn後に新しいnowを保存。再利用は元scanの境界を使い、新しいscanとして扱わない |

3件とも上記SHAで再現、3 tests passed。再現に使うAPIはloopbackのsynthetic fixture、Git取得先はfileのみ。
pointerの別repo・別documentへの更新もv2のFKと`db check --full`を通ることを別のfixtureで再現した。

## 診断コードと検証範囲

```bash
uv run --no-sync python scripts/schema_audit.py --fixture-schema
uv run --no-sync python scripts/schema_audit.py --database /sealed/offline-copy.sqlite3 --hash-payloads
uv run --no-sync pytest tests/integration/test_v2_hardening_reproductions.py \
  tests/integration/test_v2_schema_audit.py tests/integration/test_schema_proposal_core.py
```

診断はSQLite `mode=ro`/`query_only=ON`/read transactionを使い、存在しないDBを作らない。WAL/SHM/journal sidecarがある場合は拒否する。
CLIではDB fileを前後でSHA-256照合する。違反はcodeと件数のみ、raw row/ID/URL/payloadは出力しない。修復・削除・自動移行・API/Git呼出しはない。
SHA検査は保存済みAPI bodyとdocument bodyについて行う。32MiB超は未検証件数として報告する。cacheのGit closure、全文raw digest、JSONの期待形状、すべてのscopeの意味は証明しない。
違反ゼロでも、過去に保存されなかったデータ、同一件数での誤変換、watermark境界の正当性を証明できない。

前回pilot DBが作業環境に残っているため、これに86項目の読取り専用診断を行い、違反なし・source file前後一致を確認した。非公開artifactにのみ記録し、実データの行・API本文・識別子を公開文書へ転載しない。
これは実DBの**変換テストではない**。提案DDLの制約と不具合再現はfixtureでのみ検証した。

提案DDL断片はin-memory DBでparent ownership、pointer更新/削除、同一seedの複数ref、本文共有と観測の分離を確認する。完全target DDLはP1で独立作成した。P2 archive/map/batch基盤は独立commandで実装した。保存済み Git/PR converter と限定保存ペイロード復元は統合実装へ進んだ。追加再解析と新オンライン runtime は後続範囲で、実データ移行成功を主張しない。

## 今回の検証記録

- 標準offline gate: **88 passed / 128.30秒**。既存76件に、再現3・readonly診断4・提案中核3・列対応2を追加。実Git/file、loopback synthetic API、dummy credential、実SQLite/CLIを利用し外部通信を遮断した。
- listing kind/parent更新保護、complete pointer CHECK、current version削除保護と共有body/version不変triggerをDDL断片に追加後、中核3件を再実行してpassed。
- Ruff check/format、compileallとdiff whitespaceを確認する。実行結果はignored `artifacts/schema-hardening/`に保存する。
- synthetic index probeは各1,000行で実行。pr_observations(pr_id,id)、collections(repo_id,pr_id,kind)はSCAN→covering INDEX SEARCHになる。追加page/サイズはindex-probe.json。これはtarget全DDLの性能評価や実DB容量見積りではない。
- source runtime/001/002/pyproject/uv.lockは調査基準から差分なし。実DBの変更・変換・source cacheのGCは行っていない。
