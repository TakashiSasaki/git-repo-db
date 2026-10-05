# データモデルと不変条件

正本schemaはpackage資源`resources/migrations/001_initial.sql`です。
番号とSHA-256 checksumを`schema_migrations`へ記録し、変更を検出します。
初版のschemaは開発中に作成した新規DB用です。以後の変更は既存migrationを書き換えず、番号付きmigrationを追加します。

| 実体群 | 主なtable |
|---|---|
| 対象・目録 | sources、inventory_runs、repositories、repository_names |
| Git観測・公開 | collection_runs、snapshots、ref_observations、acquisition_roots |
| Git構造 | git_objects、commits、commit_parents、tree_entries、tag_objects |
| 内容・digest | contents、content_digests、blob_content_map、content_locations |
| 先端path | root_manifests、root_manifest_entries |
| PR・文書・観測 | pull_requests、pr_observations、pr_documents、document_versions、resource_observations |
| PR関係 | pr_reviews、review_threads、review_comments、pr_events、pr_code_observations、pr_git_links、pr_commits、pr_file_changes |
| API | api_responses、collections、collection_pages、collection_memberships、sync_checkpoints |
| 検索・索引 | search_documents、index_generations、index_membership |
| 作業・回収 | jobs、coverage_components、cache_entries、cache_leases、space_reservations、preservation_obligations |

Git objectは方式＋完全長OIDで識別します。path/ref/tree nameはBLOBです。
commitのparent順序を保持し、commitへ固定branch IDを割り当てません。
全commit×全pathの永続展開を行わず、共有tree構造から歴史的pathを復元します。
現在のheadsに必要なmanifestはroot treeごとに共有します。

Blobの通常digest入力はraw payloadだけです。Git OIDの入力には型と長さのheaderを付けます。
raw digestはrepresentationとalgorithmを持ち、MD5/SHA-1だけで内容を統合しません。
SHA-256＋長さの候補索引は非一意で、衝突候補を表現できます。既存OIDとraw digestの不整合は上書きせずエラーにします。

同じ内容の複数repo/branch/pathの取得根拠と出現を保持します。
symlinkはlink自身のBlob、gitlinkは外部commit参照です。LFS pointerのdigestをLFS実体の検証済みdigestと扱いません。

PR文書は本文実体と観測を分けます。A→B→Aは本文版2種類でも観測順を保持します。
REST/GraphQLの同じreview commentはprovider/node IDで結び付けます。
API response payloadはSHA-256とbodyで再利用し、request/pageの来歴は別に保存します。

publication_seqは結果集合やcoverageの公開変更で進みます。結果が不変な索引再構築では進みません。
cursorはDB instance、publication_seq、query fingerprint、sort keyを含み、変更後は再開始を要求します。
restoreは新しいDB instanceを発行し、元DBのcursorやcache/lease/予約を有効化しません。
