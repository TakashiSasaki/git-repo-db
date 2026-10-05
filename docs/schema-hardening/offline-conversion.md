# v2からのオフライン変換・検証・切替仕様

これは実装仕様案。converter、実DB変換、切替はこの区切りで実行しない。
旧CLI互換・旧schemaへの書込み互換は不要。source DBと必要なcacheは保存し、targetは別の新規DBとする。

## 1. 安全境界とsource識別

1. application、scheduler、Git子processを停止し、writer/cache lockが解放されたことを確認する。停止だけで未完了jobをcompleteにしない。
2. sealed source DBを用意する。未checkpoint WAL/rollback journalがあるsourceはそのまま受理しない。ユーザー管理下でSQLite backup等の整合copyを取得する方法と、旧ファイル一式の保全を先に確定する。converterはsourceへcheckpoint/VACUUM/migrate/backup manifest上書きを行わない。
3. sourceはread-only open/query-only transaction、cacheはread-only mountまたは同等の書込み禁止経路で扱う。source内にログ/一時file/checkpointを作らない。
4. source識別にはcatalog_meta、schema_migrations、**実際のsqlite_schema/PRAGMA制約**、DB file SHA-256、source db_instance_id、release SHA、SQLite runtime、configの非秘密参照を記録する。v2と申告されても実DDLが違えば診断する。
5. 未知のextra table/column/trigger/shadow objectは列挙し、typed archiveまたはsealed source packageに収容して未対応を記録する。schema nameを動的DDLとして実行しない。
6. targetは新path、new db_instance_id、明示format_id/version/DDL hash、building状態で作る。sourceのschema_migrationsをtargetの適用済みDDL ledgerへcopyしない。source ledgerはconversion_sourcesに記録する。

setup用のgit clone/fetch、uv dependency取得はこの境界の前に行える。
**conversion/reparse/index build/validationのprocessはGitHub APIもnetwork git fetchも呼ばない**。旧collector、content hydrate、pressure GC、通常sync/restoreを変換手段に使わない。

Git原本読取りには既知cacheの`cat-file`等のread-only operationだけを許可する。
`GIT_NO_LAZY_FETCH=1`、protocol allow deny-all、replace refs無効、optional locks無効、system/global config無効化を設定する。
promisor/shallow/alternatesを調査し、alternatesは明示許可したread-only local rootsだけを辿る。missing objectが自動fetchを起動する経路を禁止する。
source work/logsも手掛かりとして一覧化するが、未知spoolを完成した取得事実と扱わない。

## 2. 変換manifest・IDと再開

conversion_sources: source fingerprint/format、schema/ledger hash、input DB byte size、必要cache/object-list fingerprint、認証値を除いたscope参照。
conversion_runs: target format/DDL/parser/preservation profile version、開始・終了・検証時刻、source immutable証明、状態building/paused/validated/rejected。
conversion_batches: table/rangeまたはsource page集合、input canonical hash、target transaction commit marker、row/edge対応、未解決診断。
id_mappings: `(source fingerprint, source table, tagged old key, target entity, tagged new key, reason, conversion run)`。one-to-manyやmany-to-oneも複数rowで表現する。

local IDを維持するtableは明示identity mapまたは検証済みidentity ruleを記録する。
binding UUIDやpage occurrence IDの新規発行はsource composite keyとのmapを永続化し、再開時に同じmapを使う。
raw keyのtagged表現はINTEGER/TEXT/BLOB/NULLを区別し、BLOBはbyte length+base64で保存する。JSON文字列化だけでkey typeを失わない。
target用の新integer領域は既存IDsの最大値と衝突しないよう予約する。repoやobjectを勝手に再採番しない。

source rowごとのcanonical serializationはcolumn順・SQLite storage type・byte length・exact bytesを含める。
JSONが同義でもraw文字列/byteが変わるtransformは旧raw値を保持し、semantic decode結果と別hashを記録する。
batchのデータ、ID map、manifest進捗は同一target transactionでcommitする。source cursor位置だけを先に進めない。
再開はsource fingerprint・target DDL/parser version一致時だけ、最後のcommit batchから行う。中断したtargetのみrollback/cleanupできる。

## 3. 保全と再解析の順序

