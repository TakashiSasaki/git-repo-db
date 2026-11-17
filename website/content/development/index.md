# Resource Atlas ウェブサイトの開発

サイト編集は `web` ブランチ、本体・設計正本の変更は `main` ブランチで行います。
Google AI Studio では `web` を選択してください。Node/Vite の編集・プレビューは
本体の取得、Python、API キーを必要としません。

```bash
npm ci
npm run dev
npm run build
node scripts/check_web_tree.mjs
```

通常の追随は次の1コマンドで、更新要否の判定、必要な機械生成、要確認箇所のレポートまで行います。

```bash
python scripts/refresh_web.py
```

説明文や設計モデルは自動で書き換えません。レポートは
`website/.build/verification/refresh/report.md` に保存され、要確認項目が残っていても main の作業を止めません。
`--check` は生成せずに計画だけを出します。初回は未確認として扱い、以降も再実行だけでは要確認リストを消しません。

下位コマンドで設計原文やスキーマを使う完全なサイト検証では、`product-source.json` が指定する `main` を
更新開始時に一度だけ取得します。固定 SHA の手動更新は不要です。本体の Python と依存はそこで検証し、ウェブ側の
Python 環境 `website/.venv` は別に作成します。製品用の `scripts/local-run.sh` は
その製品チェックアウトで使い、ウェブの起動コマンドには付けません。

```bash
python scripts/prepare_product.py
website/.venv/bin/python website/tools/schema_viz.py --ir website/.build/inputs/inventory.json --format all
website/.venv/bin/python website/tools/schema_viz.py --ir website/.build/inputs/inventory.json --check
website/.venv/bin/python website/tools/build_docs_site.py --no-mermaid --check
```

実際に取得した本体・ウェブのコミットと IR の識別情報は自動で記録します。
途中で main が進んでも再取得せず、ウェブの遅延や失敗で main の作業を止めません。
本体の正本・スキーマ情報は読み取り入力であり、このブランチで編集する第二の正本ではありません。
SQLite は各環境の Python が読み込むものを使います。検証用に SQLite を差し替えません。
製品側の手順は [main の環境案内](https://github.com/TakashiSasaki/resource-atlas/blob/main/docs/local-python.md) を参照してください。

通常の push は検証とプレビューを行います。公開はワークフローの手動操作で明示的に指定します。
プレースホルダーの Mermaid 図を使うプレビューは完全なリリース受入ではありません。
