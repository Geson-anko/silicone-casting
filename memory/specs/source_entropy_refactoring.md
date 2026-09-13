# ソースエントロピー低減リファクタリング仕様

> 履歴資料: 2026-09-13 の追加指示により、この仕様の互換ファサード・旧 import 経路・内部配置の維持要件は置き換えられた。現在の方針は [型・ファクトリ・責務分割](../feedback_types_and_factories.md) と [AGENTS.md](../../AGENTS.md) を参照する。

## 01. 概要

### 目的

本仕様は、現行機能と Blender 公開契約を維持したまま、依存方向、重複、型の境界、巨大モジュールの責務混在を減らし、変更理由を局所化できるソース構造へ整理するためのものである。

対象ユーザーはアドオンの機能利用者ではなく、機能追加、障害修正、レビューを行う保守担当者である。利用者から見える振る舞いは変更しない。

着手時の基準状態は次のとおりである。

- tier 1 は 258 tests passed である。
- pyright strict は 0 errors である。
- 現行のオペレータ、RNA プロパティ、パネル、登録順、ジオメトリ出力を互換性の基準とする。

本仕様のキーワード MUST、SHOULD、MAY は RFC 2119 の強度で解釈する。

### ゴール

- 共通型が特定機能モジュールへ依存する逆向き依存を解消する。
- 選択メッシュ取得の同一実装を一か所に集約する。
- Blender RNA の文字列値に対する静的型境界を明示する。
- `ui/properties.py`、`ui/panel.py`、`operators/color_simulator.py` の責務を凝集性に沿って分離する。
- 現在の import 経路を互換ファサードとして維持する。
- 変更領域とテスト領域の所有権を排他的にし、実装とテストを並列化可能にする。

### 非目標

- 新機能、UI 改定、計算式変更、ジオメトリアルゴリズム変更は行わない。
- 行数を均等にするためだけの機械的分割は行わない。
- 無関係な `core`、golden mesh、マニフェスト、ドキュメントの整理は行わない。
- 将来用途を予測した汎用フレームワーク、基底クラス、サービスコンテナは導入しない。

## 02. 用語定義

- **Blender 公開契約**: `bl_idname`、`bl_label`、`bl_options`、パネルの `bl_idname`、`bl_parent_id`、`bl_category`、`bl_order`、RNA プロパティ名・型・既定値・範囲・更新挙動、`Scene.silicone_casting`、パッケージの `__all__`、クラス登録順を指す。
- **互換ファサード**: 既存の import 経路から同一のクラス、関数、定数を取得できるよう再公開する薄いモジュールを指す。業務判断、ループ、分岐、Blender データ変更を持たない。
- **RNA 列挙値**: Blender の `EnumProperty` が保存・受け渡しする文字列値を指す。Python の `Enum` インスタンスではない。
- **Literal 型別名**: 実行時の値を変換せず、許可される文字列集合だけを静的型検査へ伝える型境界を指す。
- **凝集性による分割**: 同じ変更理由を持つ宣言と処理を同じモジュールへ置き、異なる変更理由を別モジュールへ置く分割を指す。
- **選択メッシュの安定スナップショット**: `context.selected_objects` の現在の順序を保ったリストであり、メッシュ以外を除外し、選択情報が提供されない場合は空リストとなるものを指す。
- **造形ドメイン用語**: マスター、分割面、パーティングライン、抜き勾配、湯口、エア抜き、インターロック、収縮代は、本変更で扱うジオメトリまたは振る舞いがないため該当なし。

## 03. 要求仕様

### 3.1 共通オペレータ基盤

1. 実装は `OperatorReturn` を `solidify` の責務から切り離し、`operators` 配下の private な共通オペレータ基盤へ移動しなければならない（MUST）。
2. `solidify` 以外のモジュールが `OperatorReturn` を得るために `solidify` を import してはならない（MUST）。
3. 共通基盤は、Blender のオペレータ返却トークンである `RUNNING_MODAL`、`CANCELLED`、`FINISHED`、`PASS_THROUGH`、`INTERFACE` の集合を表す Literal 型別名を提供しなければならない（MUST）。
4. `solidify`、`export_stl`、`separate_loose_parts`、`color_simulator` に重複する選択メッシュ取得は、共通基盤の単一定義へ集約しなければならない（MUST）。
5. 共通の選択メッシュ取得は、選択情報なしを空として扱い、メッシュ以外を黙って除外し、入力順を保ち、新しいリストを返さなければならない（MUST）。
6. 共通基盤は `operators/_operator.py` の一モジュールに限定する（MUST）。型と選択取得はいずれも「Blender オペレータ境界で反復利用する最小プリミティブ」であり、別々の一宣言モジュールへ過剰分割しない。

