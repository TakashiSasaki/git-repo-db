# 変更に応じた CI

CI は [現在の policy](../scripts/ci_dependencies.json) と有効な Git tree からチェックを選びます。通常の lane は `tests`、installed wheel / sdist は独立した2 workersの `packaging`、静的検査は `static`、SQLite 機能と doctor は `smoke` です。一つの Python/SQLite binding を使い、独立した SQLite-minimum lane、過去の phase lane、件数・node ID 下限、GitHub artifact の再利用判定を廃止しました。

SQLite 環境は [ADR 0032](adr/0032-environment-sqlite-validation.md) に従います。開発・リリースとも各環境の Python が実際に使う単一版で十分です。テスト用 SQLite の取得・構築・追加導入・差替えや版マトリクスは行いません。Python の選択を依存準備・子プロセスで保持し、実測 Python / SQLite / source ID を記録します。製品の機能・WAL 安全条件を満たさない環境は失敗と報告し、条件を緩和しません。例外は理由・範囲の報告と事前の所有者明示承認が必要です。

通常の開発用CIと独立開発レビューでは、利用可能な1つのCPUアーキテクチャでの検証を受け入れ、x86_64/aarch64の追試やアーキテクチャ別マトリクスを必須にしません。既存のx86_64ホストCIの実行は、そのアーキテクチャのリリースサポート宣言ではありません。リリース対象アーキテクチャは未決定であり、明示的なリリース計画で選んだ対象に限ってアーキテクチャ固有の検証を課します。選択対象の未検証は受入不足として報告します。ADR 0001が要求するローカルとホストの独立したrelease acceptanceと、SQLite等の製品安全条件は変更しません。

PR の初回・再開などは merge-base から実際に試験する merge tree への差分を使います。`synchronize` は event の直前 head (`before`) から実際の merge tree への差分を使い、今回変わった入力を選びます。`before` が無効・欠落・取得不能、または現在の feature の祖先でなければ全体へ広げます。現在の base 由来の code が直前 head に含まれなければ、その差分も全体を選びます。main push は `before` から試験 tree への差分です。rename の両側と削除も NUL 区切りで読み、path を shell code として実行しません。

- `tests/unit`、`tests/integration`、`tests/e2e`、`tests/packaging` 以下で、pytest の標準命名に合うすべての `test_*.py` / `*_test.py` を現在の acceptance として発見します。新規追加・rename に個別 allowlist 更新は不要です。`tests/live` は明示的な opt-in のままです。
- 他の test/helper module から import されていない leaf test の変更は、開発モードではホスト CI での不要な重複実行を避け、静的検査とスモーク検査を実行しつつローカル検証対象（`required_files`）として記録します。Release モードでは全 acceptance を選択・実行します。test module の絶対・相対・同階層 import を AST で検査し、import される test の変更は consumer を落とさないよう全体を選びます。`pytest_plugins`、動的 import や解析できない Python があれば全体へ広げます。共通 fixture の指定は leaf 判定より優先します。
- source、共通 fixture、依存 lock、CI policy、importer は現在の acceptance 全体を選びます。
- 現行 runtime/schema/import contract は `src/**`、CI contract は policy/shared inputs として全体を選びます。
- policy に明示した過去の schema-hardening SQL/JSON/CSV は report inputs です。実GitHub検証と synthetic 検証の JSON も evidence/report input です。非空の JSON object として検証し、不正な JSON、空 object、非有限数を拒否します。拡張子だけで executable と扱いません。未分類の新規 SQL/JSON/CSV は全体へ広げます。
- 通常の prose と `.agents/skills/**/*.md` のみの変更は、読み取りと非空検査を行います。Skill の `scripts/` や未分類ファイルは prose に分類せず、実行可能な変更として全 acceptance を選択します。Skill の YAML frontmatter・リンク・手順はレビューで検証します。
- 未知の依存、比較履歴の欠落・不正、明示的な Release モードは現在の acceptance 全体へ広げます。

main push や PR だからという理由で無条件の full acceptance は行いません。Release モードは明示的な選択です。既知の prose 以外を推測で除外しません。

開発時の通常の検証（Development validation）と、明示的なリリース検証（Release acceptance）は明確に分離されます。通常の PR や push ではローカルでの焦点を絞った検証を基本とし、CI では軽量な静的検査・設定検査・スモークを実行して検証状況を報告します。開発 PR でソース変更時に無条件のホスト全件テストを実行したり、ローカル検証済みケースを自動で重複実行したりしません。完全な独立全件実行（ローカルおよびホストでの pytest 全件、isolated wheel/sdist packaging、厳密な node ID 照合）は、明示的に要求されたリリース検証（`mode=release`）でのみ行われます。

現在の manifest は catalog3 runtime と救出の動作試験を中心に、通常試験と保護境界を含みます。過去の phase export や古い DDL pin の試験は現行 acceptance の下限にしません。不要になった試験の削除も変更として扱い、残る acceptance 全体を選びます。件数の固定下限は設けません。

実行前に選択した file の node ID を収集し、結果の JUnit と exactly once で照合します。失敗、skip、欠落、重複、余分な ID、別 run / attempt / SHA の古い結果、各実行自身の実測環境と異なる binding を名乗る結果は成功扱いにしません。これは実行識別の照合であり、ローカルとホスト CI の SQLite 版の一致を要求しません。確定した CI の証跡は clean tree と一致する必要があります。

