# 不変条件・現状根拠・提案保証・既存データへの影響

調査基準SHAと構造はREADME/current-schema.json。F=FK/UNIQUE/CHECK、T=trigger、A=application admission/transaction、D=オフライン監査・診断。
SQLite CHECKは別tableを参照できず、NULLで評価がunknownになる式は違反にならない。NULL許容を先に決め、必要なNOT NULLと組み合わせる。
下表は調査基準からの設計対応。現在の全DDL・試験・残余gateは [invariant-contract.json](invariant-contract.json)、更新/削除方針は [p1-design.md](p1-design.md) が正本。statement時unpublishだけでは不十分なため、親identity/fact固定と単調公開を追加した。

| ID / 不変条件 | v2の保証と根拠コード | 提案する保証方法 | 既存データへの影響・診断 |
|---|---|---|---|
| I01 repoの所属・内部ID | repository UUIDはapplication生成。v2 binding `(instance,native_id)` UNIQUE、repo.source_idは単一の旧列。`repository_identity.bind`、`CollectionService._discover` | F: repo ID、binding ID、instance/native ID UNIQUE。A: UUIDv4新規発行、URL/OIDでrepo統合しない | repo UUID維持。bindingだけ新IDを作り旧composite keyを対応付ける。ID衝突は診断・保留 |
| I02 endpointは同一repo | v2 run_endpoint_repo INSERT/UPDATE trigger。repo.urlは優先endpointの重複projection。endpoint DELETEはFK RESTRICT相当 | F: `(endpoint_id,repo_id)` scoped FK。preferred endpointはrepoのpointerを唯一の正本にする | 優先0件、旧url不一致を黙って選ばない。runの過去URLがNULLなら維持 |
| I03 snapshot/run/repo | 個別FKのみ。`GitImporter.sync`で同repoを渡すがSQLでは別repoにできる | F: snapshots(acquisition_id,repo_id)→acquisition(id,repo_id) | `snapshot_run_repo`診断。row再割当はAPI再取得でなく旧証拠を照合。曖昧なら阻害項目 |
| I04 current snapshot | v2 current_snapshotにFKなし。`MaintenanceService.check`は存在/publishedのみ、repoを検査しない | F: `(current_snapshot_id,repo_id)` FK。T: pointer設定時published、参照中のunpublishを拒否。DELETE RESTRICT。bootstrapはNULL→target作成→設定 | cross-owner pointerが既存checkを通る再現済み。最新generationだからと自動修復しない。旧pointer自体を保全 |
| I05 current PR observation | v2 current_observationにFKなし。`ensure_pr`で更新 | F: `(observation_id,change_request_id)` FK。T: publication、参照中unpublishを拒否 | missing/別PRを診断。payload/時刻から勝手に最新選択しない |
| I06 current document version | v2 current_versionにFKなし。`document`で更新 | F: `(version_id,document_id)` FK、DELETE RESTRICT。version/bodyはimmutable | cross-document pointer再現済み。旧body・version・pointerを記録し、意味が未確定なら停止 |
| I07 resource observation belongs to document | document_id/version_idそれぞれFK、同じdocumentかは未保証 | F: composite version/document FK | `resource_version_document`。観測行は本文の重複排除で削除しない |
| I08 review / thread / comment同一PR | reviewsのpr/document、commentsのdoc/threadは独立FK。`document/thread_comments`が正しい値を渡す | F: document/CR、thread/CR scoped keysをコメント/レビューへ付与。A: provider IDはbinding内で解釈 | `review_document_pr`、`comment_thread_pr`。v1/v2のthread内部IDを維持、外部IDはraw payloadから別属性へ |
| I09 code observationとPR snapshot | 個別FK。commit/fileはcode observationへFKだが再開で別observationに分断 | F: observation/CR FK、stable listing/CR FK。T/A: commit/file pointerは正しいkind。A/D: completeは全page/context証明後のみ | `code_observation_pr`、complete_*_listing_fragment。raw pagesを全再解析し、旧complete assertionとeffective stateを分ける |
| I10 API collectionとrepo/PR | collections.repo_id/pr_idは独立FK。`collection`はapplicationで同repo | F: `(change_request_id,repo_id)` FK、NULLはrepo-wide collection | `collection_pr_repo`。PRを番号だけで決めない |
| I11 code→Git acquisition同一repo/PR/観測/role | pr_git_linksはcode/acquisitionの個別FKのみ、root.observation_idはFKなし | F: code/pr observation、root acquisition/repo FK。T: 親経由のCR/repo/role/expected OID一致。A: exact roleとAPI期待OIDの検証 | `code_acquisition_pr`。NULL acquisitionは未取得として維持。違う証拠をつなぎ直してcompleteにしない |
| I12 root seedと由来の区別 | `UNIQUE(run_id,oid,role)`、ref同一OIDでINSERT失敗。formatをuniqueに含まない | F: acquisition/format/OID/roleでwalk seed共有、別root_originsでref/PR-role出現を全保持 | seed ID維持。manifest/refから複数originを生成し対応を記録。保存されなかった観測時刻はunknown |
| I13 Git OIDの表現 | git_objectsだけformatとBLOB長CHECKあり。他root/ref/tree/linkは不十分。PR OIDは自由TEXT | F: 全OIDにformat enum、BLOB/20or32-byte CHECK。A/D: TEXT hexは明示decode・元字句保存、期待OIDと実取得OID照合 | `oid:*`。不正値はzeroやNULLへ黙って変換しない。unknownを別状態で扱う |
| I14 Git objectの意味・形式 | object.type enum、FKでID存在のみ。commit.tree_idがblobでもFKを通る。`import_objects/parsed`はapplication側で型を扱う | T: commit/tree/tag/blob_map/parentが参照する型とformat。T: 参照済みobjectのidentity/type変更拒否。A/D: 実byteからOIDとsize検証 | git_object_type_*。gitlinkは外部commitでchild_id NULLを許す。raw tree不在なら原本再構成を断定しない |
| I15 raw contentとdigest | 三種digest長CHECK、blobとの原文照合は`save_blob`。representationは自由TEXT。SHA-256候補索引は非一意 | F: digest algorithm/長さ、非負byte_length。A/D: raw byte hash・length一致。衝突候補はexact bytesで比較し、missing bytesなら共有を断定しない | 既存content/digest IDs維持。verified_at/pipelineは旧検証の主張、移行の検証時刻とは別 |
| I16 API/body hash | document body_sha256は32byte CHECK、API shaは長CHECKなし。`collection/document`がhash計算 | F: SHA長、body byte_length。A/D: raw SHA再計算。UNIQUE(hash,bytes)で衝突表現可能 | `sha256:*`。API wire/gzip前bytesではなく保存decoded bodyを保持。hash不一致は原本と旧assertionを隔離、無断補正しない |
| I17 boolean | endpoint.is_preferredのみ0/1 CHECK。他published/verified/deleted/obligation/manifest flagsは自由INTEGER | F: NOT NULL + IN(0,1)全適用 | `boolean:*`。2をtrueへcastしない。旧flagをlegacy recordへ保持し判定保留 |
| I18 ordinal・数値 | parent_ordinal、size、reservationの一部は非負CHECK。PR/page ordinals、attempt/generation等は緩い | F: position≥0、attempt≥1、number≥1、bytes/generation≥0。A/D: parent ordinal density、page chain、finite not_before | `ordinal:*`、`attempt:*`。page*10000+positionは連番ではない。全ページ位置へ再解析、不明なorderは元ordinalのまま保全 |
| I19 JSONと自由文字列 | STRICT TEXTはJSONを保証しない。metadata/request/scope/valueなどはapplication json.loads。root_manifestはarray、Git path/refはBLOB | F: json_validと期待object/array shape。A/D: schema version付きkey dialect解析。自由理由/URL/path/OID文字列をJSON扱いしない | `json:*`はsyntaxのみ。妥当JSONでも期待形状不明ならlegacy opaque。NULLはabsence、{}や[]へ勝手に置換しない |
| I20 stateの値と遷移 | 大半stateは無制約TEXT。Git run=planned/fetching/refs_captured/published、failedはjobにだけ保存され得る | F: tableごとのenum（unknown明示）。A/T: 許可遷移、attempt fence、公開前postcondition。取得事実とexecution stateを分離 | `state:*`。unknown値は捨てず診断。旧runningを稼働中プロセスとして復元しない |
| I21 観測時刻・再解析時刻 | nowはclient時刻。`document`のnormalization時にもnow、`INSERT OR IGNORE(collection,doc)`で同collection内複数観測が失われ得る | F/A: observed_at/source time、parsed_at、converted_at、time provenanceを別に保持。observed不明はNULL+raw claim | 元timestamp文字列を保全。同本文でも新API requestの観測は別。保存されなかった過去更新は捏造しない |
| I22 本文重複と観測 | `(doc,sha,body)`でversion再利用、別resource_observationsに履歴。A→B→Aの本文は2種類 | F: global text bodyをexact bytesで共有、versionはdocumentに属しID維持、observationにはbody同一uniqueを設けない | 全観測ID/順序/時刻/本文対応を検証。反復観測をbody hashで消さない |
| I23 完了collectionとwatermark | 完了collectionのreturn/replayでもincremental_commentsが新nowを書き込む | A: scan identityとscan_started_at不変、page chain/cap/context成功時だけ安全境界更新。D: legacy checkpointの上限を保存scan証拠から保守的に評価 | 再利用で前進する事象再現済み。updated_atを観測済み境界にしない。証明不能なscopeのみneeds_refresh |
| I24 validator/再開scope | ETagはrepo native ID/source/principal/version/URL/acceptを含むJSON key。watermarkはcolon key。旧dialectも残る | F/A: binding/source/principal/URL/query/accept/API/parser/profileをtyped scopeとして固定。cursorはそのscan/endpoint/contextにだけ再利用 | scope/value原文保持。account/権限変更で使わず、別主体のvalidatorやpage cursorを混用しない |
| I25 jobsと取得事実 | collection_runs/cache_leasesが最新job.attemptに依存。旧attemptは上書き、checkpoint用途混在 | F: job_attempts(job,attempt)とmutable progress。factsは実取得/観測IDに属する。A: destinationにlease/reservationを新規取得 | 旧attempt全履歴は再現不能。最後に保存された状態のみsource provenanceとして残し、架空attemptを生成しない |
| I26 coverageの正本 | owner_id自由TEXT、state/details更新で古い値は残らない。照会はcomponent stateを読む | F: typed scopeとimmutable claims/current pointer。A/D: effective coverageを保全・再解析証拠で判定し、旧asserted stateは残す | ambiguous owner、破損/欠落/partialはcompleteへ格上げしない。全remote historyを保存した主張にしない |
| I27 cacheを原本と混同しない | cacheはGCで消える。content_locationsもunavailableになる。saved digestsだけのbinary rawは復元できない | A/D: source cacheはreadonly検証、必要なら独立コピー。raw existence/closure/locator validityを別に記録 | source cacheを削除しない。missing cacheは全API再取得の理由にしない。復元不能rawのscopeを診断 |
| I28 互換列と名前 | repo.source/host/native/urlはbindings/endpoints/membershipと重複、nameは最新metadataで更新 | F/A: 互換projectionを削除、display name/alias assertion/native nameを意味別に整理 | 旧列はlegacy recordへ保存し正本と照合。矛盾を多数決やURL一致で処理しない |
| I29 index/検索 | FTS世代・membership、search_documentsは派生。入力bodyとraw照合、scan fallback | F: scoped current index、safe generated names。A/D: final durable inputからrebuild、exact source keys/bodies/offsets/coverageを比較 | source FTSを編集/削除しない。stale/orphan derived rowsはlegacy archiveへ。無索引で正しい照会を維持 |
| I30 format・変換完了の識別 | v2 catalog_meta version + schema_migrations checksum。通常runtimeはversion不一致を拒否 | F/A: target format_id/version/DDL hash、source fingerprintとconversion run manifest、validated gate。新DB instance IDを発行 | 旧checksumを差替えない。件数一致・DDL checksum一致だけで移行済みにしない |
| I31 DELETE/UPDATE parent保護 | 個別FKは既定NO ACTION。current pointersには参照保護がない箇所がある | F: scoped composite FKとRESTRICT。T: 公開/参照中のidentity/type/owner変更を拒否。A: 構築中はNULL pointers、検証後設定 | sourceは不変。targetがpointer未確定なら診断し、parentを先に消して解消しない |

## 制約とコスト

FK親のscoped UNIQUEはSQLiteでは別indexを要し得る。idだけのPKに加え(id,owner_id)を置くのはownership検証の費用として明示する。
child側のFK indexはSQLiteが自動作成しない。parent更新/削除時の全scanを避けるindexと、照会用途のindexを兼用できるか個別に検討する。
OID/digest形状、boolean、JSONはCHECK、parent ownershipはcomposite FK、parentの型/公開状態はtrigger、暗号学的検証・dense order・完成条件はapplication/監査で扱う。
triggerを増やすだけでは完成証明にならない。直接SQL INSERT/UPDATE/DELETE、transaction rollback、中断/再開を全DDLで試験する。