### 3.2 Literal と Enum の判断

1. RNA の `direction`、`mode`、Boolean の `operation` と `solver`、オペレータ返却トークンは、実行時には Blender が管理する文字列のまま維持しなければならない（MUST）。
2. 前項の値集合は、各境界の Literal 型別名または Literal を使用する Protocol 属性で狭めなければならない（MUST）。
3. 本変更では Python の `Enum` または `StrEnum` を新設してはならない（MUST）。RNA との往復に値変換が必要になり、保存済み `.blend` と Blender API の文字列契約に対して追加の状態表現を生むためである。
4. Blender が所有する `EnumProperty` 自体は維持しなければならない（MUST）。Literal は静的型境界であり、RNA 定義の代替ではない。
5. 将来 Python Enum を採用してよいのは、プロジェクト自身が実行時の値の同一性と振る舞いを所有し、RNA やファイルへの直列化境界が明示される場合に限る（MAY）。この判断は本変更の範囲外とする。

### 3.3 プロパティの分割

1. 現在の `ui/properties.py` に混在する mixture、color、scene aggregation を、それぞれ一つの変更理由を持つ private モジュールへ分離しなければならない（MUST）。
2. mixture の行 PropertyGroup と選択状態に関する補助型は `ui/_mixture_properties.py` が所有しなければならない（MUST）。
3. colorant、color profile、色入力同期、派生色、プレビュー更新コールバックは `ui/_color_properties.py` が所有しなければならない（MUST）。
4. scene 全体の PropertyGroup、各機能の scene-level RNA 宣言、オブジェクト poll、mixture と color の子 PropertyGroup の集約は `ui/_scene_properties.py` が所有しなければならない（MUST）。
5. `ui/properties.py` は `SiliconeCastingMixturePart`、`SiliconeCastingColorant`、`SiliconeCastingColorProfile`、`SiliconeCastingProperties` を従来どおり取得できる互換ファサードにしなければならない（MUST）。
6. private モジュール間の依存は mixture/color から scene aggregation へ逆流してはならない（MUST）。scene aggregation だけが子 PropertyGroup 型を参照する。

### 3.4 パネルの分割

1. 現在の `ui/panel.py` に混在する mixture calculator、color simulator、sidebar panels を凝集性に沿って分離しなければならない（MUST）。
2. mixture の表計算表示補助、検索・小計処理、UIList、popover panel は `ui/_mixture_panel.py` が所有しなければならない（MUST）。
3. color profile/colorant の UIList、描画補助、color simulator popover panel は `ui/_color_panel.py` が所有しなければならない（MUST）。
4. メイン、Measurement、Coloring、Processing の sidebar panel は `ui/_sidebar_panels.py` が所有しなければならない（MUST）。
5. `ui/panel.py` は現在そこから取得されているパネル、UIList、描画・計算補助を従来の経路で取得できる互換ファサードにしなければならない（MUST）。既存テストが参照している private 補助も、このリファクタリングでは移行期間なしに削除しない。
6. 分割後も UI の表示順、ラベル、アイコン、popover 幅、開閉状態、operator 呼び出し、プロパティ参照は変えてはならない（MUST）。

### 3.5 混色オペレータの分割

