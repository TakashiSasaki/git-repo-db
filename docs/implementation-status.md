# 実装状況

仕様の基準は添付 `github-repository-catalog-plan-2026-10-05-2.md` 第19節。
更新日: 2026-10-05 UTC。実データpilotの最終値は下記の記録を参照。

## Schema v2（0.2.0）

Repo IDをUUIDv4として、サービスinstance・native ID・複数Git取得URL・複数sourceを分離する変更を実装しました。
既存migrationのchecksumを維持し、v1のRepo ID・Git object・本文・digest・snapshotを保持します。
管理CLIにinstances、endpoints、repos bind、sourceの既存repo指定、syncのendpoint指定を追加しました。
取得URLはrunで固定し、優先先を変更しても中断したrunの再開先は変わりません。
旧runの取得URLは不明としてNULLで保持します。GitLab/Gitea等のGit-only登録に対応し、MR/PR API adapterは後続範囲です。
現在のschemaは[データモデル](data-model.md)、操作例は[リポジトリ識別と取得先](repository-identity.md)を参照してください。

追加検証はv1 migration・rollback・checksum改変拒否・旧backupの別state復元、マウント別名、native IDのinstance scope、複数API source、外部thread ID衝突、endpointのscopeとSIGKILL後の固定取得先を対象にしました。

- 標準試験: 76 passed / 115.86秒、skipなし。最後のPR namespace非対応判定を追加後、GitHub/identityの関連18件も46.75秒でpassed。Ruff check/format、compileallも実行。
- 実データ4件をbackup後にv2へ移行。Repo ID/current snapshot、78,523 Git object、22,193 content、66,579 digest、14,179 PR文書を維持。過去6,206 runの取得先はNULLのまま保持。
- 全DB/FK/索引の整合性検査passed。v1 backupを旧コードで読み、新DBとの9種類のfirst-page item・coverageの一致を確認。外部通信を遮断し、実credentialと全cloneのない状態で検証。backupのSHA-256は変化なし。
- `scripts/demo.py --work-dir artifacts/demo-run-005 --scenario offline-recovery`: complete。v2の収集、更新、clone回収、offline照会、再索引、backup/復元を検証。
- 0.2.0のwheel/sdistを`artifacts/dist-v2/`へ生成。標準試験内で両distributionのclean installとpackage資源を検証。

一次記録は`artifacts/schema-v2/final-tests.txt`、`api-identity-tests.txt`、`pilot-evidence.json`、`pilot-check.json`、`before.json`、`after.json`と`artifacts/demo-run-005/evidence.json`に保持しています。下記のM0〜M11はv1実装・pilotの検証記録です。

| 工程 | 状態 | 検証した主要経路 |
|---|---|---|
| M0/M1 | 実装・標準検証済み | package、設定、CLI、公開JSON schema、STRICT/FK、DELETE/EXTRA、rollback、単一writer、容量予約 |
| M2/M3 | 実装・標準検証済み | 固定roots、DAG/tree/tag、三種raw digest、SHA-256 Git、可逆本文、raw path、scope、cursor、timeout |
| M4/M5 | 実装・標準検証済み | 全PR状態・文書種別、観測版、REST/GraphQL同一文書、101 threads/replies、独立watermark、ETag、上限・部分応答 |
| M6/M7 | 実装・標準検証済み | 実回収、未完了保存義務の保護、孤児Gitのlock、SIGINT/SIGKILLからの再開、backup/別state復元 |
| M8 | 実装・標準検証済み | contentless trigram世代、原文照合、scan補完、索引の世代切替・故障復旧、cloneなし再構築 |
| M9/M10 | 中核gate検証済み | オフライン標準試験、wheel/sdistからのclean install、両entry point、CI定義、文書、再現demo |
| M11 | 指定4件のpilot完了 | 全Git/PR収集complete、1,262 PR、全clone実回収、9種類の照会で削除前後一致。10GB/10GB条件を維持 |

