# STL 出力（Export STL）

[README に戻る](../README.md)

選択したメッシュを、3D プリント用の STL に書き出す。

![Processing パネルの一番下にある Export STL ボタン](images/export-stl-button.png)

![Export STL を押して開いたファイルブラウザの下部。赤枠のファイル名にアクティブなオブジェクトの名前 Mold.002.stl が入っている。青枠が保存を実行する Export STL ボタン](images/export-stl-browser.png)

- 既定のファイル名は **アクティブなオブジェクトの名前** + `.stl`（アクティブが選択中のメッシュでないときは、選択中のメッシュのうち 1 つの名前）。拡張子は省略しても付く
- 既定の保存先は、最初は保存済みの `.blend` のフォルダ。同じ Blender を終了するまでは、**直前に書き出したフォルダ** になる

## 📦 書き出される内容

- **選択中のオブジェクトだけ**
- **モディファイアを適用した形**（元のオブジェクトは変わらない）。レンダー表示（カメラのアイコン）をオフにしたモディファイアは含まない
- 長さは **mm**。既定の単位設定（Unit Scale 1.0）では座標を **1000 倍** し、Blender 上の 1 m を STL の 1000 にする。Unit Scale を変えても、Blender 上の実寸が mm で出る（[単位の扱い](units.md)）
- 選択したオブジェクトは、**すべて 1 つの STL ファイル** に入る

## 📂 パーツごとに書き出す

1 つずつ選択して、そのたびに **Export STL** を押す（保存先は前回と同じフォルダになる）。

> ⚠️ **注意**: [Separate Loose Parts](surface-cut.md#-separate-loose-parts) の直後は、全パーツが選択されている。そのまま押すと 1 ファイルに入る。

## ⚠️ 選択に混ざりやすいもの

**A** キーの全選択では、次のものも STL に混ざる。

- Boolean の **Operand** に使ったメッシュ
- Draw Surface Cut の切断面（`.Cutting Surface`）
- Air Vents の管（`.Air Vents`）

ダボの形のオブジェクトと、Separate Loose Parts で非表示になった元のオブジェクトは、選択されない。