1. 現在の `operators/color_simulator.py` に混在する RNA Protocol/計算 adapter、material 構築、operator classes を分離しなければならない（MUST）。
2. colorant/profile/settings の Protocol、active profile の解決、core の混色計算へ入力を適合させる処理は `operators/_color_adapter.py` が所有しなければならない（MUST）。
3. preview material の作成・更新、シェーダーノード設定、material 名に関する定数は `operators/_color_material.py` が所有しなければならない（MUST）。
4. profile/colorant の追加・削除、mixture volume の転記、選択メッシュへの material 適用を行う operator classes は `operators/_color_operators.py` が所有しなければならない（MUST）。
5. `operators/color_simulator.py` は現在 UI、properties、tests、`operators/__init__.py` が取得しているクラス、関数、Protocol、定数を従来の経路で取得できる互換ファサードにしなければならない（MUST）。
6. material datablock の共有、削除時の生存、ノード名、diffuse color、transparency、選択物の material slot 更新挙動を変えてはならない（MUST）。

### 3.6 制御構造、命名、分解度

1. 分岐や反復は、それ自体の行数を減らす目的では抽出してはならない（MUST NOT）。抽出後に独立した事前条件、事後条件、名前で説明できる責務を持つ場合だけ関数化する（SHOULD）。
2. UI の draw 処理は、表示上ひとまとまりの section または再利用される cell/row 単位で分ける（SHOULD）。一度しか使わない一行ラッパーは増やさない（MUST NOT）。
3. 一つの関数が状態の解決、計算、Blender datablock 変更、report の二つ以上を同時に担う場合は、今回定めた adapter/material/operator の境界へ分離する（SHOULD）。
4. 名前は `common`、`utils`、`helpers` のような無制限に責務が増える語を新規モジュール名に用いてはならない（MUST NOT）。
5. private 実装モジュールは直接の公開 API とせず、外部公開は既存ファサードと親 `__init__.py` に限定する（MUST）。

## 04. アーキテクチャ概要

データフローは次の方向に限定する。

1. UI panel は scene properties を読み、operator を起動する。
2. operator は RNA 文字列を Literal で狭めた Protocol 越しに読み、必要な core 計算または Blender data API を呼ぶ。
3. color adapter は PropertyGroup 相当の Protocol を core の色計算入力へ変換する。
4. color material 層は adapter の結果を Blender material へ反映する。
5. scene aggregation は mixture/color の子 PropertyGroup を束ねるが、子モジュールは scene aggregation を参照しない。
6. ファサードは private 実装から再公開するだけであり、private 実装はファサードを参照しない。

`core` は変更せず、引き続き `bpy.ops` 非依存とする。新しい private モジュールに循環 import があってはならない（MUST）。properties の更新コールバックで遅延 import が必要な場合も、依存先は責務を所有する private モジュールとし、循環をファサードで隠してはならない。

## 05. インターフェース仕様

### 既存公開インターフェース

- 新しい公開 API は追加しない。
- `silicone_casting.operators` と `silicone_casting.ui` の `__all__` は要素と意味を維持する。
- ルート登録対象のクラスオブジェクト、登録順、解除順を維持する。
- `ui.properties`、`ui.panel`、`operators.color_simulator` の既存 import 経路は維持する。
- Blender の operator return、`poll`、`execute`、`invoke` の結果および report の種類・条件を維持する。

### 新しい private インターフェース

- `operators/_operator.py` は `OperatorReturn` と、Context を受け取り選択メッシュの安定スナップショットを返す private 関数を提供する。
- properties の private 三モジュールは、子 PropertyGroup から scene aggregation への一方向参照で構成する。
- panel の private 三モジュールは、各表示領域のクラスと描画補助を所有し、`panel.py` がそれらを再公開する。
- color の private 三モジュールは adapter、material、operator の順に依存し、逆方向依存を持たない。

事前条件、事後条件、エラー型は既存の各仕様書に従う。本変更だけを理由に新しい例外型、例外メッセージ、入力拒否条件を追加してはならない（MUST NOT）。

## 06. データモデル

- `Scene.silicone_casting` 配下の全 RNA プロパティ名、RNA 型、単位、既定値、最小・最大値、enum item、保存可否、更新コールバックの観測可能な結果を維持する（MUST）。
- mixture part、color profile、colorant の PropertyGroup クラスと入れ子関係を維持する（MUST）。
- Blender 単位、mm 入力、mL 表示、色空間、滴/mL 校正の意味は変更しない（MUST）。
- `.blend` に保存済みの値を移行する処理は不要である。RNA 名も型も変えないため、データ移行は該当なし。

## 07. 振る舞い詳細

### シナリオ A: 選択メッシュ取得

