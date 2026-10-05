# P1: 独立target DDL・変換契約・制約検証

レビュー入力: branch `design/schema-v2-hardening`、HEAD `2ca0a0f0b80763ca6ab921f5544809c43bbcc8e3`、main `9a4110185d7e7abffc291f9cfd118ca71587f998`。
開始時remote/PRはこのSHAと一致し、最新CI run 37327752971 は86 passed / packaging 2 failed。重複修正はなかった。
本工程はsynthetic fixtureのみ。通常application・migration runner・001/002資源・実DB・旧Git cacheを変更/変換/切替しない。

## 採用する物理構造

完全DDLの正本は [target-schema.sql](target-schema.sql)。独立空DBに構築できる74 STRICT tables、426 columns、159 indexes（自動索引を含む）、250 triggers。
format_idは `repo-catalog/catalog3-p1`、versionは3。未リリースの独立設計formatであり、通常アプリが読める形式とは宣言しない。
DDL hashは [conversion-contract.json](conversion-contract.json) の `ddl_sha256`（ファイルのUTF-8 bytesのSHA-256）を正本にする。新DB identityへ同じhashと新UUIDv4を記録し、source ledgerとは別に識別する。実構築した全column/type/nullability/default/PKは [target-inventory.json](target-inventory.json)、FK/UNIQUE/CHECK/trigger/indexの正本は完全SQL。
SQLite下限は **3.46.1**。各接続はforeign_keys=ON、recursive_triggers=ON。今回のSQL試験はWALを利用せず、アプリのWAL runtime gateを緩めない。

| 分類 | 採用・判断 |
|---|---|
| 今回必須 | scoped owner/current pointer、親identity/来歴固定、factとprogress分離、root seed+origins、stable listing、payload+page occurrence、typed source archive、conversion ledger/ID map、typed resume scope/claims |
| 既存機能として維持 | Git structure/content/digest/manifest、source membership/name、PR文書/レビュー/thread、cache/lease/予約、派生検索入力/索引世代。新アプリ用のphysical contractを定義し、旧lease/予約/FTSを有効な状態として移さない |
| 名称の整理として採用 | 中央のchange_requestsとbinding-scoped番号空間。各関連tableはDDLで確定した名称を使う。GitLab等のAPI adapterやサービス意味の全面統一は実装しない |
| 任意・今回は採用せず | GitとPRのglobal byte-store統合、独立publication_claims/ref_capture_manifests、thread専用の全履歴projection。保存API occurrences・typed archiveから再解析できる証拠を残す |
| 後回し | 複数DB統合・双方向同期・change feed、全local integerのUUID化、各サービスMR/PR collector、新runtimeの起動/照会/収集への接続 |

論理案の全名称をそのまま表へ増やさず、origin_key/occurrence FK、completion/effective claim、typed legacy_records/legacy_valuesに集約するものもある。
Git contentsとPR text_bodiesは別。本文だけexact bytesで共有し、document_versions/observationsの既存IDと別々の観測を維持する。
同じdocumentで同bodyの複数旧versionがある場合もIDを維持できる。version→bodyの一意制約で不要なversion統合を強制しない。

## identity・公開・更新と削除

比較した方式:

| 方式 | 評価 |
|---|---|
| statement時のunpublish triggerだけ | deferred FKの間に親IDを往復して回避できるため不採用 |
| ON UPDATE RESTRICTだけ | 参照中の親key変更は即時拒否できるが、未参照factの来歴変更を防がない |
| 公開専用参照tableだけ | publicationをFKに含められるが、そのkey/factの変更規則も必要。今回は表を追加せず単調公開とidentity固定で保証 |
| **RESTRICT + immutable identity/fact + monotonic publication** | 採用。key/owner/contextは挿入時から不変。公開は0→1だけ。NULL pointerでbootstrapできる |

snapshotのacquisition_idは、同じrepoの別acquisitionへの付け替えも禁止。CR observationのCR/時刻/payload、body/version、listingのCR/collection/kind/scope/head/baseも不変。
一時的なid変更、SAVEPOINT内の更新、commit前の復元では回避できない。既存factを修正する代わりに新factと対応/再解析証拠を作る。
全FKにON UPDATE/DELETE RESTRICTを明示。全PKにidentity triggerを置き、取得/変換factはDELETEも禁止する。
conflict INSERT・UPSERT・REPLACEはPK/UNIQUE衝突をBEFORE INSERTで拒否する。REPLACEの暗黙DELETEはrecursive_triggers=OFFでも回避させない。冪等converterは既存map/hashを照合してから未作成rowだけINSERTする。
metadata/current pointer/progressはDDLで許した列だけ明示UPDATEする。新しい未公開factの構築順はNULL pointer→参照先作成→publish→pointer設定。transaction rollbackは許可する。
`proposal-core.sql`も同じidentity方針へ修正したが、完全DDLの代用にはしない。

