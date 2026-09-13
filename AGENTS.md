# AGENTS.md

このファイルは Codex がこのリポジトリを扱う際のガイダンスを提供する。

## プロジェクト概要

`silicone-casting` は **シリコーン造形用の樹脂型モデル（3D プリント可能）を生成する Blender アドオン**。マスターモデルから、注型・脱型できる分割型を作るまでのツール群を提供する。

## 開発原則

LLM コーディングで陥りがちなミスを減らすための行動指針。**慎重さを速度に優先する**バイアスを置いている。trivial なタスクでは判断で柔軟に運用してよい。

### 1. 実装前に考える

**仮定を勝手に置かない。混乱を隠さない。トレードオフを表に出す。**

実装に着手する前に:

- 仮定は明示的に述べる。不確かなら質問する
- 複数の解釈が成り立つなら全部提示する。黙って 1 つに決めない
- もっと単純な方法があるなら言う。正当な理由があれば押し返す
- 何かが不明瞭なら止まる。何が混乱の原因か名指しして質問する

### 2. シンプルさを優先

**問題を解く最小限のコード。投機的な実装はしない。**

- 頼まれていない機能は足さない
- 単発の用途しかないコードに抽象化は入れない
- 要求されていない「柔軟性」「設定可能性」は持ち込まない
- 起こり得ないシナリオに対するエラーハンドリングは書かない
- 200 行書いて 50 行で済むなら書き直す

自問する: 「これをシニアエンジニアが見たら過剰だと言うか?」Yes なら単純化する。

### 3. 外科的な変更

**触る必要があるものだけ触る。自分が散らかしたものだけ片付ける。**

既存コードを編集するとき:

- 周辺コード・コメント・整形を「ついでに改善」しない
- 壊れていないものをリファクタしない
- 自分なら違う書き方をするとしても既存スタイルに合わせる
- 無関係な dead code に気付いたら指摘する。勝手に消さない

自分の変更が orphan を生んだ場合:

- 自分の変更が原因で未使用になった import / 変数 / 関数は消す
- 元から dead だったコードは、頼まれない限り消さない

判定基準: diff の全行が、ユーザーの要求から直接トレースできるか?

### 4. ゴール駆動の実行

**成功条件を定義する。検証できるまでループする。**

タスクを検証可能なゴールに変換する:

- 「バリデーションを足す」→「不正な入力に対するテストを書いて通す」
- 「バグを直す」→「再現するテストを書いて通す」
- 「X をリファクタする」→「変更前後でテストが通ることを確認する」

複数ステップのタスクでは短い計画を先に提示する:

```
1. [手順] → 検証: [チェック]
2. [手順] → 検証: [チェック]
3. [手順] → 検証: [チェック]
```

強い成功条件があれば独立してループできる。弱い条件 (「動くようにする」) は確認を繰り返す羽目になる。

**この原則が効いている指標**: diff から不要な変更が減る、過剰実装による書き直しが減る、ミスの後ではなく着手前に確認質問が出る。

## メモリ参照

プロジェクト固有の規約・知見・ユーザーの好みは repo ルート [memory/](memory/) に保存する（git 管理対象）。エージェント固有メモリは [memory/agents/](memory/agents/) 配下に同じレイアウトで配置する。ユーザー環境の Codex メモリには保存せず、プロジェクト内の git 管理を優先する。

セッション開始時、または規約が関係しそうなタスクに着手する前に [memory/MEMORY.md](memory/MEMORY.md) のインデックスを確認すること。新しい規約・フィードバック・ユーザー像が判明した場合は同ディレクトリにファイルを足し、`MEMORY.md` から 1 行リンクを張る。

## プロジェクト状況

**配布形態**: Blender **Extension**（`blender_manifest.toml`）。レガシーな `bl_info` は使わない。GitHub Release に zip を添付して配布する。

**対応バージョン**: Blender **5.1 以上** / Python **3.13**。Blender 5.0 は Python 3.11 で、対応するとツールチェーン全体を py311 構文に落とし CI マトリクスも 2 世代に割れるため足切りした。

**レイアウト**: Extension のソースルートは [src/silicone_casting/](src/silicone_casting/) で、`blender_manifest.toml` と `__init__.py` が同じ階層に並ぶ（`blender --command extension build --source-dir` がそのまま通る形）。

