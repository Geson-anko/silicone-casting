---
name: knowledge-blender-geometry-api-facts
description: bpy wheel で実測した Blender API の挙動（to_mesh / calc_volume / 行列式によるワールド体積 / stale な matrix_world / ERROR report が RuntimeError になる件 / RNA イントロスペクション / 親子パネルの登録順 / 背景実行での clipboard と選択状態）と、実測して契約を固める手順
metadata:
  type: project
---

`bpy` の挙動を推測で仕様やテストに書くと、実装で必ず食い違う。以下は **実測して確定させた事実** であり、仕様書・テスト・実装のいずれからも前提にしてよい。初回の測定は 2026-08-14、PyPI `bpy` 5.2.0 wheel（`just test` と同じランタイム）。

## 実測のやり方

- 挙動: scratchpad に `.py` を置いて `uv run python <path>` で走らせる。`bpy` wheel がそのまま動くのでシーン・`bmesh`・depsgraph すべて本物
- 型: scratchpad に `pyrightconfig.json`（`typeCheckingMode: strict`、`reportMissingModuleSource: false`、`reportImplicitOverride: true`）を置き、想定コード形状を 1 ファイルに書いて `uv run --isolated --with fake-bpy-module-5.1 --with pyright pyright <dir>`。`src/` を汚さずに strict 通過を確認できる
- スタブの綴りを確かめたいときは `uv run --isolated --with fake-bpy-module-5.1 python -c "import sysconfig; ..."` で site-packages を求め、`bpy-stubs/types/__init__.pyi` を grep する（実体は無く `.pyi` だけなので `import bpy` はできない）

## 体積の測り方

- **ワールド体積 = ローカル体積 × `abs(matrix_world.to_3x3().determinant())`**。`BMesh.transform(matrix_world)` してから測るより速く、誤差も小さい（鏡像スケールの立方体で transform 方式 192.00000000000546 / det 方式 191.99999999999997、解析値 192）
- `BMesh.calc_volume()` は既定 `signed=False` で絶対値を返す。鏡像スケール（行列式が負）でも破綻しない。Solidify の外殻+内殻では符号付き体積が「外殻 − 内殻 = 壁の体積」になり、これが欲しい値そのもの
- **開いたメッシュの `calc_volume()` は無意味な値を返す**（面 1 枚外した 2×2×2 立方体で 6.67）。watertight 判定で門を作らないと嘘の数字が出る
- watertight 判定は「全辺の共有面数がちょうど 2」の 1 パスで済む（境界辺 <2 と非多様体辺 >2 を同時に弾ける）。辺 0 本のメッシュは条件を空虚に満たし体積 0.0
- 体積は float32 座標の丸めが 3 乗で効くため解析値と相対 1e-5 程度ずれる（[[bpy-typing-and-precision-gotchas]] と同じ話）。表示用に整形した**文字列一致**で assert すると誤差の議論を回避できる

## `to_mesh()` / depsgraph

- `Object.to_mesh()` は `bpy.data.meshes` にデータブロックを作らない（`users == 0` の一時メッシュ）。データブロックを残したくない読み取り経路ではこちらを使う。`bpy.data.meshes.new_from_object` はデータブロックを作る
- `to_mesh_clear()` は `to_mesh()` 無しで呼んでもエラーにならない → `finally` に無条件で置ける
- `to_mesh()` を 2 回続けて呼ぶと 1 回目の参照が死ぬ（`ReferenceError: StructRNA of type Mesh has been removed`）。一時メッシュへの参照を関数の外へ持ち出さない
- `context.evaluated_depsgraph_get()` だけでモディファイアの追加・値変更が反映される。**`Depsgraph.update()` は不要**。ただし呼ぶたびに評価済みデータブロックへの参照を無効化するので、1 パスで 1 回だけ取って共有する
- **`obj.scale` / `obj.location` を代入した直後の `obj.matrix_world` は stale。** `to_3x3().determinant()` が 1.0 を返す。`context.evaluated_depsgraph_get()` がフラッシュを行うので、depsgraph は transform を設定した **後** に取得する。危険なのは期待値を `matrix_world` から導出するテストで、**両辺が stale になり「通るのに何も検証していない」状態**になる。期待値は解析値（例: `8.0 * 2 * 3 * 4`）で書く
- `show_viewport = False` のモディファイアは評価結果に入らない → 「測る/焼くのはビューポートに評価された状態」を不変条件にできる
- 非メッシュへの `to_mesh()` は `RuntimeError: Object does not have geometry data`（カメラで確認）
- `hide_viewport = True` のオブジェクトは `context.selected_objects` に現れない（`select_set(True)` しても入らない）→ 隠れたオブジェクトの扱いを設計する必要がない
- 編集モード（`EDIT_MESH`）でも `evaluated_get` → `to_mesh` の経路が通り、オブジェクトモードと同じ体積を返す

## パネル

- **親パネルより先に子パネル（`bl_parent_id`）を登録すると `RuntimeError`**（`Registering panel class: parent 'X' for 'Y' not found`）。`_CLASSES` の順序が意味を持つ。逆に「親 → 子」なら `bl_order` が降順でも問題ない
- `draw` が docstring だけのパネル（ヘッダーのみの親）は正常に登録・描画できる。`draw` を持たないパネルは登録できない
- `bl_order` は 5.1 のスタブにも実体にもある。登録順に依存させずに並び順を決められる
- `Panel.bl_options` の Literal は `DEFAULT_CLOSED` / `HIDE_HEADER` / `INSTANCED` / `HEADER_LAYOUT_EXPAND` のみ
- `layout.operator()` の戻り値 `OperatorProperties` は `__getattr__` / `__setattr__` が `Any` で綴られているため、`props.value = "..."` は pyright strict を素通りする