`plan.json` は現在の対象、対象外の `excluded_files`、未実行の `unexecuted_files`、ローカル検証が必要な `required_files` を保存します。四つの通常 test directory の file はすべて対象なので `excluded_files` は空です。live および benchmark は通常 acceptance の外です。Development モードの成功は `acceptance_status=development_checks_passed` です。Release モードでは、ホスト全件合格時に `hosted_release_passed` となり、検証済みのローカル release receipt と照合できた場合のみ `acceptance_status=complete_release_passed` が成立します。過去の成功を今回実行した試験として数えません。`validation-manifest.json` はすべての選択チェックが照合できた場合だけ作ります。失敗時は raw JUnit/profile を artifact に残します。

`synchronize` の prose-only 成功は今回の prose 検査の成功であり、過去の runtime 試験が成功した証明ではありません。直前の CI が失敗・未実行・cancelled でも、その結果を再利用しません。実行中に push すると concurrency 設定で前の run が取り消されるため、最終 full run が完了するまで待ちます。source run が失敗・未完了のまま prose を push した履歴でも、後続の成功が `development_checks_passed` に留まることを回帰試験で確認します。

最終統合の確認は手動です。通常 job の緑色だけではマージ準備の完了を意味しません。次の手順で最終入力と完了証跡を結び付けます。

1. 最終統合 tree を clean commit にし、workflow dispatch の `mode: release`（ローカルなら `python -m scripts.ci_plan --mode release`）で acceptance を選択・実行・照合します。失敗・取消・実行中の run は使いません。
2. ローカル環境で `python -m scripts.ci_execute receipt` により clean tree でのローカル release receipt を生成します。
3. `python -m scripts.ci_execute reconcile-release --local-receipt <path> --hosted-manifest <path>` により、ローカル receipt とホスト manifest の双方を照合し、`complete_release_passed` を確立します。
4. plan / manifest の `acceptance_input_hash` を最終 tree の plan と比較します。この hash は prose と明示した report を除く Git tree entries（path、mode、object ID）から作り、runtime、tests、依存、CI policy、未知の入力の変更を検出します。通常 test と shared/executable contract の明示指定は除外より優先します。evidence-only follow-up は同じ hash を持ち、runtime は今回未実行として記録します。
5. base 更新を含む最終マージ候補で hash が異なる場合、その候補の full acceptance を完了させます。hash が一致しても、対応する完了済み full の SHA と run の明示的な確認が必要です。

この fingerprint は結果を自動取得・再利用する機能ではなく、完了証跡を手動で比較するための識別子です。リモート API や artifact の存在を推測して readiness を成立させません。

```bash
uv run --no-sync pytest tests/unit/test_ci_plan.py tests/unit/test_ci_profile.py tests/integration/test_ci_execution.py -q
```

[過去の選択結果](ci-selection-results.json) は `historical-only` です。過去の件数・承認結果は現行の acceptance gate ではありません。

SQLite 方針の再発防止は通常の `tests` workflow の独立した `sqlite-policy` job で行います。
標準ライブラリだけで `python scripts/check_sqlite_validation_policy.py` と detector の
単体テストを実行し、文書だけの変更でも全件 pytest や依存準備を要求しません。
CI・検証スクリプト・AGENTS / Skills・明示された現行手順の禁止構成を検出します。
過去の証跡、負例テスト、製品コードの安全性条件は別の範囲として保持します。
このチェックは既知の構文・命令パターンに対する軽量な防止策であり、所有者の例外承認や
独立レビューを代替しません。承認済み例外でも検出を黙って無効化せず、範囲と根拠を
レビュー可能な変更として記録します。

## sdistの軽量ゲート

[ADR 0033](adr/0033-minimal-product-sdist.md) の収録契約は `sdist_inputs` に分類した
製品入力・build設定・rootメタデータ・配布検証/CI構成の変更で検査します。READMEだけの変更も
sdist入力としてこのゲートと必要な依存準備を選びます。一般のdocs proseだけでは選びません。
不明な比較履歴と明示的Releaseモードでは安全側に選びます。

`acceptance_input_hash` はruntime/tests/依存/CI入力の識別子で、proseの `README.md` を
除外したままです。一方、sdist receipt の `source_inventory_sha256` はREADMEを含む
必須ソース集合のpath・byte数・SHA-256を束ねます。READMEだけの変更では前者は同じでも
後者は変わるため、sdistを再構築して実際の収録内容を照合します。二つのhashを相互の
代用にせず、READMEのためにruntime hashやfull pytestの選択を広げません。

`tests.yml` は準備済みの同じPython/Hatchlingでsdistだけを構築し、
`check_sdist_contract.py --build` により全member、必須入力ハッシュ、有限容量を検査します。
`artifacts/ci-profile/sdist-members.json` に一覧とハッシュを残します。
`sdist_contract` command profileの成功・実測環境・入力識別は既存gateで照合し、
未実行・非ゼロ終了・planの選択改変は成功としません。full pytest/packaging laneの
Development時の自動実行方針は変更しません。sdistゲートの成功は実動作・Release acceptanceではありません。

Accessの既存配布検証も同じcheckerを再利用し、checker・配布verifier・共通fixtureの変更を
workflow triggerに含めます。Pagesのsourceは従来のGit checkoutと公開allowlistのままです。
siteをsdistから生成する経路やデプロイ権限は追加していません。
