# Boolean モディファイア追加機能 仕様

- 作成日: 2026-08-29
- ブランチ: `feature/20260829/boolean-modifier-tool`

## 目的

Blender 標準の Boolean モディファイアを、N パネルから対象・演算・Solver を
明示して追加できるようにする。モディファイアの適用や評価結果のメッシュ化は
行わない。

## 入力

- **追加先**: Object Mode でアクティブかつ選択中のメッシュオブジェクト
- **Operand**: `Scene.silicone_casting.boolean_operand` で指定する別の
  メッシュオブジェクト
- **Solver**: `Scene.silicone_casting.boolean_solver` で選ぶ次の 3 種類
  - `MANIFOLD`（Manifold）
  - `EXACT`（Exact、既定値）
  - `FLOAT`（Float）
- **Operation**: ボタンで選ぶ次の 3 種類
  - `DIFFERENCE`（Difference）
  - `UNION`（Union）
  - `INTERSECT`（Intersect）

## 振る舞い

- Processing パネルの Solidify と STL Export の間に Boolean セクションを置く
- `silicone_casting.add_boolean` を実行すると、追加先へ新しい Boolean
  モディファイアを 1 つ追加する
- 追加したモディファイアは `operand_type = "OBJECT"` とし、指定した Operand、
  Operation、Solver を設定する
- Solver が Manifold で、追加先か Operand の評価メッシュが非多様体なら Exact で追加し、INFO で知らせる。追加後のメッシュ編集には追従しない
- 同じ操作を繰り返した場合も既存モディファイアは更新せず、毎回 1 つ追加する
- 追加先以外の選択オブジェクト、Operand、既存モディファイアは変更しない
- 次の場合は `poll` を偽にしてボタンを無効化する
  - Object Mode ではない
  - アクティブオブジェクトが選択中のメッシュではない
  - Operand が未指定、メッシュではない、または追加先自身である
- オペレータは Blender の Undo 対象とする

## 非ゴール

- Boolean モディファイアの適用・削除・並び替え
- Collection Operand
- Solver 固有の詳細設定（Self Intersection、Hole Tolerant、Overlap Threshold）
- Operand の表示・選択状態の自動変更
- Blender 標準 Boolean の計算結果そのものを golden mesh で固定すること

## 検証

- tier 1 は実 `bpy` で、3 Operation と 3 Solver、Operand、追加先、繰り返し追加、
  `poll` 条件を検証する
- tier 2 はビルド・インストール後の実 Blender で、公開オペレータとプロパティが
  登録され、指定どおりの Boolean モディファイアが追加されることを検証する
