# 新スキーマ案と変更理由

**設計案。完全なproduction DDLやconverterは未実装。** `proposal-core.sql`はownership/pointer/root/listingの方式を検証する独立DDL断片で、applicationのmigration資源には入れない。
target formatの仮称は`repo-catalog/catalog3-draft`、schema version仮称3。未確定DDLをrelease済みformatとして宣言しない。

## 1. 全体の区分と正本

| 区分 | target logical tables / 新しい役割 |
|---|---|
| format・変換 | database_identity、conversion_sources、conversion_runs、conversion_batches、id_mappings、validation_results、legacy_records |
| repo・service | repositories、service_instances、repository_bindings、repository_endpoints、sources、source_repositories、repository_name_assertions、inventory_observations |
| Git取得事実 | git_acquisitions、ref_capture_manifests、snapshots、ref_observations、acquisition_roots、root_origins、repository_object_sources、publication_claims |
| Git構造・原文 | git_objects、commits、commit_parents、tree_entries、tag_objects、contents、content_digests、blob_content_map、content_locations、root_manifests/entries |
| API取得事実 | payloads、fetch_collections、fetch_occurrences、collection_memberships、observation_origins、resource_payloads、unresolved_payloads |
| PR/MR・文書 | change_requests、change_request_observations、documents、document_versions、text_bodies、document_observations、reviews、review_threads、thread_observations、review_comments、change_request_events |
| コード観測 | code_observations、code_listings、code_commits、code_file_changes、code_acquisitions、legacy_listing_items、reanalysis_runs |
| 完了・差分取得 | completion_markers、validators、incremental_scans、resume_cursors、legacy_checkpoints、coverage_scopes、coverage_claims/current |
| 実行・cache | jobs、job_attempts、acquisition_progress、collection_progress、cache_locators、active_cache_entries、cache_leases、space_reservations、legacy_runtime_records |
| 派生索引 | search_documents、index_generations、index_membership、legacy_derived_records |

既存53 tablesの287 columnsはcolumn-conversion.csvで全列対応を与える。表の新規分割はこの区分を実装するための論理モデルであり、名前/物理統合は全DDL作成時に確定する。
既存columnで変更を指定していない属性（metadata、raw payload、timestamp、reason等）もtarget本体またはtyped legacy envelopeへ保持する。DDL断片で省略した属性を捨てる意味ではない。

## 2. repo、binding、取得先

repositoriesはUUID、display name、metadata、preferred endpoint pointer、current snapshot pointerを持つ。
source_id/provider_host/provider_repo_id/url互換projectionは削除し、旧値をlegacy_recordsに保存する。
sourceとrepoはsource_repositories、native identityはbinding、接続URLはendpointを正本とする。
source.kindはdiscovery_kind（manual_git/github_inventory）へ整理し、provider kindはinstanceに置く。
Git URL・hostname・port・mount aliasはRepo IDではない。同じOIDを含むfork/mirrorも自動統合しない。

bindingにはUUIDを追加する。旧(repo_id,instance_id)からの対応を必ず記録する。
repo/instanceごとに1 binding、instance/native_idの一意性を維持する。native_id NULLはAPI識別がないことを表し、全NULL同士を統合しない。
PR/MRの番号空間は`UNIQUE(binding_id,request_kind,number)`。同じRepo IDを別serviceへ明示登録してもPR番号が衝突しない。
旧PRはGitHub bindingへ結び付ける。複数候補・native情報の矛盾は自動選択しない。

preferredはendpointのbooleanからrepoのscoped pointerへ移す。preferredが存在すれば必ず同repoで、最大1件になる。
repo構築中のNULLを許す。公開catalogの少なくとも1 endpoint/1 preferredはadmission auditで検査する（未確定repoを通常収集対象にしない）。
runのendpoint URLは当時のsnapshotとして残す。URL変更は過去のrunへ伝播させない。v1由来のNULLを移行時のpreferred URLで埋めない。

distinct-name集合はrepository_name_assertionsとして保持し、全rename event historyとは呼ばない。
provider full_nameはbinding内の観測属性に分ける。source_repositoriesの時刻は旧backfill/maintenanceの意味を保ち、API初回発見時刻へ改名しない。

## 3. shared root seedとref/role観測

acquisition_rootsはwalkのseed：`UNIQUE(acquisition_id,object_format,oid,role)`。
同じseedを指すraw refやPR role出現はroot_originsに分ける。
ref_observationsのraw ref、OID、peeled OID、target typeは全て保持し、rootへリンクする。2 refs→1 objectは1 seed+2 originsである。
converterはroot/manifest/refの旧IDと内容を照合し、派生originに元row/page/refの由来を記録する。
failed captureでDB refsが全rollbackした場合、cache intake refから再解析できても失われた観測時刻/期待OIDを復元したとは扱わない。

Git object/commit/tree/blob/tag保存は維持し、形式・型・長さ・parent order・OID実証を強化する。
raw treeがない場合、tree_entriesのmode整数と名前の集合だけで元のmode字句/entry順を必ず再構成できるとは限らない。canonical再構成がOIDに一致した場合だけ原本実証とする。
commitsのraw_headers/raw_message、tagのraw_payload、保存raw_text、残存Git objectはbyteで検証する。digestのみのbinary原文は作らない。

## 4. observationとbody、旧current state

