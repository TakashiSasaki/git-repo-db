# P7 crash recovery and independent acceptance — 2026-10-16

P7の残存安全性修正と独立検証を完了した。**全リポジトリの完全合格とは扱わない**。
最終実行ソースは `178ddbaa8fa06f52aff4993730205c5a38da91f4`、Git tree は
`9740ad1a91f367192bb31ce9777d039c2bb4729b`。この証拠追加は実行入力を変更しない。
最終PR HEADは証拠コミットを含むため、試験対象ソースSHAと区別する。

## Crash recovery / history

[Phase 0 inventory](crash-recovery.md) のとおり、最初に存在したのは
`/workspace/git-repo-db`、branch `work`、main `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`
のみ。未コミット、未追跡、stash、固有の未pushコミット、進行中Git操作はなかった。
旧P7 agentの作業環境はここに存在せず、他環境の未保存作業の有無は確認不能。
16個のreflogコミットを `refs/recovery/20261016/pre-fetch/<full SHA>` に固定し、
元Gitディレクトリ、binary-safe差分、プロセス、ファイルハッシュを外部に保存した。
ロック削除、reset/clean/prune、履歴書換えは実施していない。

最初にfetchした#87/#88/#89はそれぞれ `290e9831` / `e0c6fd85` / `7cbe97f0`。
元#88の46 integration testsは独立再実行し、46 passedを確認した。再実装ではなく、
この既存実装を継続して修正した。新#87は
`c058af3a1be9ba3e9a1b0ba649c789f5bdcd1d75`、#88の祖先である。
途中で別経路から到着したdesign merge `12f1b04488a7e95cd0b7f057ad5c2bc6aee739d2` は
`refs/recovery/20261016/remote-concurrent-design-12f1b04` に固定し、通常mergeで両履歴を保存した。
元の `711a9cd` design mergeを重複実行していない。mainは変更していない。

このセッションで作成した実装・レビューworktreeも削除せず保存した。
最終HEAD/status/diffは `final/final-worktrees/` に個別保存している。
`p7-input-followup` の残存20,020-byte差分は1182738へ統合済みの中間ドラフトで、
後続の厳密なContext処理に置換されている。固有の未統合作業はなく、元差分と
`final/input-followup-leftover-disposition.json` を保存した。これは元クラッシュ環境からの
回収ではなく、このセッション内の開発素材である。

## Reproduced corrections

- **Durable request accounting:** strict ASCII request identity、不変の予算契約、同一IDの
  process間flock、Operational/Search外のregistry/marker/checkpointを導入した。
  読取・decode・検証・admissionの前に予約をfsyncし、atomic replaceとdirectory fsyncで
  固定する。SIGKILL後は不確かな予約を保持する。正常な同一live attemptだけが実測値へ
  settleでき、その書込順序も中断時に大きい予約を採用する。同一ID再試行、別の明示ID、
  予算増額拒否、破損・欠落・曖昧JSON・FIFO拒否、初期化途中の再開を検証した。
- **Bounded actual work:** DB/WAL/SHM/journalを実バイトで制限し、増大・置換を検出する。
  SQLite length/column/SQL/VM制限と限定projection、bounded JSONL read、decode前の
  JSON深さ/要素数、base64/hex/UTF-8/proof/header/metadataの予約を適用した。
  拒否候補も課金する。巨大末尾を数えるための無制限scanを行わず、未知件数を未知とする。
  partial候補、未読table/page、予算上限は不完全receiptとなる。
- **Replay / provenance:** digestだけで再送扱いせず、native type/declared size/bytes、
  physical copy、repository/Capture origin/Capture UUID、source/ref/root、Notes target/path/
  role proofを検証する。NotesのCapture/role/body admissionを同一atomic unitにし、
  拒否時の余分なCaptureを残さない。元の出所とforensic抽出の出所を分離する。
  欠落した必須Core/Context authorityの再挿入を修復として実施せず停止する。
- **Corruption classification:** 正に確認したschema/domain/retained-byte破損を永続停止し、
  staging限定の破損、lock/permission/I/O/環境制約、判定不能を区別する。
  suspect本体をread-only SQLiteで開くことによるsidecar変更を避け、writer cut下の
  bounded forensic copyで確認する。SQLite 3.53.1のintegrity_checkが見逃したCHECK違反も
  trusted DDLの全CHECKと永続的domain predicate、bounded UTF-8監査で検出する。
  正当な過去proof・terminal履歴、空文字列、binary Notesは受理する。
