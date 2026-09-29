# 単位の扱い

[README に戻る](../README.md)

## 📝 TL;DR

- 長さの入力欄は、シーンの長さの単位で表示されます。**単位を付けて入力** すると確実です
- 値は内部では **mm の実寸** で保存されます。Unit Scale を変えても実寸は変わりません
- 体積は **mL**、重量は **g** です
- STL は **mm の数値** で書き出されます

## 📏 長さの入力

次の欄は、シーンの長さの単位（**Scene Properties > Units** の **Length**）で表示されます。

- Solidify の **Thickness**
- Surface Cut の **Thickness** と **Boundary Extension**
- Air Vents の **Diameter**
- Registration Keys の寸法

入力するときは、`3 mm`、`0.5 cm` のように **単位を付けて** 入れると確実です。

値は、内部では mm の実寸として保存されています。

シーンの **Unit Scale** を後から変えても、実寸（mm）は変わりません。表示だけが、新しい単位に換算されます。

![Scene Properties の Units。Unit Scale と Length の欄](images/scene-units.png)

## 🧪 体積と重量

- 体積は mL（= cm³）、重量は g で表示します。
- Measure Volume は Unit Scale を考慮して、Blender 上に表示される実寸での体積を出します。

## 📤 STL

STL には、長さの単位の情報がありません。

そのため、このアドオンは **mm の数値** で書き出します。

STL の数値は「Blender の座標の値 × Unit Scale × 1000」です。これは、Blender 上に表示される実寸を mm で表した値になります。

既定の Unit Scale 1.0 では、座標の値の 1000 倍ですね。

詳しくは [STL 出力](export-stl.md) を見てください。