- Given: Context がメッシュ、非メッシュを混在した選択順で返す。
- When: Solidify、STL export、loose-part separation、color material apply のいずれかが選択メッシュを取得する。
- Then: 元の順序を保ったメッシュだけのリストを得て、各機能の従来の `poll` と実行結果が維持される。

### シナリオ B: 互換ファサード

- Given: 既存コードが従来の `ui.properties`、`ui.panel`、`operators.color_simulator` から識別子を取得する。
- When: 分割後のパッケージを import して register する。
- Then: 従来と同じ責務のクラスまたは関数が取得され、全クラスが従来順で登録される。

### シナリオ C: RNA enum

- Given: Blender が `direction`、`mode`、Boolean operation/solver を文字列として PropertyGroup または Operator へ供給する。
- When: 実装が値を分岐または別関数へ渡す。
- Then: 実行時変換なしで従来の文字列が使われ、pyright は許可された値集合として検査する。

### シナリオ D: 色更新

- Given: 色プロファイルまたは色材の RNA プロパティが更新される。
- When: properties の更新コールバックが color adapter と material 層を呼ぶ。
- Then: 計算結果、preview material、UI 表示、選択メッシュへの適用結果が分割前と一致する。

## 08. エッジケースとエラー処理

- `context.selected_objects` が提供されない、または空の場合は空リストとして扱い、従来どおり operator が無効または取消となる（MUST）。
- 非メッシュだけが選択されている場合は空選択と同じに扱う（MUST）。
- 選択中に object が複数種類ある場合、非メッシュを報告なしで除外する現行挙動を維持する（MUST）。
- active object が選択メッシュに含まれない STL export の既定名決定を変えない（MUST）。
- active color profile がない場合、体積が正でない場合、material を適用できるメッシュがない場合の取消・report 条件を変えない（MUST）。
- color profile 削除後も使用中 material datablock が残る現行挙動を維持する（MUST）。
- register、unregister、ファイル load 後の一時選択状態リセットを分割によって重複登録してはならない（MUST NOT）。
- 不正な RNA enum 値を新たに Python Enum へ変換して例外化してはならない（MUST NOT）。入力制約は Blender RNA が所有する。
- 非多様体入力、開いたメッシュ、自己交差、ゼロ面積面、極端なスケール、非一様変換行列はジオメトリ処理を変更しないため、本仕様固有の追加処理は該当なし。既存仕様とテスト結果を維持する。

## 09. 受け入れ基準

- [ ] `OperatorReturn` の定義が一か所だけであり、どのモジュールも型取得のために `solidify` を import していない。
- [ ] 4 か所にあった選択メッシュ取得が一つの private 実装を共有している。
- [ ] RNA の direction、mode、operation、solver と operator return は Literal で狭められ、Python Enum は追加されていない。
- [ ] `ui/properties.py` は互換ファサードであり、PropertyGroup 定義、更新計算、分岐を持たない。
- [ ] `ui/panel.py` は互換ファサードであり、Panel/UIList 定義、draw ロジック、集計ロジックを持たない。
- [ ] `operators/color_simulator.py` は互換ファサードであり、Protocol 定義、material 構築、operator 実装を持たない。
- [ ] 各 private モジュールが本仕様で定めた一つの変更理由だけを持ち、循環 import がない。
- [ ] `bl_idname`、RNA プロパティ、panel metadata、`__all__`、登録順が既存契約テストを通過する。
- [ ] 着手時の 258 件を含む tier 1 全件が通過する。
- [ ] pyright strict が 0 errors である。
- [ ] `just run` が成功する。
- [ ] `just blender-test` が成功し、Extension の build、install、register、主要 operator の実行を確認できる。
- [ ] `src/silicone_casting/core/`、`tests/silicone_casting/core/`、`tests/fixtures/` に差分がない。
- [ ] golden mesh の再生成がない。

## 10. 実装計画と担当分割

4 領域の実装者と 4 領域のテスト著者を並列起動できる。各行の実装ファイルとテストファイルは他行と重複しない。全担当者は他担当者の変更を取り消してはならず、ファサード境界を共通仕様として統合する。