暗号学的OID/digest照合、UUIDv4発行、dense ordinal、全page chain/cap/partial評価、scopeの主体/権限一致、公開前保存義務、effective coverageの証明はSQLだけでは確定できない。[invariant-contract.json](invariant-contract.json)の各I01〜I31にDDL・実在する試験node・残るP2〜P5 gateを対応付けた。
`context_proven`/terminal/complete等の値はadmissionが証拠を確認して設定する。SQLでflagを書けたことを完成証明とは呼ばない。
250 triggersとchild FK indexesの費用を隠さない。空targetはこの環境で271 pages×4096 bytes。データ入りの書込み/索引/容量費用は未測定でP2〜P4のsynthetic実測へ引き継ぐ。実DB規模の見積りではない。

## 機械検証する変換契約

正本は `conversion-contract.json`。CSV/Markdownは `scripts/schema_contract.py --generate` または `scripts/schema_design_catalog.py` で生成する。

- 全287旧列を列挙し、active outputのproduction/column/rule/依存/失敗分類/検証と、必ず存在するtyped archive位置を指定する。
- source row keyはSQLite storage typeを保持するTLV、各valueはINTEGER ASCII、REAL IEEE754 big-endian、TEXTのCAST AS BLOB exact bytes、BLOB exact bytes、NULL empty bytes+null tagで保持する。型とcolumn/keyを失わない。
- archiveは `legacy_records(source_id,source_table,source_key)` にrow hash、`legacy_values(record_id,column_name)` にstorage_type/value_bytes。未知・不正・未関連の値もここへ保持する。typed archiveはactive normalized dataの代わりに無条件で公開するものではない。
- one/many/merge/zero_until_runtimeとidentity/split/merge/derived/archiveを区別する。本文共有はbodyへのmany-to-oneであり、observation rowのdedupではない。
- actual targetを構築し、outputの実在/type、全必須列を含む逆方向provider、登録ruleのsignature、source/context入力、依存graph、archive location、旧列網羅を検証する。不正契約をnegative testで拒否する。
- scalar ruleは実行可能。contextual join/allocation/replayとtarget persistenceはrecipe/factory contractを確定した状態で、P2〜P4のconverter実装へ渡す。このツール自体はconverterではない。
- wall clockを使うparsed/evaluated/conversion時刻は別input。observed_atは保存値か証拠不在のNULL。replayしただけで観測時刻やwatermarkを前進させない。
- P4のproven evidenceが不足する出力はarchiveと診断を残す。P5のfresh runtime factoryは旧lease/予約をimportしない。old derived indexは原本から再構築する。

## CI修復と再現条件

空の専用UV_CACHE_DIR、git archiveしたHEAD、Python3.12/uv0.12.19で `uv sync --locked --group dev` → `uv build` →包装試験を再現した。
省略を外したstderrは **httpxがcacheに見つからない** と示した。index overrideは設定されていなかった。lockのregistryはhttps://pypi.org/simple。
locked syncはwheel URLからhttpxを取得・導入できるが、registry resolver metadataをoffline pip用に揃える保証はない。別venv・source外CWDでconstraintsによるregistry解決が失敗した。現在のvenvに導入済みであることはoffline新規導入の証拠にならない。

`scripts/prepare_wheelhouse.py` はonline準備専用。uv.lockから当該Python/platformで使えるwheelを選びSHA-256を検証、lock hash付きmanifestを出す。試験のbuild/sdist rebuild/installは **--offline --no-index --find-links** とlock export constraintsを使い、registry metadata/既存cacheへ依存しない。
空cacheからwheel/sdist-wheel両方を実行して成功した。packagingのskip/xfail/削除はない。network guardとGit file限定も維持した。失敗時stderrはpytest.failで省略せず表示する。
SQLite下限はonline準備でpysqlite3-binary==0.5.4を専用領域へ導入し、独立制約試験だけを3.46.1で実行する。通常アプリのSQLite依存は変更しない。

ローカル検証では標準gate 190 passed、SQLite 3.46.1 lane 103 passed、空cache包装2 passed、offline-recovery demo complete。検証コマンドは下記。最終HEADの再実行とCI結果はこのPRの最新checks/本文で確認する。

```bash
uv run --no-sync pytest tests/unit tests/integration tests/e2e tests/packaging --strict-markers -m "not live and not benchmark"
uv run --no-sync python scripts/run_sqlite_minimum_tests.py
uv run --no-sync python scripts/demo.py --work-dir artifacts/p1/demo-final --scenario offline-recovery
```

前工程の88件ローカル成功、レビュー時のCI失敗、本工程の最新検証を混同しない。

## converter工程へ渡すもの

P2はsealed source識別/source/cache write deny/network deny、typed row/key serializer、ledger・ID map・atomic batch/resume、容量preflightを実装する。
P3はcontractのactive providerを具体化し、全旧row/column exact archive、ID/edge/time/byte比較を通す。missing/invalidはblocking/partialのdecision manifestへ残す。
P4は全保存pageと残存local Gitからstable listings/root origins/resume/effective claimsを再解析し、同一OID複数ref・途中再開・watermark非前進をdesired invariantで検証する。P5でcollector/runtimeを新formatへ接続する。

未実装: converter・履歴再解析engine・暗号学的/effective完成監査・新runtime/query/collector、実DB変換・運用切替。旧v2の3 characterization testsは引き続き不具合再現であり、collector修正の成功を主張しない。過去pilot readonly診断を本工程の移行成功と扱わない。
