# 段階的実装計画と未確定判断

## 前工程の区切り

調査基準SHA/branch確認、実v2構築・全制約抽出、runtimeと試験の読み書き照合、3事象の再現、readonly診断、不変条件、logical target/schema core、全table/column対応、offline変換・検証・切替仕様を作成する。
source application、001/002 migration、schema version、収集済みDB/cacheを変更しない。target production DDL投入、実データconversion/cutover、自動mergeは範囲外。
schema proposalと再現の期待値はレビュー可能にし、未確定を実装済みと書かない。

## P1成果と次工程の実装順序

P1は独立完全DDL、機械契約、制約テストを作成した。[p1-design.md](p1-design.md)に採用判断・未実装・CIの確認方法を記録する。通常runner・実DB・旧cacheは対象外。[P2基盤](p2-foundation.md)でsealed input、exact archive、代表ID map、atomic batch/resume、guardとcapacityを実装した。[P3A handoff](p3a-handoff.md)はoperational source分類と検証済みP2境界のphase初期化を扱う。[P3B handoff](p3b-handoff.md) records the accepted identity recipes, allocation/maps and phase proofs. Remaining domain conversion belongs to P3C–P3E.

P3Aはbounded synthetic acceptanceを確認した。最終local affected closureはP2/P3A 5 filesの156 IDsをnative SQLite 3.53.1とaudited 3.46.1でそれぞれexactly-once pass、skip/failなし。source full inventory/disposition、recognized operational FTS/ANALYZE、complete P2 proof、atomic receipt/restart、genuine hot-journal spill recoveryとguardを含む。これはlocal focused evidenceで、policy/shared変更のfresh hosted full acceptanceと最終SHA/runはPR #1のvalidation記録で確認する。At that boundary, P3B was the next slice; the accepted P3B boundary and current P3C prerequisites are recorded below.
[P1仕上げ](p1-lifecycle.md)でcomplete markerの削除/置換経路を閉じ、本文補完・再発見・再検証・partial→complete・rollback/restartの正当系を完全DDLで実行する。変換契約のstaged writeと旧検証claimの保全をP2/P3へ渡す。synthetic admission例を新runtimeの完成と扱わない。

## 実装順序とgate

| 工程 | 実装 | 終了条件・試験 |
|---|---|---|
| P1 target DDL確定 | source mappingから全physical DDLを作る。format identity、scoped keys、publication/type triggers、JSON/state/numeric約束、archive/ledger、typed scope、sealと単調補完を確定 | 全table/column mapping整合。INSERT/UPDATE/DELETE・NULL・deferred/bootstrap・rollback試験。不正owner/type/flagとcomplete marker削除/REPLACEを拒否。本文/検証/再発見/再開の正当系も実行。標準gate・3.46.1・packaging・後段demo成功。old source formatはread-only入力専用 |
| P2 conversion foundation | sealed source識別、未知構造・typed row hash、new destination、ID map、batch transaction、pause/resume、space preflight、network deny、source/cache write deny | every old key/columnの対応とtyped archive、fault injectionでcommitted batchだけ再開。source/cache fingerprint不変。API client/fetch/GCを起動できない |
| P3A operational source / phase handoff | strict coreと全schema inventory、既知FTS/SQLite statistics分類、全object disposition、verified P2 parentとphase receipt | actual v2 pathの合成fixture、positive/negative source admission、typed archive/map/診断proof、atomic handoff/restart、tamper/competing writer/旧P2 write拒否。lifecycleはbuilding |
| P3B identity conversion — accepted bounded slice | service/source/repository/binding/endpoint/name/membership、明示lookup/allocation/map | Accepted `p3b-identity/1` ownership, immutable P2/P3A evidence, source-derived identity proofs and stable committed binding maps; see [handoff](p3b-handoff.md). Target remains `building`; blockers remain visible and activation is forbidden. |
| P3C stored Git facts — next bounded slice | objects/edges/content/digests/acquisitions/snapshots | Establish a reviewed P3B-to-P3C owner before writes; preserve frozen identity evidence and prove source-derived bytes, IDs, same-owner edges, parent order and raw names. Missing originals remain explicit; reconstruction belongs to P4. See the concrete prerequisites below. |
| P3D saved API/PR history | payloads/pages/documents/versions/observations/reviews/events/unresolved data、progress分離 | A-B-A、本文共有と観測分離、orphan/invalid/partial scopeとoriginal time保持 |
| P3E integrated normalized proof | P3B〜P3Dの合成入力→全normalized conversion→restart | IDs/bytes/edges/pointers/diagnosticsをarchive/sourceと比較。件数/FKだけで成功判定しない。まだactivationしない |
| P4 offline reanalysis | saved REST/GraphQL pages、pending/unresolved payload、stable code listings、root origins、必要local Git raw、manifest/search rebuild | 同一OID refs、page中断再開、head/base変化、cap/GraphQL partial/上書きpage、非canonical raw不在を検証。旧assertionsと派生結果が別に辿れる |
| P5 resume/first sync | typed completion/ETag/watermark/cursors、再利用のscope gate、new runtime command/query対応 | fixture clockでwatermark飛越しなし、replayで前進なし。request logで完了済み子resourceの全件再取得を避け、partialのみ続き、account/API/profile変更を拒否 |
| P6 representative offline dry-run | 実データのsealed inputと容量条件を明示して、別targetへconversionし全proof/query/index gate、pause/abort/restartを検証 | 実データの非公開report、source不変、runtime query/coverage差分説明、bytes/edge/ID mapping、space/時間/indexコスト実測。未解決ケースのdecision manifest |
| P7 cutover | 外部active-catalog pointer切替、新runtime起動、監視とrollback | validated format以外起動不可、source path/cache保持、old referenceへ戻せる。実施対象・運用windowを改めて定める |