1. source identity/schema/unknown structuresを封印し、constraint violationsと欠落をdiagnosticにする。
2. repo/instance/source/endpoint/bindingを変換する。旧互換列との矛盾・PR binding不明・preferred pointer欠落を列挙する。
3. payloadsを全件byte-preservingで移す。未参照body、GraphQL error/partial、pending-comment、旧ETagにしか参照されないbodyも対象にする。
4. Git object/structure/content/digest、取得run/ref/root/snapshot/source edgesを移す。進捗・lease/予約と取得事実を分離する。
5. saved API pages、request/cursor/主体scope、PR/document/version/observation/eventを移す。本文を共有しても観測rowは維持する。
6. listing、thread history、未関連payloadを保存page/legacy snapshotからofflineで再解析する。converter自身がHTTP clientを生成しない。
7. completion、watermark、validator、page/GraphQL cursorを型付き再開情報へ変換する。判定不能なraw checkpointも保存する。
8. current pointersと公開claimsを設定する。source claimとeffective validationを分離し、矛盾があればpartial/unknownを維持・診断する。
9. manifest/path/searchをfinal durable inputsからtarget上で再生成する。FTSは任意で、scan queryの正しさを先に検証する。
10. 全verification gateを通しtargetをvalidatedにする。validated前に新applicationを稼働させない。

## 4. 原本・観測保全の証拠（件数以外）

| 対象 | 必須比較・証明 | 証明できない場合 |
|---|---|---|
| 全旧row/column | tagged old key → output row/column/archiveの対応。per-row exact hash、multiset digest、未対応件数、NULL/storage type、ID maps | 変換先またはarchive不明ならgate失敗 |
| PK/FK/ownership/current | source→target edge tuples、repo/CR/document所属、pointer先のID/body/publication、parent DELETE/UPDATE試験 | 不正pointerを最新rowへ黙って差替えない |
| API payload | 全id/raw byte length/SHA/exact bytes。orphanも包含、source payloadを再serializeしない | 不正JSON/unknown shapeはopaqueとして保持。hash不一致は診断 |
| page/scan | collection identity、page sequence/request/query/variables/next cursor、payload ID、original time、known context、cap/partial理由 | overwritten pageの過去request/時刻はunknown、全履歴復元とは呼ばない |
| 本文/文書 | old version ID → exact UTF-8 body、global body map、document owner、全observation ID/time/order/version対応、A-B-A fixture | exact body一致なしのhash共有禁止。観測rowのdedup禁止 |
| PR code listing | 全保存page arrayのresource/page-position/oid/path/patch multiset、code observation↔listing context、head/base consistency、provider limit | 途中再開の分断はoffline repair候補。証拠不一致なら部分listingのまま |
| Git | format/OID/type/size/parent order/tree raw names/modes/targets/tag raw、repo acquisition source edges、profile対象raw bytesとdigest | raw不在ならlegacy verified assertionとして保全し、新たにrehash済みとしない |
| ref/root/path | 各raw ref→OID/peeled/role/origin、共有seed→全origins、root manifest path/mode/format/OID tuples、history reachability | lost captureはcache派生証拠と元観測を区別、subsetをfullにしない |
| completion/resume | scope・主体・binding・API/parser/profile、saved range/chain/cap、不確実性、validator body、safe watermark境界 | 部分scopeのみfast path停止。取得済みbodyを捨てて全PR再取得にしない |
| 照会 | catalog/repo/ref/tree/commit/path/hash/code/PR/version/thread/timeline、scopeとcoverage、paging全体、raw offsets、current/history/recordedの結果内容 | 意図した差（不具合是正、namespace分離）はsource rowsと診断根拠を伴うexpected difference manifestに記録 |
| 物理原本 | source DB/cache/work fingerprint前後一致、target SQLite integrity/FK、object availability、必要rawの独立保全 | source変更なら検証失敗。sourceがliveだった結果を承認しない |

SQLite integrity_check、FK check、table count、aggregate hashだけでも不十分。変換が同じ数だけ誤った関係を作る場合を反例fixtureで試験する。
derived indexesの違いをdata lossとして扱わず、入力原文/coverage一致を検証する。必要なhistorical rawが元から存在しない場合、scopeごとに欠落を報告する。

## 5. saved payloadの扱い

