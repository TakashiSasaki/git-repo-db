# P1仕上げ: 完了一覧と単調補完

対象branchは `design/schema-v2-hardening`、レビューHEADは `62692a85b110e025d781523037ff88f2a1dee3fe`、mainは `9a4110185d7e7abffc291f9cfd118ca71587f998`。
開始時のremote/PR HEADはレビューHEADと一致。最新PR CI run **37337326501** とpush run **37337320713** は成功しており、指摘後の重複修正はなかった。
未改修 `target-schema.sql` のblobは **977a0caa152a4c2046f529bdfdfa50c502abaa52**、SHA-256は `f5e6fdfe1a0c22e9f7b6f4618d6b93fbd02ee44ac96cb90f49e98fbf3ae67b7d`。
本工程は全74表の独立DDLを使うsynthetic試験のみ。通常runtime、実DB、旧cache、collector、移行runnerは変更・変換・切替していない。

## 完全DDLでの再現

`scripts/probe_listing_seal.py` は指定SQLからmemory DBを構築し、74表であることを確認して同repo/CR/scope/head/baseのcommits/files一覧を用意する。
両progressをcompleteにし、completeなcode observationの参照あり/なしを別々に試す。
BEGIN内でcomplete markerをDELETE、同keyのpartial markerをINSERT、正しいcollectionのoccurrenceと未使用positionで項目を追記してCOMMITする。

| 入力 | SQLite | commits / files、参照あり / なしの結果 |
|---|---|---|
| 上記の未改修完全DDL | 3.46.1、3.53.1 | 全経路がCOMMIT成功。progress=partial、参照ありではcode observation=completeのまま。FK違反0、integrity=ok |
| 修正後完全DDL | 3.46.1、開発環境SQLite | DELETEで拒否。rollback後もprogress=complete、観測も維持。FK違反0、integrity=ok |

診断はfixture値だけを出力し、実DBやcacheを読む引数を持たない。再現用SQLはGit blobから取り出せる。

```bash
mkdir -p artifacts/p1-finish
git show 62692a85b110e025d781523037ff88f2a1dee3fe:docs/schema-hardening/target-schema.sql > artifacts/p1-finish/review-target.sql
uv run --no-sync python scripts/probe_listing_seal.py --sqlite-minimum --schema artifacts/p1-finish/review-target.sql
uv run --no-sync python scripts/probe_listing_seal.py --sqlite-minimum
```

## 一覧の固定と構築順

completeは、観測から参照されているかに関係なく、そのlistingの集合を永続的に固定する。
`listing_complete_retain` がcomplete markerのDELETEを拒否する。既存のidentity/no_replace/no_downgrade triggerと併せ、ID変更、降格、DELETE→再作成、REPLACE、UPSERTで再び開けない。
code_commits/code_file_changesのINSERT/UPDATEには **存在するpartial progress** を必須にする。進捗行がない場合とunknownの場合も追記を拒否する。

正当な順序は、listing/context作成 → partial marker初期化 → page/item保存 → 原本・terminal/context/capのadmission → completeへのUPDATE → complete code observation作成。
partial markerの削除は許可するが、項目factは削除・上書きしない。再開時は既存項目を照合してpartial markerを再初期化できる。unknown→partialにはアプリのscope確認が必要。
誤ったcompleteを訂正する場合は別のlisting/collectionと診断を作り、完了済み集合を書き換えない。
未COMMITの完了・項目はtransaction/SAVEPOINTのrollbackで元に戻せる。rollbackを完了後のDELETEと同一視しない。

変換契約の `code_listing_progress.staged_write` は初期値、項目production、最後にUPDATEする列を構造化している。
code_commits/code_file_changesはprogress productionに依存する。機械検証は初期partial、列/type、依存の実在を確認する。**この順序を実行するconverter persistenceは未実装**。

## 情報補完の採用方式

| 対象 | 採用する意味と更新 | 比較した代案・採用理由 |
|---|---|---|
| contents | identity/byte_length/text_state/created_atは固定。eligibleのraw_text=NULL→既知だけ許可。既知本文の別bytesへの変更、NULLへの消去は禁止 | 追記型の本文結果tableや固定claim+別projectionも可能だが、本文bytesの履歴は不要。write-once補完で既存のcontent/map/location参照を保ち、表を増やさない |
| source_repositories | pairを保持する「発見されたことのある関係」。first_seen/last_seenは既知時刻のmin/max集約。NULL→既知、より早いfirst、より遅いlastを許可。時刻消去・内側への縮小は禁止 | pair行を個々の観測として固定すると再発見を表せない。別のpair-event表は今回は追加せず、個々のinventory/page/payload事実と集約を区別する。現在の所属・全発見履歴をこのpair行だけから復元しない |
| git_objects | format/OID/type/size/IDは固定。verifiedはadmissionされたOID/size結果の単調projectionで0→1を許可、1→0は禁止 | 各検証attemptの専用証拠tableや歴史的bit固定+別結果も可能だが、今回必要な状態は既存bitとarchive/再解析・診断ledgerで表現できる。詳細な実行証跡の永続化はP3/P4 |

sourceの新時刻は供給されたtimezone-aware RFC3339の観測時刻（最大microsecond精度）から得る。移行時刻で埋めない。同じinstantのreplayで元の文字列表現も更新しない。より細かい精度や不正日付は丸めず拒否する。
DDLはjuliandayで不正時刻/粗い逆行を拒否するが、timezone必須やmicrosecond単位の厳密な順序はSQLの保証ではない。
admissionはdatetimeで厳密にmin/maxを比較する。sub-millisecondと同時刻の別表記の試験を含む。旧値の不正・矛盾はarchive/診断し、黙って正規化しない。