## 検証記録

標準試験は実Git、loopback合成API、dummy credential、SQLite実ファイル、実CLI subprocessを利用。
親と子Pythonの外部通信を遮断し、Git transportをfileに限定。実tokenのない環境で実行する。

- `UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync pytest tests/unit tests/integration tests/e2e tests/packaging --strict-markers -m 'not live and not benchmark' -x -q`: 68 passed / 105.74秒（2026-10-05、最終source変更後、skipなし）。
- Ruff check、format check、compileallを実行。
- wheelとsdist由来wheelを新規venvにoffline導入し、source外のCWDから両entry point、収集・照会・migration/GraphQL/schema資源・DB checkを利用。
- `scripts/demo.py --work-dir artifacts/demo-run-004 --scenario offline-recovery`: complete。合成Git/APIの更新、clone実回収、offline検索、再索引、backup、別stateへの復元を検証。`artifacts/demo-run-004/evidence.json`。
- `artifacts/dist/`: wheelとsdist。`artifacts/runtime-requirements.txt`: lockからのruntime依存export。

## 実データ試験の範囲

最初のlive smokeは指定された空repo `TakashiSasaki/git-repo-db` のみ。
HTTP gzipの二重decodeによる最初の失敗を残し、修正後の新規stateで1 passed / 4.27秒。最終sourceでの追加smokeは1 passed / 4.21秒（live-smoke-003）。対象未指定の起動はAPI呼出前に失敗することも確認。
`artifacts/live-smoke-001/`は失敗記録、`artifacts/live-smoke-002/live-evidence.json`は修正後の記録。
GraphQL静的queryも実APIで検証。存在しないPR #1へのlookupエラーはPR収集成功とは扱わない。
実PRの収集は続くpilotで確認する。

ユーザー指定のpilotは以下の4件。4件目の表記訂正はユーザーから確認済み。

- TakashiSasaki/templates
- TakashiSasaki/museum-portal
- TakashiSasaki/museum-portal-aistudio
- TakashiSasaki/gas.moukaeritai.work

cache_max_bytesとmin_free_bytesはそれぞれ10,000,000,000（decimal GB）。
専用stateは`artifacts/pilot-001/state`。対象ごとに`--include-repo`でsourceを限定し、所有者の全repo列挙は実行しない。
最終結果は4件ともGitとPRのcoverageがcomplete。PR数はtemplates=1,105、museum-portal=50、gas.moukaeritai.work=107、museum-portal-aistudio=0（計1,262）。
保存済みGit objectは78,523、commitは15,672、unique contentは22,193、三種digestは66,579、PR文書・観測版は各14,179、review threadは1,868。
raw Blobのlogical unique byte数は283,203,593、可逆保存したUTF-8本文は107,960,728 bytes、保存API応答のdecoded bodyは415,875,943 bytes。これらはwire転送量ではない。

4件のGit再同期は4.86秒でcomplete、objects/contents/digests/document_versionsの増加なし（PR全件取得の完了前に実行）。
初回museum-portalのGit/50 PRは300.858秒、gas.moukaeritai.workのGit/107 PRは817.975秒、museum-portal-aistudioは5.099秒。
templatesは修正適用のための中断・再開を含む。最長の継続attemptは7,699.709秒で全PR文書を保存したが4件のGit取得でpartial、現在の参照の存在を確認して26.455秒で再開しcomplete。これを無中断初回所要時間や純粋なhash速度とは扱わない。
以前の試行にはHTTP gzip二重decode、容量走査中の消失maintenance.lockによるIO_ERRORがあり、修正と回帰試験の記録を保持した。再開時は保存済みPRのcompletion checkpointを利用し、全件を再取得しない。