- `api_responses.body`: response.contentのdecoded bytes。gzip前wire body・headers・HTTP statusを全件保存したという前提にしない。
- `collection_pages`: REST array、GraphQL response、partial/errorとvariablesを分類し、pageの元時刻/ordinal/cursorを使う。
- `sync_checkpoints.pending-comment`: repo/number/kind/provider identity/payload/collectionを保持。関連PRが存在しないpayloadもunresolved_payloadsへ移す。
- `sync_checkpoints.etag`: validator scopeとresponse_idを照合。存在しないresponse、scope解釈不能はvalidator無効だがraw evidenceを保持。
- `pr_observations`、documents/review/thread metadata/event/code payload: normalized snapshotとして再利用可能。raw APIとのexact request関係が不明ならその不明を保持。
- unreferenced API body: parseできればcandidate resourcesとして回収し、確証なくrepo/PR/request/観測時刻へ結び付けない。
- raw Git: source cacheのobjectとintake refsをread-onlyで調査。既存DBのGit DAGから不足構造を補える場合もraw OID検証を行う。

意図不明なtable/column/valueはtyped legacy recordで保全する。既にtargetへexact bytesで保全された大bodyはそのbody ID+hashを参照し、archiveに二重複製しない。
archiveがsource DB参照だけになりtarget単独で失われる設計は避ける。unknown rawはtargetまたは同梱sealed archiveに収容し、件数/byte/keysのmanifestを持つ。

## 6. 最初の同期を全件再取得にしない

**移行はnetwork禁止、切替後の通常syncは別工程**。初syncは変更確認に必要な通信を行えるが、移行のために全PR本文・コメント・reviewを取り直さない。

| 情報 | reuse条件 | 無効/不明時の扱い |
|---|---|---|
| completed PR marker | binding/CR、元scope/主体/権限参照、API/parser/profile、各saved collection/listing/Git証拠を照合。旧job IDだけのmarkerはtyped proofへ昇格できたもののみ | 意味不明markerはarchive、該当子resourceのみneeds_refresh。旧completeコードの判定をそのまま移植しない |
| partial REST collection | 同一stable collection/context、保存page、last committed cursorが一致。既存pagesはofflineに再解析済み | 古い/失効cursorはそのlistingの再評価対象。新obsにpage2だけ入れない。旧pagesは消さない |
| GraphQL root/child cursor | binding/CR、query+variables、page size/API/parser、parent thread identity、saved error flagsと同じscan | cursorのopaque文字列だけで再開しない。error/partialのunknownを残す |
| ETag/validator | original URL/query/accept/API version/主体/sourceとbody exact integrityが同じ。safe redirectで同じnative identityを確認 | 304だけでbodyが無ければ不成立。別accountのETagを流用せず、そのresourceのみrefresh |
| watermark | 同じtyped scope、成功したbounded scanの実start境界と最終pageが証明できる。再利用/reparseでは前進させない | old updated_atをscan時刻にしない。保存scanの保守的な下限へrewind可能な場合のみ採用し、overlapを付ける。不明なら該当incremental endpointをneeds_refresh |
| Git current snapshot | 保存済み公開roots/structure/digests/profile obligationsを照合。改訂されたparserでローカル再解析のみ必要ならnetworkを使わない | 元raw不在を全API再取得の理由にしない。次の通常Git syncで不足する対象rootのみを明示する |

旧key dialect（source無しwatermark、source付きv2 colon key、JSON ETag scope、pr-complete、graphql-root/child、pending-comment）を全部識別する。
keyから復元したscopeは元request/collection/bindingと照合し、colon分割や最新repo名だけで決めない。
watermarkより後に更新された未観測コメントを飛ばさないことをfixture clockで検証する。元scan startが保存されていない場合に「絶対に再取得がゼロ」を約束しない。
scopeを証明できないケースは診断と計画された限定refreshにし、通常の変換経路にはnetwork accessを追加しない。

初sync試験はfixture API request logで検証する：完了済みclosed PRの全コメント/review/listingを再列挙しない、partialのみ続き、validatorの304に保存bodyを使用、watermarkの未観測区間を飛ばさない、別account/instanceは旧fast pathを使わない。
open PRの変更確認、未知scopeの個別refresh、失効cursorの対象listing再取得は必要性を明示する。新API adapterが未実装のserviceはunsupportedのまま。

## 7. 自動変換できない／制限されるケース

