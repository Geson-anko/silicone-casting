---
name: feedback_surface_cut_and_separation
description: Surface Cut は1本の統合モディファイア、分離は評価済みコピーを元と同じコレクションへ出力して元を非表示にする
type: feedback
---

# Surface Cut と loose-part 分離の期待動作

- Surface Cut は、分割面の極薄ソリッド化と Manifold / Exact Difference を内部で連続実行する **1 本の `Surface Cut` モディファイア**として追加する。Operand に Solidify、Target に Boolean という別々のモディファイアを積む形ではない
- Surface Cut の厚みは mm で指定でき、最小値は 0.001 mm とする。作成後もモディファイアの Thickness 入力から変更できるようにする
- Surface Cut モディファイアは、作成後も Cutting Surface、Even Thickness、Solver（Manifold / Exact）を入力から変更できるようにする
- loose-part 分離は元オブジェクトを直接分割しない。全モディファイアを適用した評価済みコピーを作り、そのコピーを loose part ごとに分割する
- 元オブジェクトのメッシュとモディファイアは維持し、成功後は非表示にする
- 結果用コレクションは作らず、分割後のオブジェクトは元オブジェクトと同じコレクションにフラットに出力する
- 切断面は面数の削減より実形状の滑らかさを優先する。外周・内周の2ループでは、ループブリッジのように周方向へ四角面が並ぶ構成を好む