P1～P5のsynthetic試験を通ってもP6の実データ変換を成功済みとは言わない。
各工程でcollectorとqueryを同じtarget contractへ更新する。DDLだけ置換して旧applicationを使い続ける必要はない。
変更は作業branch/レビュー単位に分け、mainへ直接commit/自動mergeしない。

## 未確定の設計判断

| 判断 | 推奨案 | 比較・確定条件 |
|---|---|---|
| 全physical tablesの粒度 | 取得fact・mutable progress・typed checkpoint・保全archiveを意味別に分離 | 小table過多のjoin/transaction費用をP1で検証。logical module統合でも所有・時刻の意味は失わない |
| 共通PR/MR名称 | change_requests + binding-scoped number | 今回GitHubデータを移せることを優先。GitLab/Gitea adapterの全面実装は別。request種別/approval意味の無理な同一化を避ける |
| body-store統合 | PR text_bodiesとGit contentsをまず分離 | 全binary・representation/profile・raw証拠を保つ共通byte storeの費用と利点を測定できれば統合。body共有は観測共有でない |
| 新binding/occurrence IDs | bindingはUUIDv4、occurrenceはlocal integer/UUIDを用途別に選ぶ | 旧composite key mapの永続化とreplay determinismが必須。全local integerのUUID化はしない |
| malformed source行 | typed legacy record + blocking/partial diagnostic | critical pointer/identityはnormal activation不可。非critical unknown payloadのarchive利用範囲をexplicitに決める |
| effective coverage | 元assertionを保存し、矛盾・不足scopeを再評価 | raw不在の旧verified claimを新rehash済みとしない。すべてを一律unknownにして全API取得へ倒すことも避ける |
| watermark回復 | 元scan/context証拠から保守的境界を採用、overlap | source timeの確かさ、旧dialect、clock/order不明を検証。証明不能scopeは限定refresh、移行中のfetchは禁止 |
| cache独立性 | source read-only locator、必要ならreflink/independent copy | future runtimeがsourceへfetch/GCしないこと。追加空き・promisor/alternates・必要closureで選択 |
| source sealing | P2は停止済みsidecar-free sourceからbyte copy、前後SHA/stat/schema照合 | live WALをそのまま読むdiagnosticは拒否。source保全とcopy取得の運用を実DBに合わせて確定 |
| index | scoped parent keys/child lookupを優先、derived searchはoffline rebuild | representative page_count/index_bytes/EXPLAIN/書込みコストが必要。FTSなしでも正しいquery |
| archive配置 | target内typed archive + large exact body参照、必要なら同梱sealed sidecar | 全unknown bytesがportable保全されること。source参照だけでtargetの未解決dataが消える設計は採用しない |
| cutover方法 | source外のactive pointerをatomic変更 | volume境界、config path、service起動方法を実運用で確定。source rename/overwriteしない |

## レビュー時に確認すること

- preservation guaranteeの種類（exact bytes、relation、legacy assertion、derived/unknown）がqueryと診断に一貫して現れるか。
- 新しいFK/triggersが古いinvalidデータを黙って落とさず、全column correspondenceへ戻れるか。
- 切替後の最初のsyncで無駄な全PR全子resource取得が起きないことをrequest logで示せるか。
- converterが旧jobs/sync/restoreのshortcutを使い、network/source cache mutationを再導入していないか。
- 未知payloadやstateを捨てたり、partialをcompleteにする暗黙のdefaultがないか。
- source checksum書換えやcountsだけでvalidated gateを通していないか。

この区切りの終了は上記仕様と再現/診断のレビュー可能性で判定する。実移行の許可を既に得たものとして扱わない。

## Historical P3A-to-P3B handoff boundary

These historical requirements are implemented within the accepted [P3B handoff](p3b-handoff.md). They remain preservation constraints, not instructions to repeat P3B. P3C is the next bounded implementation task.