document_versionsのlocal IDは維持し、本文実体はtext_bodiesへ切り出す。
bodyはUTF-8 byte length+SHA-256を候補に、exact bytesで共有する。versionはdocumentに属するまま、observationは別rowを維持する。
同bodyで別観測、A→B→A、別API requestで同payloadはそれぞれ別事実である。
Git contentsとの全面統合は必須にしない。Gitのbinary/profile/raw digestと、JSONから抽出したPR Unicode本文の表現・由来を保つ。共通byte-storeへ統合するかは未確定。

観測rowはobserved_at（旧claimを含む）、parsed_at、conversion run、origin confidenceを分ける。
saved API response、page、single-resource validator、jobキー、GraphQL request由来を型付きoriginにする。
`resource_observations.collection_run`とevent.run_idの任意文字列をrun FKへcastしない。不明なキーはraw legacy keyとして残す。
現在のdocument/review/threadが上書きされ、完全履歴は保存されていない場合、旧current stateをlegacy state assertionとして保持する。
保存GraphQL pageから過去thread observationを再解析できる場合も、そのpageの取得時刻を使い、移行時刻を観測時刻にしない。
失われた上書き履歴はunknown。orphan payloadから似た本文を見つけただけでrequest/時刻/主体を推測確定しない。

## 5. 安定listingと途中再開

code_listingsはCR・scope・対象head/base・collectionに属し、一覧IDはjob再開で変わらない。
code_observationsはそのlistingを参照する。commit/file rowsはlisting/page/positionをkeyにし、pageを保存し終えた範囲と欠落を明示する。
新規page保存時はraw payload occurrence、item位置、resume cursorを同一transactionで確定する。
再開は同じlistingへ続き、新しいcode observationへpage 2だけを格納しない。
completeには全保存pageの連続性、last cursor、同一scope・head/base、reported/cap/graph/API不確実性の評価を要求する。
parent一致FKだけではkind（commit/file）・完成条件を証明できない。kindはtrigger/admission、完成はscope監査で保証する。

旧行は全保存pagesから再解析する。旧code observationのID/主張を保持し、派生修復をreanalysis_runsで追跡する。
old partial collectionのpage 1/2が同じcontextだった証拠が不足すれば、新listingはpartial/unknown。旧completeを盲信せず、再解析しただけでcompleteにしない。
v2 ordinalはpage*10000+positionであり疎。raw arrayがある場合にpage/positionへ変換する。原文がない場合、元ordinalと順序の不確実性を保持する。

## 6. API取得・payload・進捗

payloadsは元decoded body BLOBとSHAを保持し、integer IDを維持する。未参照・未関連付け・不正JSON・未対応GraphQL応答も削除しない。
fetch_occurrencesはpayload identityと別で、request/variables、page、cursor chain、time、主体/権限scope、API version、parser provenanceを保持する。
v2のページ保存は同requestのINSERT OR REPLACEで上書きされ得る。残存payloadを保全できても旧request全履歴を復元できるとは限らない。
normalized payloadしかない場合は「API原文」ではなくlegacy normalized payloadとして保存する。
not-stored response headers/status/auth identityはNULL/unknown。requestに新しい主体を与えて古い取得事実を偽装しない。

fetch_collections/git_acquisitionsは取得のidentity・scope・観測事実、*_progress/jobs/job_attemptsは再開可能な処理状態に分離する。
旧attemptは最新保存値のみをlegacy-last-knownとして移す。1..attemptの架空履歴を作らない。
coverageはscopeとclaimsを分け、元asserted state・検証済みpostcondition・effective stateを併記する。
ownerはrepo/acquisition/CR/collectionなどのexplicit FK field + exactly-one-owner CHECK（またはtyped per-owner table）にする。任意文字列のまま正本にしない。

## 7. index・DELETE・exchange

追加するscoped UNIQUE/FK keys、boolean/numeric/JSON CHECK、publication/type triggersはinvariants.mdに対応する。
必要index候補:

- scoped FKのchild側owner/id、current pointer参照列：parent DELETE/UPDATE保護の全scanを避ける。
- bindings(instance,native)、endpoints(repo,url)、source_repositories(repo,source)：識別とmembership。
- roots(acquisition,format,oid)、origins(root,kind,position)：共通walkと由来照会。
- fetch occurrences(collection,page,position/request fingerprint)、listing items(listing,page,position)、completion(scope)：オフラインreplayと差分再開。
- document observations(document,observed time,id)、code observations(CR,observation,id)：履歴/現在pointer検証。
- validator/scope、incremental scan/source identity：誤scope流用を防ぐ。

child indexの自動生成はない。新indexのentry数・page_count・書込みコスト、FK child lookupのEXPLAIN QUERY PLANを次工程で測定し、無条件に全columnへindexを付けない。
今回の限定probeでは各1,000行のsynthetic v2 DBで、PR observation親とcollection repoのchild lookupがSCANからcovering INDEX SEARCHへ変わることを確認した。index-probe.jsonに実追加page数を記録する。targetのcomposite FK用索引・trigger書込み費用は別の実測が必要。
重複するPK prefixで済む場合は追加しない。shadow/FTS tableを既存formatのrow正本としない。
削除は取得済み事実にCASCADEしない。current pointerとparent ownershipはRESTRICT、公開factのidentity変更はtrigger/admissionで拒否する。

データ交換時にはinteger local IDをsource DB namespaceと一緒に扱い、Git objectはformat/OID、bodyはstrong digest+bytesで照合する余地を残す。
今回はDB間merge、双方向sync、change feed、vector clock、全tableのglobal UUID化を実装しない。理由のない再採番は行わない。
