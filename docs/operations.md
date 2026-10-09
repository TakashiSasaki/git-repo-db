# 運用

DBとdomain本文は永続領域、cache/work/quarantineは管理作業領域です。任意の `transport-archive/` は補助通信記録で、正常な現在状態の利用には必要ありません。
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

backupはwriter lock内でsourceの全payload bytesを走査し、新たな物理破損を診断・隔離してからSQLite backup APIを使います。コピーのSQLite整合性と全bytesを検証し、checksum/configuration/identityと `quarantined_payload_count` をmanifestへ保存します。DB fileの単純copyで代用しません。
出力DBと隣接する`<output>.manifest.json`を必ず一緒に保管・移動してください。restoreには両方が必要です。cacheはbackupに含まれず、保存しなかったGit原本まで復元できる完全mirrorではありません。
restore先は未作成のpathを指定します。空directoryを含む既存pathは拒否します。毎回fresh stageへコピーし、checksum・identityを確認してから、診断走査前にコピーのactive隔離件数をmanifestと照合し、全bytes検証を続けます。件数不一致や未説明の破損では公開せず、作成した失敗stageを保存します。Linuxのatomic no-overwrite公開で競合した場合も、先に作られた宛先を保持します。
復元後の照会は保存データで動作します。収集の再開前に取得元、認証、予算を再確認してください。
cache/lease/予約/旧running processを有効な復元状態とみなしません。

`quarantined_payload_count` は必須の非負JSON整数で、bool・文字列・小数・負数・`9223372036854775807`を超える値を拒否します。数えるのは検証済みコピーのactive `payload_quarantine` 行だけです。同じphysical objectの複数representation、修復済みの診断履歴、staging、cache隔離directoryは数えません。正の一致件数は正常に扱い、既知の隔離bytesと診断を保持します。件数が一致しても未説明の破損を許容しません。archiveの欠落・故障をこの件数へ含めません。

catalog3 の新規初期化は schema version **15** のcomplete packaged DDLから直接行います。旧開発DBとそのbackupは拒否し、migrationや互換viewは設けません。v2 importerとfinalizeは廃止済みで、D2は `not_applicable / retired` です。歴史的なreceiptと不明identityの捏造禁止は維持します。

通常Issue/コメントとレビュー/レビューコメントは各リソースの最新受理状態を保存します。PRタイトル・本文・PR会話コメント、Git、独立スレッドの履歴は保持します。通常の現在状態と必要な完全性証拠はcatalogだけで再起動・照会・再索引・交換・backup/restoreできます。

部分取得で未提供の値には元のclockと取得scopeを保持します。後着した古い完全応答は未知の項目だけを補完でき、実際の同時刻矛盾は未解決として確認します。Issue移動後も、子コメントには現在所属と元の取得元の両方が残ります。受信先に移動元repo/Sourceがなくても、その取得snapshotを保持して交換できます。

照会の `last_checked_at_us` はこのcatalogで正常なlive取得を確認した時刻です。事前revision/scopeの一致を確認した初回・編集・同内容取得で単調に更新します。provider更新時刻や項目ごとの取得時刻とは用途が異なり、importや再解析では進みません。最新状態だけを照会していても、以前の共有本文は自動GCされません。容量計画では[実測された本文保持量と列用途](current-state-schema-liveness.md)も考慮してください。

## 任意の通信記録

`catalog.toml` の `[github]` にある `record_messages` はbooleanで、既定はfalseです。有効時はstate配下の `transport-archive/` にHTTP content-decoding後の正確な応答bytesと許可リストのmetadataを保存します。資格情報headerを記録しません。recorder障害は許可された32文字以下のコードだけを使い、観測時刻・試行番号とともにtransport内で最新100件を保持します。未知のコードや予期しない例外は `ARCHIVE_FAILURE` とし、例外本文を診断へ出しません。警告表示はbest-effortで、warnings-as-errorsや表示hookの故障でも有効なdomain保存を続けます。取消し・HTTP・解析・DBの失敗は通常どおり伝播します。記録の有効/無効はcollection coverageを変えません。

```toml
[github]
record_messages = false
```

`parser inspect-message REF --max-bytes N` と `parser reparse-message REF --context FILE --max-bytes N` は明示した保存通信を上限付きで読みます。後者は投影だけを返し、元の観測時刻を保持して通常状態を自動更新しません。再解析contextはprovider投影に必要な所有者・取得scopeを明示するJSONです。[記録仕様](latest-state-transport.md)と[CLI](cli.md)を参照してください。

catalog backupは補助archiveを含めず、多storeのforensic backupや保存期間・自動削除を保証しません。archive保持を別に選ぶ場合は、その用途と容量を別途管理します。本文bytesは書き換えずに保存するため、source本文内の秘密情報までmetadata filteringで除去されるわけではありません。

最初のsyncではscope、service、principal、API/parser/profile、head/baseの証拠が一致する一覧やvalidatorだけを再利用します。復元された旧job/lease/容量予約を過去の証拠として扱い、新しい実行を開始してください。

実GitHub同期は、対象1repoと操作範囲、通常のsecret供給、リクエスト数・時間予算を別途指定・許可してから行います。sourceの`--include-repo`は発見対象、`sync --repo`は収集対象を限定します。共通の`--timeout-seconds`は照会用で、同期全体の期限や要求数上限にはなりません。HTTP timeoutも要求単位です。指定予算を既存の制御で保証できない場合は、実行前に最小限のtransport上限を追加するか、確実に制限できる操作範囲へ絞ります。

実データ検証は、失敗した試行も含めて`docs/validation/real-world/`へMarkdownと隣接JSONを記録し、handoffまたは関連PRからリンクします。application commit、対象ref/OID、環境、実行command、範囲と予算、実測の要求数・時間・DB/cache容量、照会・復元結果、診断とPASS/FAIL条件を残します。代表的な正規化照会出力はSHA-256で復元前後を比較します。DB/cache・認証付きHTTP原文・secret・private payloadはコミットしません。成功記録の正本はこの報告で、Issuesは不具合や未解決作業に使います。

定期運用ではsync、jobs resume、cache gc --applyをcron/systemd等から呼べます。
この開発では実ユーザーのスケジュールを登録しません。実運用の対象・周期・要求予算はpilot後に決めてください。
LFSはGit pointer bytes、添付はsource本文と埋込みURLを保存します。本体取得・URLの自動巡回は行いません。archiveの保存期間・自動削除、包括的な削除伝播、全履歴本文・diff索引、意味検索、Web GUI、非Linux restore、CAS-76/CAS-77は保留範囲です。現在の実装・検証・制限は[構造改善の対応記録](current-state-schema-closure.md)、[完全schema一覧](current-state-schema-inventory.md)、[実装対応表](latest-state-transport-implementation.md)と[統合handoff](model-integration-handoff.md)を参照してください。
