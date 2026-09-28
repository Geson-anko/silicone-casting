---
name: testing-strategy
description: "このプロジェクトの 2 階層テスト戦略: tier 1 (PyPI bpy wheel で pytest) と tier 2 (実 Blender に install して統合チェック)。golden mesh の作法、不変量ベースの検証、bpy/bmesh をモックしない方針、書いてはいけないテストの一覧、tests のレイアウトと import 順の制約。Triggers: 'テストを書く', 'test を追加', 'テスト戦略', 'golden mesh', 'fixture', 'どこにテストを置く', 'テストが落ちる', 'カバレッジ'."
---

# テスト戦略

______________________________________________________________________

## 2 階層構成

|                | tier 1                                                    | tier 2                                                        |
| -------------- | --------------------------------------------------------- | ------------------------------------------------------------- |
| コマンド       | `just test`                                               | `just blender-test`                                           |
| ランタイム     | PyPI の `bpy` wheel（本物の Blender ランタイム）          | 実 Blender インストール                                       |
| 置き場         | `tests/silicone_casting/`                                 | `tests/blender/run.py`                                        |
| フレームワーク | pytest                                                    | **なし**（素の `assert`）                                     |
| 何を担保するか | ジオメトリのロジック、オペレータの振る舞い、公開 API 契約 | packaging、extension のインストールと登録、実アプリ上での動作 |
| CI             | 3 OS × bpy 5.1 / 5.2                                      | 3 OS × Blender 5.1 / latest                                   |

**tier 1 が主戦場**。`bpy` wheel は fake ではなく本物のランタイムなので、`bmesh` もデータ API もシーンも実挙動で動く。速いので普段はこちらだけ回す。

**tier 2 は wheel では検証できないものだけ**。zip がビルドできるか、`extension install-file` が通るか、Blender が `bl_ext.user_default.silicone_casting` として解決するか、実 Blender 上でも同じジオメトリが出るか。Blender 同梱 Python に何もインストールせずに済むよう **third-party を import しない**（pytest も使わない）。これが 3 OS で最も壊れにくい。

______________________________________________________________________

## `bpy` / `bmesh` をモックしない

「動くテスト」ではなく「**実環境の振る舞いを保証するテスト**」を優先する。

**優先順位**:

1. **実 resource** — `bpy` wheel、実 `bmesh`、実シーン、`tmp_path` での実ファイル I/O。第一選択
2. **自前 ABC の fake** — このプロジェクトが自分で定義した抽象のみ
3. **`bpy` / `bmesh` / `mathutils` のモックは禁止** — ライブラリ表面をミラーした fake は「自分の仮定」をテストするだけで、Blender 側の変更を検出できない (Freeman & Pryce, *"Don't mock what you don't own"*)
4. **自分のコードの内部関数モック禁止** — リファクタで壊れるだけで何も保証しない

`core/` が `bpy.ops` 非依存であるおかげで、tier 1 はシーンもコンテキストも要求せずに済んでいる。この制約を崩すとテストが一気に脆くなる。

______________________________________________________________________

## ジオメトリの検証は 2 段構え

golden mesh だけに頼ると、テストが「変わっていない」ことしか言わなくなる。**仕様から解析的に導ける不変量を先に assert し**、その上で golden で正確な形状を固定する。

### 1. 不変量 (`tests/_helpers.py` の `mesh_invariants`)

| 項目                                              | 何を捕まえるか                                                    |
| ------------------------------------------------- | ----------------------------------------------------------------- |
| `vertex_count` / `edge_count` / `face_count`      | トポロジの規模                                                    |
| `boundary_edge_count` / `non_manifold_edge_count` | **印刷可能性**。`is_watertight` が False なら 3D プリントできない |
| `loose_part_count`                                | 分割型が期待どおりのピース数になっているか                        |
| `volume`                                          | 樹脂の使用量。解析的に計算できるので強い assert になる            |
| `bbox_min` / `bbox_max`                           | オフセット量・スケールの正しさ                                    |

期待値は **仕様から手計算で出す**。実行結果をコピペしない。

```python
# 2x2x2 の cube を 0.2 外側にオフセットすると 2.4 立方から 2.0 立方を抜いた体積になる
EXPECTED_VOLUME = 2.4**3 - 2.0**3
```

### 2. golden mesh (`assert_matches_golden`)

- `tests/fixtures/*.obj` にテキストで保存（binary `.blend` は Blender バージョンに縛られ diff も効かない）
- OBJ の読み書きは `tests/_helpers.py` の自前実装。`bpy.ops.wm.obj_export` はコンテキスト依存で出力形式も Blender 版で揺れるため使わない
- 比較は **頂点順・面順に依存しない正準化**（頂点を丸めた座標でソートし、面をそのランクの集合として比較）
- `@pytest.mark.golden` を付ける