| code案 | 問題 | 方針 |
|---|---|---|
| SOURCE_UNSEALED / SOURCE_CHANGED | WAL/journal/live writers、file/cache fingerprint変化 | 停止・sealed copyを要求、sourceには修復しない |
| UNKNOWN_FORMAT / DDL_DRIFT | version/checksumと実schema不一致、extra table/column | 実構造と全typed dataを保全し専用mappingが必要 |
| IDENTITY_AMBIGUOUS | PR binding/native ID/namespace、repo duplicate/conflict | 候補と旧値を非公開診断に保存。URLやnumberだけで統合しない |
| CROSS_OWNER_POINTER / DANGLING_EDGE | current/parentが欠落または別所属 | 原主張を保全しsemantic activationを止める。許可なしに最新へ差替えない |
| INVALID_TYPED_VALUE | bad OID/digest/boolean/attempt/state/JSON/shape/time | raw valueをarchive、0/false/{}へ黙って補正しない |
| RAW_HASH_MISMATCH / RAW_UNAVAILABLE | body不整合、binary/cache原本消失、非canonical tree原本不在 | original hash claimとraw byteを分ける。新verifiedとしない。scope別に不足を記録 |
| LISTING_CONTEXT_CONFLICT | partial pagesのhead/base/API scope不一致、cap/不連続、missing page | 全pageを保持、partial/unknown。完成した一覧を捏造しない |
| ORIGIN_UNKNOWN / OVERWRITTEN_HISTORY | polymorphic旧run、orphan body、同request上書き、同collection observation collapse | origin不明のdataは保持、時刻/主体/順序を推定確定しない |
| RESUME_SCOPE_UNKNOWN / WATERMARK_UNPROVEN | opaque checkpoint/期限/権限変更、scan開始境界不明 | raw保存、該当fast path無効、通常移行を全件API取得に切替えない |
| SPACE_BUDGET / ARCHIVE_INCOMPLETE | target/archives/index/cache copyの容量不足、未対応raw未収容 | targetをpaused、source不変。容量確保または代案をレビューする |

blocking conditionと、legacy-asserted/partialとして読取り可能な残余を区別する。未解決scopeの公開可否はexplicit decision manifestに記録し、converterが勝手にcompleteにしない。
公開レポートはcode/aggregateとfixtureだけ。実repo/PR/doc/URL/ID/本文/認証値は非公開artifactのみに置き、repositoryへcommitしない。

## 8. 容量・切替・rollback

F_nowをsource/既存backupを既に差引いた空き容量とする。
必要追加空き = target DB worst-case + target journal/WAL peak + index二世代 + archive/spool + 必要cache独立copy + 新規backup分 + headroom。
source DB sizeをさらにF_nowから二重に差し引かない。既存10GB minimum free方針はheadroomとして別に保つ。
raw payload、typed archive、scoped indexesの重複/圧縮率を見積もりに入れ、count比例だけでtarget sizeを断定しない。

| 方式 | メリット | 費用・制約 | 判断 |
|---|---|---|---|
| 別新規DB・同volume | source不変、byte/edge比較とrollbackが明確 | target/journal/index/archiveの追加空き | 第一候補 |
| 別volume | source側空きが少なくても可能 | 安定接続/permissions/切替pointer、copy量 | 容量不足時の第一代案 |
| reflink snapshot/copy | COWで独立copy、初期費用を抑え得る | FS依存、変換/索引書込みで増えるためworst-case予約が必要 | cacheの独立copy・保全用途。DB変換をchecksum編集で済ませない |
| 段階的destination build | 小batch/spoolとpause/resume | 最終DBの追加空き自体は減らない | 第一候補と併用 |
| 元DB in-place rebuild | 必要空きが減る可能性 | rollback複雑、source不変要件に反する。journal/backupで結局空きが必要 | 今回の第一案として採用しない。source原本が別封印copyならcopy上の方式を別途比較 |

mutable targetとsource DB/cacheのhardlinkは不可。source cacheを新runtimeのactive cacheにしない。
source cacheからreflink/copyして独立書込み領域を作るか、旧cacheをread-only locatorとして残し、初syncのnew active cacheは別にadmissionする。

切替前gate: source前後一致、target integrity/FK/invariant、full column/edge/byte maps、offline raw/index/query検証、残余診断decision、初sync request plan、容量余裕。
新applicationはtarget formatを検査してから起動する。target state内にvalidated manifestを封印する。
切替はsource pathをrename/上書きせず、外部のactive-catalog設定/参照pointerを新targetへatomicに変更する方式を第一候補とする。
失敗時は外部pointerをsealed sourceまたは最後の承認targetへ戻す。旧applicationが必要なら保全した旧環境でのみ起動し、format互換とは扱わない。
source DB/cache/manifestを自動削除しない。切替後のcleanup/merge/publishは別に承認・計画する作業である。