## オペレータの戻り値と RNA のイントロスペクション（テストの assert が直接依存する）

- **`self.report({"ERROR"}, ...)` を呼んだオペレータは、`{"CANCELLED"}` を返しても `bpy.ops` 経由では戻り値が Python に届かず `RuntimeError: Error: <message>` を送出する。** `WARNING` では送出されない。`report` のレベル選択が、そのまま呼び出し側の制御フローを決める（`apply_solidify` は `WARNING` なので `{"CANCELLED"}` を assert できる）
  - テストは `pytest.raises(RuntimeError)` で受ける。`match=` は使わない（文言は仕様ではない）
  - **`poll` 失敗も同じ `RuntimeError` を出す**ため、`pytest.raises` だけでは「`execute` に到達しなかった実行」を誤って合格にする。Arrange で `poll` が真であることを assert するか、観測可能な副作用を先に仕込んで Act 後に変化を確認する
  - tier 2（pytest なし）では `try` / `except RuntimeError` で囲み、例外と副作用の両方を assert する
- **`Operator.bl_rna.properties` にはオペレータが宣言したプロパティが入っていない。** Blender 自身の `Operator` 構造体 RNA（`bl_idname` / `bl_options` / `layout` など 14 項目）に解決される。宣言したプロパティは `bpy.ops.<ns>.<op>.get_rna_type().properties` で読む。**`PropertyGroup.bl_rna.properties` は素直に宣言内容を返す** ので、両者は非対称
- **`bpy.types.Panel` は `bl_options` と `poll` を基底に持たない。** サブクラスが宣言しない限り `cls.bl_options` は `AttributeError`。テストは `getattr(cls, "bl_options", frozenset())` / `not hasattr(cls, "poll")` で書く
- オペレータ自身の `StringProperty` を `self.value` として **読む** と pyright strict が 2 件落ちる（`reportUnknownMemberType` / `reportUnknownVariableType`、`_PropertyDeferred` のジェネリック引数が未解決）。効くのは `value = cast(str, self.value)  # pyright: ignore[reportUnknownMemberType]` の 1 行だけで、`cast` 単独でも型注釈でも消えない。一方 `layout.operator()` の戻り値への **代入** は無警告で通る（読み書きで非対称）

## 背景実行の制約（テスト設計に直結）

- **`window_manager.clipboard` が no-op**。代入は例外を出さないが読み戻すと空文字列。tier 1 も tier 2（`blender --background`）もコピー内容を検証できない → 受け入れ基準は手動確認に落とすしかない
- 起動時シーンに選択済みの `Cube` が既に居る。「選択 0 個で `poll` が偽」を検証するテストは、先に全 deselect する fixture が必須（[[knowledge-operator-tests-in-background]] にも記載）
- `bl_options` に `INTERNAL` を含むオペレータも `dir(bpy.ops.<ns>)` に現れ、`bpy.ops` 経由で呼べる（登録確認のテストは書ける）

## 数値と書式

- `unit_settings.scale_length` は正にクランプされる（0 を代入すると 1e-9）。float32（0.001 → 0.0010000000474974513）。ゼロ除算ガードは書かない
- BU³ → mL（= cm³）は `volume * (scale_length * 100) ** 3`
- `f"{x:.2f}"` は指数表記も桁区切りも出さない（`1.2e9` → `"1200000000.00"`、`1e-7` → `"0.00"`）。スプレッドシート貼り付け用の文字列として安全

## 実 Blender での追加検証（2026-09-13 / 5.2.0）

- `hasattr(bpy.ops, "存在しない名前")` も真になる。名前空間の存在でアドオンのロードを判定しない。`addon_utils.check` の第 2 要素が実際のロード状態で、登録済みオペレータは `dir(bpy.ops.<namespace>)` で確認できる。
- STL の `use_scene_unit=True` は単位系 `NONE` では `scale_length` を反映しない。アドオンでは計測と同じ換算を行うため、`global_scale=1000*scale_length` と `use_scene_unit=False` を組み合わせる。
- 出力オペレータの `execute` 内だけで拡張子を補うと、保存画面が警告するパスと実際の出力先がずれる。`check` で先に補う。5.2 の上書き警告は赤いファイル名欄と「上書き」ボタンで表示された。
- 球形空洞・注入口・4 組のダボを持つ型では、親子を一緒に回転しただけで Exact Boolean の結果が非閉鎖になる例があった。元の姿勢では閉鎖しており、姿勢を戻すと復旧した。`use_self` / `use_hole_tolerant` では改善しなかった。正常な姿勢で評価結果をコピーしてから回転すると、閉鎖性と体積を維持できた。
- Boolean 後のメッシュが各辺 2 面でも、STL の同一座標を頂点として数えると重複辺が現れる場合がある。検証用モデルでは 0.00001 mm の頂点統合と微小な縮退辺の解消により、寸法と体積を保って単一の閉鎖・整合した向きの STL にできた。この値を一般の形状へ無条件に適用しない。

関連: [[prefer-explicit-trigger-over-live-recompute]]、[[bpy-typing-and-precision-gotchas]]
