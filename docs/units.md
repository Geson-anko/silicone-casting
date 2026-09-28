# 単位の扱い

[README に戻る](../README.md)

## 長さの入力

Solidify の **Thickness**、Surface Cut の **Thickness** と **Boundary Extension**、Air Vents の **Diameter**、Registration Keys の寸法は、シーンの長さの単位（**Scene Properties > Units** の **Length**）で表示されます。

- 入力するときは `3 mm`、`0.5 cm` のように **単位を付けて** 入れると確実です。
- 値は内部では mm の実寸として保存されています。シーンの **Unit Scale** を後から変えても、実寸（mm）は変わらず、表示だけが新しい単位に換算されます。

![Scene Properties の Units。Unit Scale と Length の欄](images/scene-units.png)

## 体積と重量

- 体積は mL（= cm³）、重量は g で表示します。
- Measure Volume は Unit Scale を考慮して、Blender 上に表示される実寸での体積を出します。

## STL

STL には長さの単位の情報がないため、このアドオンは **mm の数値** で書き出します。STL の数値は「Blender の座標の値 × Unit Scale × 1000」で、Blender 上に表示される実寸を mm で表した値になります。既定の Unit Scale 1.0 では、座標の値の 1000 倍です。詳しくは [STL 出力](export-stl.md) を参照してください。