### golden の再生成

```bash
just fixtures
```

**テストを通すために安易に再生成しない。** 形状が変わる意図があるときだけ再生成し、コミットメッセージと PR 本文に理由を書く。golden の差分は「意図した変更」か「気付いていない回帰」かがレビューでは区別できないため、それが唯一の手がかりになる。

新しい golden が要るなら `tests/generate_fixtures.py` に生成手順を追加する。tier 2 も同じ golden を読むので、tier 1 と tier 2 の期待値が自動的に一致する。

______________________________________________________________________

## 書いてはいけないテスト

既存テストにあれば削除候補として報告する:

- **継承の追試**: `assert issubclass(MyError, ValueError)`。型システムが既に保証している
- **import 可能性の追試**: import 直後の `assert X is not None`
- **定数 literal の追試**: `assert MIN_THICKNESS == 1e-6`。意味的不変条件（`MIN_THICKNESS > 0`）なら可
- **getter/setter のラウンドトリップ**: `obj.foo = x; assert obj.foo == x`
- **`__init__` でフィールドが設定されたことだけの確認**
- **framework / stdlib の動作追試**
- **例外メッセージの完全一致**: `pytest.raises(..., match="keyword")` 程度に留める。文言は仕様ではない
- **モックの戻り値をそのまま検証するだけのテスト**

### 例外: 公開 API 契約テスト

`bl_idname`、`Scene.silicone_casting` のプロパティ名、`blender_manifest.toml` のフィールドは、Blender の UI・キーマップ・既存 `.blend`・リリース CI が参照する契約。上記の原則の **唯一の例外** として固定する価値がある。

- `@pytest.mark.api_contract` を付ける
- コメントで「これは契約ピンであり振る舞いテストではない」と明示する
- 例: `tests/silicone_casting/test_manifest.py`

______________________________________________________________________

## レイアウトと約束事

```
tests/
├── conftest.py              # 共有 fixture (cube_mesh, empty_mesh)
├── _helpers.py              # bmesh の import を独占。mesh_invariants / golden 比較 / make_cube_mesh
├── generate_fixtures.py     # `just fixtures` の実体
├── fixtures/*.obj           # golden mesh
├── silicone_casting/        # src/silicone_casting/ と 1 対 1 ミラー
└── blender/run.py           # tier 2 (pytest から --ignore されている)
```

### `bmesh` の import は `_helpers.py` だけが持つ

PyPI の `bpy` wheel は `bmesh` / `mathutils` を **bpy の C 初期化時に** builtin モジュールとして登録する。そのため新しいインタプリタで `import bmesh` を単独で書くと `ModuleNotFoundError` になる（実 Blender 内では常に存在するので、この問題は wheel 環境に固有）。isort は `bmesh` を `bpy` より先に並べるので、放置すると壊れる。

`_helpers.py` が `# isort: off` ブロックで正しい順序を固定し、他のモジュールは `make_cube_mesh` などのヘルパ経由で使う。**新しいテストで直接 `import bmesh` と書かない。**

### その他

- テスト名は **仕様の一文** として読める形にする（`test_shell_of_a_closed_source_is_two_watertight_walls`）
- Arrange / Act / Assert が一目で分かる構造にする
- テスト内に分岐や計算ロジックを持ち込まない
- 新しいマーカーは `pyproject.toml` の `markers` に登録してから使う（`--strict-markers`）
- `--doctest-modules` が有効。`tests/` 配下のモジュールは import 時に副作用を持たせない
- **カバレッジは診断であり目標ではない**。数値目標を設けない。100% は赤信号（Fowler: *"high coverage numbers are too easy to reach with low quality testing"*）

______________________________________________________________________

## 実行

```bash
just test                                        # tier 1 全部
uv run pytest tests/silicone_casting/core -v     # 一部だけ
uv run pytest -m golden                          # golden だけ
uv run pytest -m "not golden"                    # golden 以外
just blender-test                                # tier 2 (build → install → 検証)
BLENDER=/path/to/blender just blender-test       # 別バージョンの Blender で
```

tier 2 は Blender のユーザー設定を書き換えるので、**複数同時に走らせない**（[/do-on-worktree](../do-on-worktree/SKILL.md) の共有 state の項を参照）。

実 Blender を対話的に触って挙動を確かめたい場合は [/blender-mcp](../blender-mcp/SKILL.md)。