- **WAL / stop / filesystem:** genuine P1 CoreとContextの未checkpoint committed WAL、
  source DB/WAL/SHMの完全同一性、独立processのwriter cut、停止後のin-flight writer排出、
  copy中SIGKILL、実P5/P6 entry point停止を検証した。restore/activationはfd/inode pin、
  actual copied-byte hash、strict bounded manifest、NOFOLLOW/NOREPLACE、stop/publication fence、
  locator parent再検査を使う。symlink/parent置換、同時destination作成、alias、sidecar、
  mutation、fsync/rename失敗、部分merge、有効化前validationを試験した。

## Exact-source execution

各command、cwd、exit code、時刻/経過時間、node ID、JUnit、journal、ハッシュは
[artifact index](final/artifact-index.json) の対応先に保存した。
大きいlog/XML/JSONLと元の末尾空白を含む一部証拠はmtime=0のgzip、probe/driverは内容を保った `.py.txt` である。
indexは元パス、元バイト数・SHA-256、保存物SHA-256を記録する。

| Scope | Result | Evidence |
| --- | --- | --- |
| Complete P7 integration | 255 passed, no skips/errors | root full run; independent C; installed D |
| P1/P2/P3/P4/P5/P6 | 317 / 197 / 75 / 202 / 47 / 50 passed | root full run: 888 total |
| P2/P3 and P5/P6 compatibility | 20 / 29 passed | root full run: 49 total |
| Wheel installed P7 | 255 passed, 61.12s | independent/d |
| Wheel-from-sdist installed P7 | 255 passed, 52.80s | independent/d |
| Generic offline wheel / sdist-wheel CLI | 2 passed, 54.15s | executions/distribution-final |
| Schema, boundary, dependency, publication audits; Ruff lint/format; schema visualization | all exit 0 | executions/final-overlay-178ddba/execution.json |

Both independently built wheels have SHA-256
`dfab687567d3b3202c1ac4de0e2d1485835eb42f3a962242c05c762b5ac2e414`。
124個のpackage/runtime/resourceファイルが最終sourceと一致し、親・子processともcheckout外の
site-packagesをimportした。配布archive/venv/合成catalog本体は外部証拠領域に保持し、
Gitには識別ハッシュと実行証拠を保存する。

**全体結果は 229 failed / 3517 passed / 2 errors、3748 selected、exit 1、566.77s**。
失敗・エラーの全231 nodeを元mainで再実行し、同じfailure/errorを確認した。
228件は既存実行時試験の失敗で、既知のSchema 21 fixture失敗5件はその部分集合である。
追加223件を隠さず保存する。228件の内訳はmissing-table 221件とassertion 7件で、
全231件について正規化した例外/assertion文言と失敗source位置までmainと照合した。
[独立照合記録](final/independent/d-root-reconciliation/reconciliation.json) を参照。
別の1件は文書unit testのpinned Chrome不足。
2 errorsはoffline wheelhouse未準備で、外部に48個のlock-pinned wheelを用意した
上記再実行では2 passed。元2 errorsは変更しない。途中の外部tempパスがcheckoutと
文字列prefixを共有し、fixtureのstartswith判定に誤検出された2 failuresも別保存した。

default marker policyが外したのは明示的に2件だけ：live smokeとnested pagination stress。
全3750 nodeのcollectionと差分を保存した。これらは実行済みとは主張しない。
既存の失敗をskip/xfailへ変更していない。全リポジトリの完全acceptanceは未達である。

初回の並行全体試験は8.8GiB `/tmp` tmpfsを使い切り失敗した。そのraw結果と環境情報は
`executions/final-178ddba` / `main-full` に保持し、成功証拠として使用しない。
容量のあるoverlay上にTMPDIRと新規basetempを指定し、最終全体試験とmain比較を再実行した。
監査分類欠落を発見した途中run、誤った仮説のprobe、bootstrap失敗も別に保持する。

## Independent reviews

各実装担当は自身の修正の独立承認から外れ、別担当が対象を検証した。
これはADR 0027の権限制限内の帰属付きengineering reportであり、owner承認ではない。

