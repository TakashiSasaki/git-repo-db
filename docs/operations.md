# 運用

DBと本文は永続領域、cache/work/quarantineは管理作業領域です。
profile、cache_max_bytes、min_free_bytesはinitで明示します。
高低水位・TTLはcatalog.tomlで調整し、全300repoの値はpilot実測から決めます。
物理空き容量ではSQLite、journal、索引の二世代、backup、ログ等の増大も考慮してください。

Git取得前に容量予約とcache世代のOS lockを取得します。
使用済み予約と実使用量を二重計上せず、転送中もheadroomを監視します。Git転送のdeadlineは既定300秒で、`collection.git_transfer_timeout_seconds`で調整できます。deadline到達時は子process groupを停止し、jobを再開可能な状態で残します。
不足時は待機として返し、shallow化や未保存原本の強制削除で回避しません。
厳密な占有上限が必要な運用では専用volume/quotaを併用してください。

```bash
repo-catalog --state-dir /path/to/state cache status
repo-catalog --state-dir /path/to/state cache gc
repo-catalog --state-dir /path/to/state cache gc --apply
```

gcの既定はdry-runです。TTL期限または予算圧迫により、保存義務を満たしたcacheだけを回収します。
DB照会やAPI pollingでTTLを延長しません。最新runが成功しても同じ世代の古い未完了義務は免除しません。
削除はlock→DB再確認→evicting→同一filesystemのquarantineへrename→実削除→evictedの順です。
親が終了しても生存Git子processのlockが残る間は回収しません。

中断したsyncは`jobs show JOB_ID`で確認し、`jobs resume JOB_ID`で再開します。
rate limitのnot_before前に再送しません。未確定fetchと固定済みrootの解析再開を区別します。
CLIを多重writerとして起動するとbusyで待機します。

```bash
repo-catalog --state-dir /path/to/state db check --full
repo-catalog --state-dir /path/to/state db backup --output /path/to/new-backup.sqlite3
repo-catalog --state-dir /path/to/new-state db restore --input /path/to/new-backup.sqlite3
```

backupはSQLite backup APIを使い、checksum/configuration manifestを併記します。DB fileの単純copyで代用しません。
出力DBと隣接する`<output>.manifest.json`を必ず一緒に保管・移動してください。restoreには両方が必要です。cacheはbackupに含まれず、保存しなかったGit原本まで復元できる完全mirrorではありません。
restoreは新規/空stateだけに行い、元stateを上書き・削除しません。
復元後の照会は保存データで動作します。収集の再開前に取得元、認証、予算を再確認してください。
cache/lease/予約/旧running processを有効な復元状態とみなしません。

catalog3 の新規初期化は schema version 7 の packaged DDL から直接行います。旧 catalog3 開発 DB とその backup は拒否します。旧catalog3→v7 migration や互換 view はありません。旧 v2 の取得済みデータは、停止した source を別の新規 state へ `import-v2` で救出し、`db finalize` の明示的な readiness 検査を通します。元 source DB/cache は読取り専用証拠として保護され、runtime cache へ流用・回収されません。typed archive、変換診断、source identity と current 選択の原証拠は別の `import-v2/workspace.sqlite3` に保存します。正規化済みの事実・観測・coverageは `catalog.sqlite3` に残ります。

実データ試行では、許可された場所から元DB/cacheを読み取り専用で特定し、取り込み先・backup・restore・測定先は自動生成した別の一時directoryに置きます。元データを一意に特定できない場合は、候補と不足情報を報告して変更前に停止します。cacheを保存していない場合も明示し、欠けた原本はpartial coverageとして扱います。旧DBの取り込みと公開repoからの新規収集は別の検証範囲です。

sourceに`-wal`、`-shm`、`-journal`がある場合、削除してimportを通してはいけません。元DBとsidecar一式を保全し、writerを停止した状態でcacheとの整合性も確保した別コピーを用意します。sidecarが残る入力は、保全したコピー側でSQLite backup API等の整合コピー手順を行い、sidecarのない別DBを作ってからimportします。`import-v2`は元DBのcheckpointや修復を行わず、現在の`db backup`はcatalog3用です。元資料は実用上の受け入れが完了するまで保持してください。

imported current pointer は同じ owner の公開済み事実と元の選択証拠からだけ復元します。最大 ID、import 時刻、曖昧な watermark を根拠にしません。重要な owner/identity 破損は finalize を拒否します。任意の本文欠落や部分一覧は coverage として通常利用できます。元 import workspace がなくても通常照会できます。

最初の sync で scope、service、principal、API/parser/profile、head/base の証拠が一致する一覧や validator を再利用します。不明な legacy cursor は再開に使わず、必要な対象だけ明示取得します。imported job/lease/容量予約は過去の証拠であり、新しい実行を開始してください。

実GitHub同期は、対象1repoと操作範囲、通常のsecret供給、リクエスト数・時間予算を別途指定・許可してから行います。sourceの`--include-repo`は発見対象、`sync --repo`は収集対象を限定します。共通の`--timeout-seconds`は照会用で、同期全体の期限や要求数上限にはなりません。HTTP timeoutも要求単位です。指定予算を既存の制御で保証できない場合は、実行前に最小限のtransport上限を追加するか、確実に制限できる操作範囲へ絞ります。

実データ検証は、失敗した試行も含めて`docs/validation/real-world/`へMarkdownと隣接JSONを記録し、handoffまたは関連PRからリンクします。application commit、対象ref/OID、環境、実行command、範囲と予算、実測の要求数・時間・DB/cache容量、照会・復元結果、診断とPASS/FAIL条件を残します。代表的な正規化照会出力はSHA-256で復元前後を比較します。DB/cache・認証付きHTTP原文・secret・private payloadはコミットしません。成功記録の正本はこの報告で、Issuesは不具合や未解決作業に使います。

定期運用ではsync、jobs resume、cache gc --applyをcron/systemd等から呼べます。
この開発では実ユーザーのスケジュールを登録しません。実運用の対象・周期・要求予算はpilot後に決めてください。
LFS実体、添付実体、完全原本archive、全履歴本文・diff索引、意味検索、Web GUIは後続範囲です。

## Import workspaceの寿命

import開始から `db finalize` 成功までは、`catalog.sqlite3` と `import-v2/` 配下のworkspace・sealed sourceを一組として保持します。workspaceはプロセス終了でも消えない作業用DBです。途中で片方だけをコピー・移動・削除して再開しないでください。workspaceの欠落・別catalogとの取り違え・schema改変・symlink/hardlinkは拒否します。

両DBの変更とbatch receiptは、固定workspaceをATTACHした一つのSQLite transactionでcommitします。この処理中は両方のDBにDELETE journalとsynchronous=EXTRAを要求します。WALで独立した二つのcommitを行う実装にはしません。初期作成の二つのファイル名公開の間で停止した場合も、対応するidentityを検証して再開します。

正常にfinalizeされたcatalogはworkspaceなしで照会・検査・backup/restoreできます。`import-v2/` はその後に破棄可能ですが、自動削除はしません。未完了・失敗状態では保持してください。元のv2 DB/cacheはworkspaceとは別であり、削除・書換えの対象にしません。通常のbackupはworkspaceを含みません。
