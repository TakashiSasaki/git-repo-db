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

設計原文やスキーマを使う完全なサイト検証では、`product-source.json` の固定コミットを
別のチェックアウトに準備します。本体の Python と依存はそこで検証し、ウェブ側の
Python 環境 `website/.venv` は別に作成します。製品用の `scripts/local-run.sh` は
その製品チェックアウトで使い、ウェブの起動コマンドには付けません。

```bash
python scripts/prepare_product.py
website/.venv/bin/python website/tools/schema_viz.py --ir website/.build/inputs/inventory.json --format all
website/.venv/bin/python website/tools/schema_viz.py --ir website/.build/inputs/inventory.json --check
website/.venv/bin/python website/tools/build_docs_site.py --product-source "$FULL_PRODUCT_SHA" --documentation-source "$FULL_WEB_SHA" --no-mermaid --check
```

`FULL_PRODUCT_SHA` は選択した本体、`FULL_WEB_SHA` は実際のウェブコミットです。
本体の正本・スキーマ情報は読み取り入力であり、このブランチで編集する第二の正本ではありません。
SQLite は各環境の Python が読み込むものを使います。検証用に SQLite を差し替えません。
製品側の手順は [main の環境案内](https://github.com/TakashiSasaki/resource-atlas/blob/main/docs/local-python.md) を参照してください。

通常の push は検証とプレビューを行います。公開はワークフローの手動操作で明示的に指定します。
プレースホルダーの Mermaid 図を使うプレビューは完全なリリース受入ではありません。
