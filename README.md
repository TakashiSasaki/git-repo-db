# Resource Atlas

Resource Atlas は、Git リポジトリとファイルシステムのカタログを作るアプリケーションです。
Git の構造・参照・履歴・Notes、GitHub の PR・Issue・レビュー、ファイルの属性・ダイジェスト・走査履歴を SQLite に記録し、取得元に接続できないときも照会できます。

通常 CLI は責任ごとに分離した保存形式を使います。Git の commit/tree/tag の実際に検証した表現と、受信側で Notes の役割を検証した本文を保持できます。一般の Git ファイル本文を保存するアーカイブ機能はありません。PR などのテキストは Context が所有し、ファイルシステムの走査は属性とダイジェストを記録します。

## 保存先とクラス

| 責任 | 所有する内容 |
| --- | --- |
| Repository | Git の恒久的な同一性、観測・主張、構造、許可された検証済み表現 |
| Context | Provider のリソース・テキスト・取得元・項目別の根拠と競合 |
| Access | 接続先・Scope・接続設定・ローカルな承認 |
| Operational | 再開可能な取得要求、累積予算、実行・キャッシュの状態 |
| Search | 元のデータから再構築できる検索投影 |
| Filesystem | ファイルシステムのルート、走査、エントリーとダイジェスト |
| Worktrees | Git 格納場所・作業ツリーの観測と明示的な関連 |

必要な役割だけを初期化します。これは 7 個の DB を毎回開くという意味ではありません。
[クラスとテーブルの対応](docs/architecture/persistence-model.json)には、各テーブルの所有者と専用の生成行クラスを定義しています。入力 DTO・値・照会結果は行クラスと区別します。列・キー・外部キーは実際の DDL から読み取れます。

```bash
scripts/local-run.sh python scripts/persistence_model.py --check
scripts/local-run.sh python scripts/persistence_model.py --format markdown
```

## 開発環境と初期化

```bash
./scripts/setup-local-python.sh
scripts/local-run.sh repo-catalog --help
scripts/local-run.sh repo-catalog init --scope repository --catalog /path/to/new-catalog
scripts/local-run.sh repo-catalog doctor --catalog /path/to/new-catalog
```

`--catalog` は新しい保存先を指定します。`--scope` は `repository`、`context`、`paired`、`access`、`operational`、`search`、`filesystem`、`worktrees` から選びます。`paired` は同じカタログの Repository と Context を初期化します。取得の再開・予算管理には Operational を明示的に追加します。

```bash
scripts/local-run.sh repo-catalog init --scope operational --catalog /path/to/new-catalog
```

互換性のない既存 DB は上書き・変換しません。以前の通常形式の DB を利用するには、その形式に対応する過去のチェックアウトを使ってください。開発環境の準備・診断・オフライン運用は [docs/local-python.md](docs/local-python.md) を参照してください。

## 取得・照会・管理

コマンドは用途別です。各コマンドの `--help` が現在の引数を示します。

```bash
scripts/local-run.sh repo-catalog acquire --help
scripts/local-run.sh repo-catalog query --help
scripts/local-run.sh repo-catalog context --help
scripts/local-run.sh repo-catalog access --help
scripts/local-run.sh repo-catalog operations --help
scripts/local-run.sh repo-catalog exchange --help
scripts/local-run.sh repo-catalog recovery --help
scripts/local-run.sh repo-catalog reparse --help
```

取得要求は `acquire` の `--input` に渡す明示的な JSON で指定します。ローカル Git、HTTPS/SSH Git、GitHub の REST/GraphQL、複数取得元のバッチを扱います。承認が必要な Context 操作には、対象を限定した `--authority` を指定します。Source は恒久 UUID、Provider リソースはサービスと種類を含む完全なキーで選択し、表示名から同一性や権限を推測しません。資格情報は参照として指定し、再開時に解決します。

一つの取得要求の予算は、再試行・再開・バッチ内の取得元を通して累積します。途中で止まっても独立して受理できる結果を保持し、未完了の範囲を完全とは扱いません。通常の照会は保存済みデータを読み、取得元への接続や本文の自動取得を行いません。

PR の `query pr-code`、`query pr-documents`、`query pr-list` は、実際の親一覧・対象の head/base・選択した文書やスレッドに範囲を限定します。ページやフィルターの外にある不足も確認し、古い完全な取得で新しい不完全な観測を補いません。項目の欠落と明示的な null は異なり、比較できない更新や同時刻の異なる値は、元の取得元・時刻を持つ候補として残します。

ページングは件数とスナップショットに基づき、別途有限のバイト数・SQL・出力予算を使います。旧形式の固定 8 MiB による自動ページ分割は引き継ぎません。新しい HTTP 走査は取得範囲を改めて取得するため、旧形式の自動 `since` 最適化よりリクエストが増える場合があります。

## 独立したファイル・作業ツリーのカタログ

Git や Provider の DB を初期化せずに利用できます。

```bash
scripts/local-run.sh repo-catalog-local init \
  --filesystem-db /path/to/filesystem.sqlite3 --worktrees-db /path/to/worktrees.sqlite3
scripts/local-run.sh repo-catalog-local scan \
  --filesystem-db /path/to/filesystem.sqlite3 --worktrees-db /path/to/worktrees.sqlite3 \
  /path/to/checkout-or-bare-repository
scripts/local-run.sh repo-catalog-local export \
  --filesystem-db /path/to/filesystem.sqlite3 --worktrees-db /path/to/worktrees.sqlite3 \
  --scan SCAN_UUID --output files.efu
```

走査は通常ファイルを毎回ハッシュし、変更中・読取失敗を履歴に残します。リンク先は追跡しません。EFU/CSV の出力は保存済み観測だけで行えます。部分走査には明示的な出力許可が必要です。[操作契約](docs/architecture/local-catalog-contract.md)と[連携 CLI](packages/local/README.md)を参照してください。

## 交換・復旧とドキュメント

Exchange は選んだ型付きリソースと依存・元の根拠を交換します。受信した主張は送信者の認証や受信側の検証成功を意味しません。原本の補助的な HTTP 記録はドメインデータから独立し、その削除や記録障害でカタログの照会・交換・復旧を無効にしません。

保存済みの権威あるデータに破損を検出した場合は通常利用を停止します。疑わしい元データを変更せず、明示的な診断・サルベージ、新しい保存先へのバックアップ復元、型と根拠を再検証したマージ、検証後の有効化を行います。Repository の事実を更新・削除して修復する操作や、旧形式の隔離件数による継続はありません。

[現行ランタイム案内](docs/current-runtime-reference.md)、[ADR 一覧](docs/adr/README.md)、[生成スキーマ監査](docs/implementation/separated-persistence-boundary.md)を現在の入口にしてください。Schema 20/21 の文書や保存済み検証結果は、それぞれの revision の履歴です。開発中のプロトタイプであり、通常の開発 CI の成功はリリース受入や全環境の検証を意味しません。

ウェブページの編集・Google AI Studio へのインポートは [`web` ブランチ](https://github.com/TakashiSasaki/resource-atlas/tree/web)で行います。正本の設計・スキーマは `main` が所有し、ウェブは `main` を非同期に追跡します。固定した本体 SHA の維持や同時更新は不要です。[受け渡し規約](docs/adr/0042-asynchronous-web-main-tracking.md)と[サイト運用](https://github.com/TakashiSasaki/resource-atlas/blob/web/website/README.md)を参照してください。
