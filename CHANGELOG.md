# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、バージョニングは
[Semantic Versioning](https://semver.org/lang/ja/) に従う。

リリースワークフローが `## [x.y.z] - YYYY-MM-DD` の節を抽出して GitHub Release の
本文にするため、**見出しの形式を崩さないこと**。

## [Unreleased]

### Added

- ダボ編集欄の折りたたみと、幅・高さ・先端縮小率に連動するテーパー角の入力に対応
- **Registration Keys** — 円柱ダボ・先細りダボ・角形キーの凸／凹を、3D ビューでクリック追加・選択編集・ドラッグ移動。距離型の寸法／隙間入力、面法線／固定軸への整列、輪郭プレビュー、削除、操作単位の標準 Undo／Redo に対応
- Mixture Calculator の密度・重量比・全パーツ行と、Coloring の全プロファイルを JSON で export/import。混合表は置換、カラーは既存リストへ追加し、不正ファイルは設定変更前に拒否
- **Inherit Collection Shape** — コレクション内（子コレクションを含む）のメッシュを Boolean の Collection オペランドで Union した形状を参照する空メッシュを作成
- Blender Extension としてのパッケージング（`blender_manifest.toml`、Blender 5.1 以上）
- **Solidify** オペレータ（`silicone_casting.solidify`）— 選択中のメッシュに、アドオン専用の Solidify モディファイアを付与する。既にあれば同じものを更新するので重ね掛けにならない
- **Apply** オペレータ（`silicone_casting.apply_solidify`）— そのモディファイアだけをメッシュに焼き込む。`bpy.ops` を使わず depsgraph 評価で行うため background でも動く
- 3D ビューサイドバーの **Silicone Casting** パネルと、壁厚（mm 入力。シーンの単位設定に依らない）・方向反転のプロパティ
- サイドバーの **Measurement**（計測）/ **Processing**（加工）の 2 セクション構成。それぞれ独立に折りたためる。壁厚・方向反転・Solidify・Apply は Processing に入る
- **Measure Volume** オペレータ（`silicone_casting.measure_volume`）— 選択中のメッシュの体積を合計し、mL（= cm³）で表示する。モディファイア込みのワールド実寸で測るので、Solidify を掛けた壁に必要な樹脂量がそのまま読める。閉じていないメッシュが混ざっている場合は数値を出さず、原因のオブジェクト名を挙げてエラーにする。結果はボタンを押した時点のスナップショットで、シーンを変えても自動更新はされない（押し直して更新する）
- 表示された体積をクリックしてクリップボードへコピーする機能（`silicone_casting.copy_value`）。単位も桁区切りも含まない数値だけが入るので、表計算にそのまま貼れる
- **Export STL** オペレータ（`silicone_casting.export_stl`）— アクティブオブジェクト名を既定のファイル名として保存先を選び、選択物のみ・モディファイア適用・1000 倍の固定設定で STL を出力する
- Measurementの横長ポップオーバーで開く **Mixture Calculator** を追加。パーツごとの体積とA/Bの密度・重量比から必要な体積／重量を算出する。名前検索、行の複数選択・並べ替え・選択小計・全体合計に対応し、入力と選択状態は `.blend` に保存される
- 2 階層のテスト（PyPI `bpy` wheel 上の pytest / 実 Blender へインストールしての統合チェック）と golden mesh 比較の基盤
- Windows / macOS / Linux での CI と、タグ push でのリリース自動化

### Changed

- Coloring の Base Volume 変更（Use Mixture Total を含む）に全染料の滴数を比例させ、配合濃度と結果色を維持

- Solidify / Surface Cut の厚み入力をシーン単位に対応する距離型へ変更し、既存の mm 保存値を維持。Lightness 入力を百分率型へ変更

- 機能と Blender 公開 API を維持したまま内部構造を整理し、オペレータ共通基盤を集約するとともに、配合計算・混色シミュレータ・サイドバーを凝集性に沿って分割

### Fixed

- Separate Loose Parts で、オブジェクト側に割り当てたマテリアルと空の材質枠を分離後も保持

[unreleased]: https://github.com/Geson-anko/silicone-casting/commits/main