| レイヤ                                        | 責務                                                                       |
| --------------------------------------------- | -------------------------------------------------------------------------- |
| [core/](src/silicone_casting/core/)           | メッシュ処理の本体。`bpy.ops` に依存せず、シーンも depsgraph も要求しない  |
| [operators/](src/silicone_casting/operators/) | `core` を Blender オペレータとして公開する薄い層。入力検証と `self.report` |
| [ui/](src/silicone_casting/ui/)               | サイドバーパネルと `Scene.silicone_casting` に載る `PropertyGroup`         |

**サイドバーの構成**: 親パネル `SILCAST_PT_main` は中身を持たないヘッダーで、コントロールはその下のサブパネル 3 つが持つ（`SILCAST_PT_measurement` = Measurement、`SILCAST_PT_coloring` = Coloring、`SILCAST_PT_processing` = Processing。並び順は `bl_order`）。機能を足すときはどのセクションに載せるかを先に決める。

現状の実装は以下の 5 機能。造形機能の本体はこれから。

- **Solidify**（Processing）— `silicone_casting.solidify` で選択メッシュにアドオン専用の Solidify モディファイアを付与・更新し、`silicone_casting.apply_solidify` でそのモディファイアだけをメッシュに焼き込む。パラメータは壁厚（mm 入力）、方向反転、均一な厚み
- **体積計測**（Measurement）— `silicone_casting.measure_volume` が選択メッシュの体積をモディファイア込みのワールド実寸で合計し、mL で `Scene.silicone_casting` に保存する（ボタン押下時のスナップショット。閉じていないメッシュがあれば数値を出さずエラー）。`silicone_casting.copy_value` は渡された文字列をクリップボードへコピーするだけの汎用オペレータで、体積という概念を持たない
- **STL 出力**（Processing）— `silicone_casting.export_stl` がアクティブオブジェクト名を既定名にして保存先選択を開き、選択物のみ・モディファイア適用・シーン単位から mm への換算で STL を出力する（既定の単位スケールでは 1000 倍）。同じ Blender セッションでは、直前に出力したフォルダを次回の既定保存先にする
- **Boolean**（Processing）— `silicone_casting.add_boolean` がアクティブな選択メッシュへ、指定した別メッシュを Operand とする Boolean モディファイアを追加する。Difference / Union / Intersect と Manifold / Exact / Float を選択できる
- **混色シミュレータ**（Coloring）— 染料色を彩度100%固定のHue・Lightness、色スウォッチ付きカラーピッカー、Hex（sRGB）から入力し、染料別の校正濃度（滴/mL）を重みにした代表反射スペクトルの減法混色近似を行う。全染料による不透明化、Lightness 100%の白による自動淡色化、黒や茶色を含む他色の暗色化を反映し、名前付きプロファイルとして保存する。光学設定はTransparencyのみ。結果色とコピー可能なカラー値を常時表示し、専用マテリアルを選択メッシュへ適用できる

## ツーリング

- パッケージ・環境管理: `uv`（`uv.lock` をコミット済み）
- Python: **3.13 固定**（`requires-python = "==3.13.*"`）
- タスクランナー: `just`（[justfile](justfile)）。Windows でも `just` は Git Bash を呼ぶ設定なのでレシピは Unix シェル前提で書く
- 型チェッカー: `pyright` を `src/` に対し **strict**
- リンター/フォーマッター: `ruff`（line-length 88、ダブルクォート、isort + `combine-as-imports`、target py313）
- pre-commit: ruff、pyupgrade（`--py313-plus`）、docformatter、mdformat、codespell、`uv-lock`、pygrep checks

**`bpy` の型と実体を同じ環境に混ぜない**。テストは PyPI の実 `bpy` wheel を使い、型チェックは `fake-bpy-module` を使う。両者は同じ `bpy` パッケージ名を占有するため共存できない。`just type` は `uv run --isolated --with fake-bpy-module-5.1` の使い捨て環境で pyright を走らせることでこれを回避している。スタブは **最小サポート版 (5.1)** に固定してあり、5.2 限定 API を使うと型チェックで落ちる。

## コマンド

`just` レシピを使う（`uv run` をラップしているので venv が常に尊重される）:

| レシピ              | 内容                                                                               |
| ------------------- | ---------------------------------------------------------------------------------- |
| `just setup`        | 開発環境のセットアップ（`uv venv` + `uv sync` + `pre-commit install`）             |
| `just format`       | pre-commit フックを実行                                                            |
| `just test`         | `bpy` wheel 上で pytest（tier 1）                                                  |
| `just type`         | 隔離環境で pyright strict                                                          |
| `just run`          | format → test → type                                                               |
| `just validate`     | Extension マニフェストの検証                                                       |
| `just build`        | `dist/silicone_casting-<version>.zip` を生成                                       |
| `just install`      | build して実 Blender に install（有効化まで）                                      |
| `just dev`          | install して Blender を GUI 起動。手で機能を触るためのもの。MCP サーバーも起動する |
| `just blender-test` | install して統合チェック（tier 2）                                                 |
| `just fixtures`     | golden mesh の再生成                                                               |
| `just version`      | `blender_manifest.toml` の version を出力                                          |
| `just clean`        | 生成物の削除                                                                       |

実 Blender の場所は `BLENDER` 環境変数で上書きできる（`.env` でも可）。CI は setup-blender action が入れたものを指す。

細かい制御が必要な場合の直接呼び出し:

- 単一テスト: `uv run pytest tests/silicone_casting/core/test_solidify.py -v`
- キーワードフィルタ: `uv run pytest -v -k "<expr>"`
- マーカー選択: `uv run pytest -m golden`
- 単一の pre-commit フック: `uv run pre-commit run ruff -a`

## コーディング規約

### `core/` は `bpy.ops` を使わない

`bpy.ops.*` は window / context に依存し、background では `temp_override` を必要とし、ロケール依存の副作用も持つ。`core/` は `bmesh.ops` とデータ API だけで書く。モディファイアの結果が要る場合も、オペレータではなく depsgraph 評価（`obj.evaluated_get(depsgraph)` → `bpy.data.meshes.new_from_object`）で確定させる。この制約があるおかげで tier 1 のテストがシーンなしで動く。

### Blender の public surface

以下は Blender 側の UI・キーマップ・既存 `.blend` から参照されるため、実質的な公開 API として扱う。リファクタリングで勝手に変えない:

- オペレータの `bl_idname`（例: `silicone_casting.solidify`）
- `PropertyGroup` のプロパティ名と `Scene` への登録名（`Scene.silicone_casting`）
- パネルの `bl_idname` / `bl_category`

### private モジュール規約

`src/silicone_casting/` 配下のモジュールは **テストの有無** で `_` prefix の有無を決める:

- テストを書かない（真に private な実装）→ ファイル名に `_` prefix を付ける
- テストを書く / 書かれている → `_` prefix を **付けない**
- 外部公開は親 `__init__.py` の `__all__` で別軸として集約管理する

### カプセル化

- クラスの内部実装の詳細や属性は、基本的にすべて private（`_` prefix）にする
- 外部から参照する必要がある属性のみ public にする
- `__init__` で設定される属性は原則として private とする

### バージョンの単一の真実

`src/silicone_casting/blender_manifest.toml` の `version` が真値。`pyproject.toml` は `package = false` の開発ツール設定専用でバージョンを持たない。リリース CI がタグと manifest の一致を検証する。

## 索引

常時ロードを避けるため、詳細は skill にオフロードしてある:

- **Git 運用**（ブランチ / コミット命名、追跡対象を変更する前に読む）: `$git-ops`
- **エージェントチーム**（設計 → 実装/テスト → 統合/レビュー → ドキュメント）: `$agent-team`
- **並列化**: `$maximize-parallels`
- **テスト方針**（2 階層テスト、golden mesh、書かないテスト）: `$testing-strategy`
- **実機確認**（Blender MCP 経由で実 Blender を触る）: `$blender-mcp`
- **PR 作成**: `$github-pr` / **main 取り込み**: `$merge-main` / **worktree 隔離**: `$do-on-worktree`

## リリース

配布は GitHub Release に extension zip を添付する方式のみ（自前 extension repository は使わない）。

1. `blender_manifest.toml` の `version` を上げる（バージョンの単一の真実。ここ以外に書かない）
2. `CHANGELOG.md` の `## [Unreleased]` を `## [x.y.z] - YYYY-MM-DD` の節に移す。**見出し形式を崩さない**（リリース CI がこの節を抽出して Release 本文にする）
3. `just run` と `just blender-test` を通し、PR にして `main` にマージする
4. マージ後の `main` に `vx.y.z` タグを打って push する

以降は [.github/workflows/release.yml](.github/workflows/release.yml) が、タグと manifest の一致検証 → `extension build` → zip の再 validate → Release 作成まで行う。タグと manifest がずれていると失敗する。