## 本文・Git原文の検証入口と照会

実行例は `tests/support/p1_admission.py`。通常applicationへ接続せず、呼出し側が渡したローカルbytesだけを扱う。ファイル読取り/hashはwriter transactionより前、単一writerを前提とする。`prepare_text_completion` / `prepare_git_verification` が検証済み入力を捕捉したSQL-only保存callbackを返す。複数補完のrollback試験はprepare→BEGIN→保存callback→COMMIT/ROLLBACKで実行し、writer transaction内の新たなhash計算を拒否する。

- `hydrate_text`: 保存byte_length、strict UTF-8、NULなし、eligibleを確認。raw-content-v1 SHA-256 anchorを必須とし、保存済みの全MD5/SHA-1/SHA-256と供給bytesを再計算照合してからUPDATEする。SQL自体はanchorの存在・長さ・NUL・write-onceの形を保証し、digest一致を計算しない。
- 補完と `content_locations(kind='durable-content',locator='contents:<id>',state='available')` の保存は同じsavepoint。既存blob_content_mapはcontent IDを維持する。通常SELECTがmap→contents→durable locationを辿り、CAST AS BLOBで元bytesを返すこと、そこからsearch_documentsへ本文を保存・照会できることを試験する。cache locatorだけを利用可能なDB本文と誤認しない。
- `verify_git_object`: typeと長さを含むGit header `type size\0` とraw bytesのhashをobject formatで計算し、OID/size一致後にverifiedを0→1にする。SHA-1/SHA-256、同長別bytes、長さ違い、type違いを試験する。tree/commit構文・closureや将来の原文availabilityの証明とは別。

この入口を通さない直接SQLは、同長の誤本文や虚偽のverified=1まで暗号学的に拒否できない。P3/P4 import・再解析とP5 runtimeの全書込み入口へ同じadmissionを実装する必要がある。
旧verified bitはlegacy_valuesにexact保存し、新target verifiedを無条件copyしない。契約のtyped P3 providerはoffline原文検証前は0、不足はpartial診断、検証済み結果だけ1を供給する。旧bitを新rehash証拠と呼ばない。
保存本文を共有しても、document versionや個々の観測を削除しない。

## 正当系・拒否系の実行範囲

`test_p1_storage_lifecycle.py` は実際の完全DDLへSQLを書き、次を確認する。

- commits/files、参照あり/なし、autocommit・BEGIN/COMMIT・SAVEPOINT、recursive_triggers ON/OFFのREPLACEで再オープンを拒否。statement ABORT後に外側transactionをCOMMITしてもsealが残る。
- 未初期化/unknownの追記を拒否し、partial初期化後の正当な追記を許可。
- 同じsource/repoの再発見、遅れて届く古い観測、同時刻replay、NULL時刻の補完。個別inventory observationsの時刻・行を維持。
- 本文未保存→tmpのローカル原文検証→本文とdurable location保存→mapを辿る照会→検索入力の保存と読取り。既知本文の上書き・消去、長さ/digest/UTF-8/NUL/anchor不足を拒否。
- Git未検証claim→原文OID/size検証→verified=1→同原文の再検証。identity変更・降格を拒否。
- 2種listingのpage 1をCOMMIT、page 2とcompleteをSAVEPOINTで保存してrollback、同じ入力/IDで再開してcomplete。保存済みpageのbytes・ordinal・観測/解析時刻を比較し、partial観測とcomplete結果を別行で保持。集合の追記・marker削除を拒否。
- 本文/Git/sourceの補完をBEGIN内で保存してROLLBACK、元claim/時刻/NULLへ戻ること、再開後のCOMMITで補完できること。

旗の値だけでpage連鎖やscope証拠まで完成したと主張しない。I09/I13/I14/I15/I17/I20/I21/I28/I29/I31のSQL、試験、残るgateはinvariant-contractへ対応付けた。
DDLは74表/426列/159索引を維持し、triggerは251（追加1）。空DBの272 pages×4096 bytesはこの開発環境の測定であり、実データ容量/性能の推定ではない。

## 最終gateとP2引き継ぎ

最終HEADで以下とCIのpackaging・後段demoを確認する。過去HEADの190/103件成功を新HEADの結果として扱わない。最終SHA・件数・CI runはPRの最新checks/本文と成果報告を正本にする。

```bash
uv run --no-sync python scripts/schema_contract.py --generate
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync pytest tests/unit tests/integration tests/e2e tests/packaging --strict-markers -m "not live and not benchmark"
uv run --no-sync python scripts/run_sqlite_minimum_tests.py
uv run --no-sync python scripts/demo.py --work-dir artifacts/p1-finish/demo-final --scenario offline-recovery
```

未実装はconverter recipe実行、lookup/allocation/ID map persistence、履歴再解析engine、productionの暗号学的証跡・page完成監査、新runtime/query/collector/FTSへの接続。
P2着手条件はこのDDL/契約/両側の試験の承認可能な状態と最終CI成功。次はsealed input、network/source/cache write deny、typed archive、ID map、atomic batch/resume、fault injectionをsynthetic fixtureで実装する。
P1のsavepoint実例をP2の耐障害converter完成と扱わない。実DB変換・旧cache変更・切替はP2着手に含めず、後続dry-run/cutover工程へ残す。
