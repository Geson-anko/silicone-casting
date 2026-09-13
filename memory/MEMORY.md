# MEMORY

このプロジェクトのメモリ索引。1 メモリ 1 ファイル、ここには 1 行のリンクだけを置く。詳細は各ファイルへ。

エージェント固有のメモリは [agents/](agents/) 配下にある。

## user

- [ユーザー像](user_role.md) — 日本語でやり取り。Blender / 3D プリント / シリコーン造形の実務者

## project

- [プロジェクトの目的](project_purpose.md) — シリコーン造形用の樹脂型を Blender で生成し 3D プリントする
- [既存プロトタイプアドオン](project_prototype_addons.md) — repo 外にある mold_cut / mold_split。次フェーズの移植元
- [format ゲートは untracked を見ない](project_format_gate_skips_untracked.md) — 新規ファイルは commit するまで違反が出ない。ローカル緑・CI 赤の原因
- [Blender ジオメトリ API の実測事実](knowledge_blender_geometry_api_facts.md) — to_mesh / calc_volume / stale な matrix_world / ERROR report が RuntimeError になる件 / RNA イントロスペクション / パネル登録順

## feedback

- [寸法入力の単位型](feedback_distance_inputs.md) — 寸法・隙間は `(mm)` 固定数値ではなく DISTANCE / LENGTH を使う

- [計画・仕様書の言語](feedback_planning_doc_language.md) — 仕様書・AGENTS.md・skill は日本語で書く
- [ユーザー向けドキュメントは後回し](feedback_defer_user_docs.md) — README / docs は依頼されるまで書かない
- [モディファイア出力に golden を作らない](feedback_no_golden_for_modifier_output.md) — Blender 標準モディファイアの結果は不変量だけで検証する
- [常時ライブ更新よりボタン起動](feedback_prefer_explicit_trigger.md) — 計測系は「押して計算 → Scene に保存 → draw は表示だけ」。テスト可能性が跳ね上がる
- [Mixture CalculatorのUI](feedback_mixture_calculator_ui.md) — Nパネル横の広いポップオーバーで開き、Enabled以外の行選択チェックボックスは使わない
- [混色シミュレータのUIと校正値](feedback_color_simulator_ui.md) — 彩度100%固定のHue・Lightness入力、全染料による不透明化、白による自動淡色化、コピー可能な結果色を扱う
- [Surface Cut と loose-part 分離](feedback_surface_cut_and_separation.md) — 1本の統合モディファイアと、評価済みコピーを元と同じコレクションへフラットに出力する分離フロー

## specs

- [空気孔の自由描画](specs/air_vents.md) — 最初の面で決めた平面上に丸い管を描き、選択メッシュ群へ共通の Boolean 切削を追加する

- [切断面のダボ・噛み合わせ](specs/registration_keys.md) — 3 種の凸／凹、クリアランス、面への配置とプレビュー・確定

- [自由描画による曲面切断](specs/drawn_surface_cut.md) — 共通のループ入力から自動補間した切断面を生成し、内部の曲がりを編集できる

- [Solidify 機能](specs/solidify.md) — 選択メッシュへの固定名 Solidify モディファイアの付与・更新と、bpy.ops 非依存の適用
- [体積計測 / サイドバーのセクション分け](specs/volume_measurement.md) — 親パネル + サブパネル 2 つへの再編と、ボタンで選択メッシュの合計体積を計測し mL で表示・クリックでコピーする機能
- [手入力式シリコーン配合計算表](specs/mixture_calculator.md) — 体積・密度・重量比からA/Bの体積と重量を算出し、行選択・小計・`.blend` 保存に対応
- [シリコーン混色シミュレータ](specs/color_mixing_simulator.md) — 染料別の滴/mL校正による混色、名前付きプロファイル、結果色表示と選択物への適用
- [STL 出力機能](specs/stl_export.md) — 選択物のみ・モディファイア適用・mm への換算で、オブジェクト名を既定名にする保存フロー
- [Boolean モディファイア追加機能](specs/boolean_modifier.md) — アクティブメッシュへ指定した Operand・Operation・Solver の Boolean モディファイアを追加する
- [ソースエントロピー低減リファクタリング](specs/source_entropy_refactoring.md) — 機能・公開契約を維持したオペレータ共通基盤と配合・混色・サイドバーの責務分割

## reference

- [Blender 実行環境](reference_blender_env.md) — ローカル Blender 5.2、Blender↔Python 対応、bpy wheel の OS 対応
