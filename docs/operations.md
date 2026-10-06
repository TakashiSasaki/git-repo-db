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
restoreは新規/空stateだけに行い、元stateを上書き・削除しません。
復元後の照会は保存データで動作します。収集の再開前に取得元、認証、予算を再確認してください。
cache/lease/予約/旧running processを有効な復元状態とみなしません。

catalog3 の新規初期化は packaged DDL から直接行います。旧 v2 の取得済みデータは、停止した source を別の新規 state へ `import-v2` で救出し、`db finalize` の明示的な readiness 検査を通します。元 source DB/cache は読取り専用証拠として保護され、runtime cache へ流用・回収されません。typed archive、診断、source identity と current 選択の証拠は target 内へ保存します。

imported current pointer は同じ owner の公開済み事実と元の選択証拠からだけ復元します。最大 ID、import 時刻、曖昧な watermark を根拠にしません。重要な owner/identity 破損は finalize を拒否します。任意の本文欠落や部分一覧は coverage として通常利用できます。元 import workspace がなくても通常照会できます。

最初の sync で scope、service、principal、API/parser/profile、head/base の証拠が一致する一覧や validator を再利用します。不明な legacy cursor は再開に使わず、必要な対象だけ明示取得します。imported job/lease/容量予約は過去の証拠であり、新しい実行を開始してください。

定期運用ではsync、jobs resume、cache gc --applyをcron/systemd等から呼べます。
この開発では実ユーザーのスケジュールを登録しません。実運用の対象・周期・要求予算はpilot後に決めてください。
LFS実体、添付実体、完全原本archive、全履歴本文・diff索引、意味検索、Web GUIは後続範囲です。