| 領域 | 実装所有ファイル | テスト所有ファイル | 依存・統合条件 |
| --- | --- | --- | --- |
| A: operator 基盤 | `operators/_operator.py`、`solidify.py`、`boolean_modifier.py`、`copy_value.py`、`export_stl.py`、`inherit_shape.py`、`measure_volume.py`、`mixture_parts.py`、`separate_loose_parts.py` | `tests/silicone_casting/operators/` 配下の `test_color_simulator.py` 以外 | D は合意済みの `_operator.py` インターフェースだけを利用する。A は color 系ファイルを編集しない。 |
| B: properties | `ui/properties.py`、`ui/_mixture_properties.py`、`ui/_color_properties.py`、`ui/_scene_properties.py` | `tests/silicone_casting/test_register.py` および必要な新規 `tests/silicone_casting/ui/test_properties.py` | C は従来の `ui.properties` 経路を利用できる。B は panel と operator を編集しない。 |
| C: panels | `ui/panel.py`、`ui/_mixture_panel.py`、`ui/_color_panel.py`、`ui/_sidebar_panels.py` | `tests/silicone_casting/ui/test_panel.py` | B/D のファサードだけを利用し、それらの所有ファイルを編集しない。 |
| D: color operator | `operators/color_simulator.py`、`operators/_color_adapter.py`、`operators/_color_material.py`、`operators/_color_operators.py` | `tests/silicone_casting/operators/test_color_simulator.py` | A の `_operator.py` を利用する。properties/panel は編集しない。 |

`src/silicone_casting/__init__.py`、`operators/__init__.py`、`ui/__init__.py` は互換ファサードによって原則変更不要とする。統合上どうしても変更が必要な場合は orchestrator だけが所有し、並列担当者は編集してはならない（MUST NOT）。

実装順は次のとおりとする。

1. A〜D の実装と対応テストを、同一ファイルへの書き込みがない状態で並列に行う。
2. orchestrator がファサードの再公開、import graph、登録クラスの同一性を統合確認する。
3. `just test` と `just type` を独立に並列実行する。
4. `just format` を単独実行し、書き換え後に `just run` を実行する。
5. `just blender-test` を他の Blender 操作と並列にせず実行する。
6. main の最新を merge し、検証を再実行してから PR を作成する。

### testing-strategy 準拠テスト計画

- tier 1 は実 `bpy` wheel を使い、`bpy`、`bmesh`、`mathutils` を mock しない（MUST）。
- private helper の実装詳細だけを固定するテストは追加しない（MUST NOT）。選択順、非メッシュ除外、空選択、operator 結果という公開振る舞いで共有化を検証する。
- Blender 公開契約は `api_contract` marker を付けた既存テストで固定する（MUST）。
- properties 分割は RNA 名・型・既定値・範囲・保存値を、panel 分割は panel metadata・順序・popover metadata を検証する。
- color 分割は profile/colorant 操作、色計算結果、material datablock、選択メッシュへの適用を実データ API で検証する。
- 型別名そのものの値や import 可能性だけを追試するテストは追加しない（MUST NOT）。Literal の妥当性は pyright strict で検証する。
- ジオメトリ出力を変更しないため、新規 golden mesh と既存 golden の再生成は行わない（MUST NOT）。
- tier 2 は build/install/register と実 Blender 上の既存 operator 動作を確認する。third-party package は追加しない。

## 11. 未解決事項

該当なし。本仕様ではファイル境界、互換性、型表現、担当所有権まで確定している。実装中に既存テストと現行挙動が矛盾した場合は、テストを実装へ合わせて変更せず、orchestrator が既存仕様書と Blender 公開契約から裁定する。

## 12. 将来の拡張余地

- 新しい operator で同じ選択メッシュ規則が必要になった場合は `_operator.py` を再利用してよい（MAY）。異なる選択規則を無理に引数化せず、意味が異なる場合は機能側に置く。
- color の計算入力が将来 RNA 以外へ広がる場合、adapter の Protocol を利用してよい（MAY）。本変更では抽象実装や fake は追加しない。
- private モジュールが将来直接テストを必要とするほど独立した公開振る舞いを持った場合は、プロジェクトの private モジュール規約に従い、ファイル名から `_` を外す判断を別仕様で行う。