- P3Aのaccepted/rejected layoutとrebuild/exclusionは[英語handoff](p3a-handoff.md#source-admission-and-preservation)を正本とする。strict 53表/287列coreとmigrationは変えず、full schema/physical bytesも保全する。未知user構造はfail closed。supported derived layoutを全SQLite拡張の許可と解釈しない。
- P2 archiveはnormalized target全体ではない。P3Aは同一targetの別runにphase-scoped receiptを保存し、P2のarchive/map/診断/ledgerを保持する。このphaseのwrite ownershipはreceipt初期化のみ。P3Bはdomain書込み前にreviewed version、permitted ownership、output proofsとresume条件を実装する。元P2の現在値proofを変更後に無条件流用しない。
- P3B identity conversion is accepted within its synthetic boundary. P3C–P3E, offline replay/reanalysis, new runtime, first sync, real-data dry-run and cutover remain later gates. `archive_complete`, a phase receipt and identity completion do not establish validation, activation or real-data migration success.
- [変更依存CI](../change-aware-ci.md)の既存p2/minimum-p2へP3A test collectionと依存を追加する。shared fixture/workerやpolicy変更は保守的にfull、未知pathもfullへ倒す。実行済み/再利用/対象外を区別する。

## Accepted P3B boundary and P3C prerequisites

The bounded P3B implementation is `c17b9de2a3a7dd4a98c0d72b93d478f05c860218` on `design/schema-v2-hardening`, PR #1. Fresh full hosted run [37397157259](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37397157259) succeeded. Independent local full validation reconciled 630 normal tests, 2 isolated offline packaging tests and 413 audited-minimum tests. Hosted artifact verification is recorded separately from the run status. The [English P3B handoff](p3b-handoff.md) defines the implemented recipes, exact ownership/proof boundary, focused fault/guard evidence and synthetic size limits; historical P3A runs are not evidence for the new code.

P3B provides `identity-init`, `identity` and `verify-identity` through the guarded worker. Its `p3b-identity/1` receipt binds the authentic reviewed P3A predecessor, complete immutable parent evidence, sealed source, exact contracts/converter and permitted identity writes. Each committed identity batch owns its rows, typed maps, diagnostics, source decisions and proof. Completion processes the bounded recipe sequence; semantic readiness additionally requires no retained parent/P3B blocking diagnostics. Neither result permits activation. The ordinary application remains v2, target lifecycle remains `building`, publication/current snapshot pointers remain unset, and only disposable synthetic DBs/caches were converted.

The next task is **P3C: stored Git facts only**. Before implementing its recipes:

1. Define one concrete P3C protocol, permitted tables/operations/key scope and source-derived output proofs. Verify the complete accepted P3B sequence and its P2/P3A parents before committing a distinct owner under the existing writer lock. Recognize the reviewed predecessor explicitly; retain exact intra-phase resume and reject altered or incomplete boundaries before domain writes. Do not use the P3B receipt as permission to write Git domains.
2. Freeze the P3B receipt, identity rows and preferred endpoint relations, binding allocations/maps, diagnostics, source decisions and committed batch proofs, together with all earlier typed archive and parent evidence. Any necessary enrichment requires a reviewed before/after source relation and new phase proof; historical current-value hashes cannot be silently reused after mutation. Older write commands must refuse the new owner, with an explicit phase-aware read-only proof path.
3. Specify recipes for stored objects/edges/content/digests/acquisitions/snapshots from preserved source facts. Preserve existing IDs and typed mappings, object format/OIDs, raw path/ref/tree-name bytes, parent ordinals, original times, ownership and acquisition assertions. Compare every eligible input and omission against exact archived values and source evidence; counts, FK checks and coherently rehashed output manifests alone are insufficient. Keep shared OIDs/content separate from repository identity.
4. Diagnose missing originals, malformed values, conflicting owners and partial/unknown claims without inventing empty content, reconstructing unavailable bytes or promoting legacy verification/completion assertions. Stored digest bytes and old `verified` flags remain assertions until independently demonstrated verification exists. Git reconstruction/reanalysis belongs to P4; saved API/PR history belongs to P3D, and integrated normalized conversion belongs to P3E. Current/publication pointers remain deferred to their reviewed later gates.
5. Retain guarded offline execution, source/cache/copy/descriptor immutability, network/process denial, sidecar-alias checks and bounded target recovery. Commit domain facts, maps, diagnostics, decisions/progress and proofs atomically. Exercise pre/post-COMMIT interruption, genuine hot-journal recovery, restart/repeat, stable allocation, competing writers and tamper rejection, including source-derived byte/ID/edge/order comparison after resume. Recovery must reverify committed ownership and all parent/output proofs before success or new writes; original-source sidecars are never recovered or removed.
6. Register actual imports, executable contracts/file reads, fixtures and test collections in the existing dependency planner and audited minimum-runtime lane. Keep P1/P2/P3A/P3B, isolated offline packaging and exact selected-ID acceptance; report fresh/reused/not-applicable evidence accurately. Measure modest synthetic rows/bytes/batches/time/memory and address the recorded O(N) proof sets, parent projections and repeated full verification costs before expanding into large Git inputs.

P3C acceptance remains synthetic and offline. It must keep lifecycle `building`, unresolved diagnostics visible and activation forbidden. Real-data access/conversion, acquisition APIs, normal sync/restore, runtime switching, multi-DB exchange, automatic merge and cutover remain outside this task; P5/P6/P7 require their separately scoped gates.