最終の全索引再構築は18.843秒、DB全整合性検査は11.979秒でcomplete。全4件のPR listもcomplete。
GC測定ではTTLを一時的に0へ設定し、4 cache世代すべてをCLIの通常GCで実削除した後、元の設定を復元した。
cache allocated bytesは176,594,944から16,384（空directoryのみ）、work=0、残存cloneのHEADは0。
DBは2,554,703,872 bytes、物理空きは29,376,851,968 bytes。cache_max_bytesとmin_free_bytesの10GB設定は保持した。

各クエリ10回、毎回新規CLI subprocess、warm OS page cacheで測定。外部通信は遮断、実credentialを除去。
以下はfirst page（既定100件まで）の所要時間で、p95は10標本のnearest rank（最大標本）による記述値。全page走査やcold cacheの保証値ではない。

| 照会 | p50 ms | p95 ms | backend |
|---|---:|---:|---|
| repos list | 64.93 | 73.63 | scan |
| refs list | 62.66 | 67.67 | scan |
| tree list | 68.26 | 72.66 | scan |
| path README | 66.02 | 74.66 | scan |
| raw SHA-256 | 918.96 | 997.31 | scan |
| code 認証 | 1336.92 | 1440.61 | scan |
| code function | 1017.22 | 1050.31 | fts+scan |
| PR museum | 4546.87 | 4861.24 | fts+scan |
| commit symmetric compare | 116.74 | 122.89 | scan |

9種類すべてcompleteで、GC後も同じitemとexit codeを返すことを確認。全page、全literal、将来の更新を含む一致を主張するものではない。
一次記録は`artifacts/pilot-001/measurements.json`、最終coverage/整合性検査は`final-evidence.json`、収集経緯は`evidence.json`、`templates-recovery*.json`、再同期は`repeat-evidence.json`。
実データ、認証値、生成state、配布artifactをソース管理へ含めない。

## 環境・一次資料

Python 3.12.14、Git 2.52.0、uv 0.12.19、PythonにリンクされたSQLite 3.53.1。
STRICTとFTS5 trigramを実行確認。GitHub REST版2026-03-10を使用。
SQLite公式資料のWAL修正条件（3.51.3以降または3.44.6/3.50.7のbackport）を確認し、未修正版を拒否する。
環境のinstall scriptとstart instructionsをドラフト保存済み。反映には環境設定画面で保存・公開が必要。
ソースと文書はGitリポジトリで管理する。実データstate、API応答、配布artifactはソース管理の対象外。

## 制約と継続判断

全300repoへの展開、スケジュール登録、外部公開は実行範囲外。
取得可能な公開repoでのpilotは、非公開repoすべてへの権限や将来のAPI応答を保証しない。owner全件のinventoryは公開/所有private件数と列挙結果を照合し、権限範囲が確認できない、または件数が一致しない場合は既知repoを保存してpartialを返す。対象指定のinventoryは明示対象のアクセスとIDを個別に確認する。
原文保存は固定profileの全heads先端UTF-8/NULなし/8MiB以下。全履歴本文、binary、LFS実体、添付実体、完全archive、Web GUI、意味検索は初版の範囲外。
PR詳細の入れ子配列は各100件まで表示し、`nested_collections`で保存総数・省略を明示。外側cursorは入れ子配列の続きを取得するcursorではない。
初回の構造保存はオブジェクト単位のtransactionで行うため、多数の小objectではfsyncが速度を制約し得る。新しい取得rootからの到達walkは毎回行うが、保存済み検証済みobjectの再展開・再hashは省略する。保存済み直接指定PR関連OIDでは、同じrepoからの公開済みclosureとlocal Gitでの存在を確認し、再fetch/再walkを省略する。symbolic PR headはremoteで観測する。manifestは設定の行数/byte数で区切ったbatchを保存する。
巨大tree/commit等の非Blob objectは一つをメモリに保持して解析する。Blobはbounded chunkで処理する。
wire転送量、fetch中peak、hashのみの処理速度、cold OS cache、全300件の推定は今回の計測と分ける。未測定値を推奨値や確定見積りに置き換えない。