- [A database/domain](final/independent/a/reviewer-a-report.md): 同一tree上612 passed、
  intrinsic破損、歴史的proof/空文字列、実lock/permissionの独自反例。
  [A supplement](final/independent/a-supplement/review-178ddbaa.json) はCHECK/UTF-8、
  binary Notes、履歴、bounded dependency lookupを独立検証した。
- [B crash/filesystem](final/independent/b/review.json): 65 passedと9独自process/FS反例。
- [C security/accounting](final/independent/c/review.md.gz): 38独自probeと全255 P7。
  reservation直後、実際のContext COMMIT後、report前のhard killとprocess再起動を含む。
- [D distributions/evidence](final/independent/d/REPORT.md): 両installed distributionの全255、
  node照合、独自Capture反例、実hosted receipt、WAL assertion品質、設計整合を検証。

## Hosted CI / ancestry / runtime

[Development run 38922059845](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38922059845)
は成功。実receiptは `development_checks_passed`、`full_acceptance=false`、runtime pytest **0**。
feature SHAは178ddbaa、temporary test mergeはd9fc2feb、treeは同一9740ad1。
21個のreceipt memberを検証したZIP SHA-256は
`5a85672b47be48e544abe1b58c9618e77277f9a60050f7264ddd6fc123e2bd27`。
これはP7 hosted runtime試験を実行した証拠ではない。release workflowは起動していない。

main → #87 design → #88 implementation の祖先関係を確認した。
63個の既存public runtime module、既定DDL、CLI/store/resourceの公開経路はmainと同一。
opt-in P7と明示的audit分類だけを変更した。Schema 21切替はない。

## Independent Pages CI workstream

#89は `660178ff1a881e4482b7a3cde02b51dc50cf2603`。
schema checkerの実importに必要な10個のtransitive trigger path欠落を独立再現し、
そのpathと回帰試験だけを追加した。P7を混入していない。
[PR89 committed evidence](https://github.com/TakashiSasaki/git-repo-db/tree/660178ff1a881e4482b7a3cde02b51dc50cf2603/docs/implementation/evidence/pages-ci/2026-10-16-independent-review)
参照。最終HEADのPages run38918703718は実Mermaid 10枚、MkDocs、安全性・link検査を成功、
8 tests passed、deploy skipped。Development38918703695も成功、runtime pytestは0。

過去の非制御比較はunit tests 21.54s→0.68s、job 84s→53sであり、因果分離したbenchmarkでは
ない。path filteringの節約量は未測定。local real-renderはChrome取得/providerと管理者制約で
失敗し保持したが、同一HEADの実hosted renderingを確認した。preview archiveの取得は403。
branch protection照会も403、rulesetsは[]で、required status policyを全確認したとはいえない。
ownerのmerge判断とrequired-check確認を残し、実装上はowner review可能。

## Supported limits and remaining gates

試験環境はLinux 6.18.44 / Python 3.12.14 / SQLite 3.53.1、local cooperating processes、
flock / `/proc/self/fd` / renameat2 / fsync契約。合成catalogはtmpfsとoverlayで試験した。
SIGKILL・例外・syscall順序を物理host電断耐久性と同一視しない。実ディスク電断、NFS、
Windows、特権者の任意namespace置換、全accounting証拠の一括悪意削除は保証しない。
Python allocation probeはnative SQLite RSSの上限を証明しない。

未対応Context resource/field candidateは非権威observation。全Context tableのtyped再構築は
約束しない。Operational/Searchは `initialized_empty` で、Search完全projection rebuildではない。
最終domain validationに合格しないcatalogの有効化を許さない。validな部分集合と
salvage全件回収の完全性は別であり、merge receiptは全件回収の証明にならない。
外部attributionを真正なorigin保証へ昇格しない。

Owner-level ADR blockersは0。試験したP7範囲の未解決実装blockerは0。
全リポジトリacceptanceの未解決項目は228件の既存実行時失敗とlocal文書browser環境。
live/stressと完全hosted release acceptanceは今回の通常development検証の実行範囲外で、
新たな通常merge要件として課していない。owner merge承認とrequired-check政策の確認は別gate。
P8のpublic runtime接続・projection rebuild・運用環境検証は将来作業である。
PR87/88/89はmergeしていない。release/tag、production recovery/activation、意図的Pages deployも
実施していない。全実行は使い捨て合成catalogを用いた。
