# 独立 Reviewer B — 七 PR 結合 runtime review

判定: **APPROVE_IN_REVIEWED_RUNTIME_SCOPE**。新規の結合実装 blocker は 0。
Reviewer `/root/review_b` はレビュー対象の production 修正を作成していない。
本判定は所有者の merge 承認、Full Release Acceptance、production activation を意味しない。

## 正確な入力

- 実行・レビュー source: `388b824d1b3abe41c902759bf37a52c6ee5bcd2f`
- effective tree: `ea006924152d2fc508c7eb21697ad3c376e373f6`
- detached worktree: `/workspace/review-b`、独立した locked dev/docs `.venv`
- `AGENTS.md`、ADR index、ADR 0001/0002/0003、0014、0025/0026/0028 の該当契約、要求された CI/three-store skills、P7/Schema21 README と先行 B evidence を確認した。
- `source-bindings.json` は全 `src/` Git object 内容の SHA-256 と比較を記録する。P7 凍結 source `178ddbaa8fa06f52aff4993730205c5a38da91f4` に対する唯一の production 差分は public `adapters/sqlite/index.py`。Schema21 凍結 source `74f90adae40ae60076dca33629fa2edbf5763474` に対しては P7 recovery 6 files と bounded `git_native.py` header loop だけが増分である。
- Public acquisition/GitHub collector、JobService、Store、QueryService、CLI は main と同一。Schema21 結合は P7 実装を書き換えていない。これは入力比較の結果であり、異なる SHA 上の古い実行を今回の実行に読み替えるものではない。

## 今回の独立実行

**13 passed / 0 failed / 0 errors / 0 skipped、exit 0、pytest 18.29 秒。**
`focused.execution.json` が argv/cwd/環境/時刻/exit/source/tree を記録する。
`collection.log`、`focused.xml`、`focused.jsonl` を独立再照合し、13 unique collected = 13 unique JUnit = 13 unique journal starts、setup/call/teardown 39 phases が各 node に各 1 回、すべて passed と確認した。
`reconciliation.json` に全 node ID と判定を保存した。

- Schema21 の Operational loss 後の genuine Core terminal 再利用、および Operational complete/Core rollback split-write の拒否: 2 node。
- frozen Source/settings job plan と Operational loss/Core preservation: 2 node。
- 201 stale document batch の後の current document 取込、cancel 時の旧 ready generation 保全、二度の rebuild、empty rebuild、durable Core text 不変、および issue/comment current body 置換: 2 node。
- opt-in P7 activation、missing Core 拒否、四 fault cuts での locator 保全、有効な既存 locator 置換: 7 node。

独立した `runtime-probes-corrected.py` も exit 0 で実行した。

1. Job INSERT 後の Attempt INSERT を SQLite trigger で失敗させ、Job/Attempt 両方の rollback を確認。
2. Restart が旧 Attempt を interrupted にする途中で新 Attempt INSERT を拒否し、旧 state/current_attempt が完全 rollback することを確認。次の正常 resume は original request を保ち、旧 running attempt を `interrupted/process_restart`、新 attempt を running にする。complete 後の resume は拒否し attempt が増えない。
3. Job 実行は Core revision/identity を変更せず、jobs/attempts/progress/index tables は Core に存在しない。`PRAGMA database_list` に attached store alias がない。
4. P7 backup API に public Schema21 directory を渡すと `BackupValidationError: Authoritative core database missing .../core.sqlite3`。backup artifact は公開されず、source 全ファイル SHA-256 は不変。
5. public Store に新しい opt-in P1 directory を渡すと `NOT_INITIALIZED`。`catalog.sqlite3` を作成せず、P1 source bytes は不変。

初回 `runtime-probes.py` は reviewer probe 自身が作った TEMP trigger により `PRAGMA database_list` に `temp` が現れることを誤って禁止し、assertion failure となった。これは product defect ではない。初回 source/log/exit をそのまま保存し、`main` と許可された SQLite `temp` のみを認める訂正 probe を別ファイル・別 disposable directory で実行した。失敗を成功ログで上書きしていない。

## Runtime と境界の評価

`ApiFacts.begin` は genuine Core completion marker を照合し、Operational の complete/cursor 単独では terminal を認定しない。不完全 acquisition は別 collection/実観測で安全に再取得する PF-P04/PF-P07 の既存契約を維持する。Operational loss は admitted facts を取り消さず、古い Job が missing なら明示的な新 Job を必要とする。physical 三 store のテスト観測を修正する PR 群は、本番 routing/DDL を変えていない。

Public Search の唯一の runtime 修正は、pinned Core read snapshot から得た `current_keys` に新 generation membership を限定するもの。旧 ready generation の参照する document を先に削除せず、cancel 時は旧 generation を保ち、201 個の stale-only prefix を読み飛ばして後続の現行 input に進む。new generation の expected count は current unique keys であり、旧 Search rows 全体を数えない。promotion 後は参照のない derivative のみ prune し、Core text は削除しない。metadata-only/現行 text と derivative の authority は逆転しない。

P7 の activation における Search/Operational は target schema の `initialized_empty` であり、public index.rebuild を接続していない。今回 public Search 修正から P7 replay/budget/stop/typed admission への依存は追加されていない。両 runtime の入口に互換 alias/implicit ATTACH/migration がないことを独立 probe でも確認した。

Shared target `git_native.headers` は split-all allocation をやめ、同じ byte line sequence を metadata reservation 前に大量 materialize しない loop にした変更である。public Schema21 collector/decoder の routing は変更していない。P7 source binding と parent の完全 regression 実行は別の証跡として扱う。

既存 Schema21 evidence が説明する Search promotion 後 cleanup の全 phase 原子性は新たに保証しない。reader lock による cleanup failure 診断は既存 evidence に残り、今回の結合で再導入された契約違反とは判断しない。

## 環境と限界

Python 3.12.14 / SQLite 3.53.1 / Linux 6.18.44 x86_64、workspace overlay 約 32 GiB。環境の実値・dependency versions は `environment.json`、実行時 overrides は execution JSON。workspace 専用 `TMPDIR` と `--basetemp`、独立 `.venv/bin` を先頭にした PATH で親/子 CLI を結合した。import origin は `/workspace/review-b/src/repo_catalog/__init__.py`。

この役割は complete full-suite、255-node P7 全体、installed distributions、hosted release を独立再実行したとは主張しない。それらは root/Reviewer D の実行・照合に属する。本レビューは上記 13 node と独立四 probe、および source/contract interaction の範囲で承認する。live/stress、実 host power loss、NFS/Windows、full Context salvage/P8 runtime wiring、production catalog/backup の操作は未実行であり、追加保証を行わない。

source/feature branch の修正、merge、release、deployment、production activation は一切行っていない。最終 source worktree は clean。
