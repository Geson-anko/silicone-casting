# 単位の扱い

[README に戻る](../README.md)

## 📝 TL;DR

- 長さの入力欄は、シーンの長さの単位で表示される。**単位を付けて入力** すると確実
- 値は内部では **mm の実寸** で保存される。Unit Scale を変えても実寸は変わらない
- 体積は **mL**、重量は **g**
- STL は **mm の数値** で書き出される

## 📏 長さの入力

次の欄は、シーンの長さの単位（**Scene Properties > Units** の **Length**）で表示される。

- Solidify の **Thickness**
- Surface Cut の **Thickness** と **Boundary Extension**
- Air Vents の **Diameter**
- Registration Keys の寸法

入力するときは、`3 mm`、`0.5 cm` のように **単位を付けて** 入れると確実。

値は、内部では mm の実寸として保存されている。

シーンの **Unit Scale** を後から変えても、実寸（mm）は変わらない。表示だけが新しい単位に換算される。

![Scene Properties の Units。Unit Scale と Length の欄](images/scene-units.png)

## 🧪 体積と重量

- 体積は mL（= cm³）、重量は g で表示する。
- Measure Volume は Unit Scale を考慮し、Blender 上に表示される実寸での体積を出す。

## 📤 STL

STL には、長さの単位の情報がない。

そのため、このアドオンは **mm の数値** で書き出す。

STL の数値は「Blender の座標の値 × Unit Scale × 1000」で、Blender 上に表示される実寸を mm で表した値になる。

既定の Unit Scale 1.0 では、座標の値の 1000 倍。

詳しくは [STL 出力](export-stl.md) を参照。
