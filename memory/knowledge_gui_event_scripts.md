---
name: knowledge-gui-event-scripts
description: tests/blender の GUI スクリプトは just blender-test に含まれず、Blender を自動終了しない。結果は $TMPDIR のファイルで読む
metadata:
  type: project
---

`just blender-test` が実行するのは `tests/blender/run.py` だけ。`draw_surface_cut` / `draw_surface_controls` / `snap_surface_cut` / `draw_air_vents` / `key_placement` / `export_file_dialog` は、`"$BLENDER" --enable-event-simulate --python <script>` で個別に起動する。

- `draw_surface_controls` 以外は Blender を閉じない。結果ファイル（`$TMPDIR/silcast-*-gui-result.txt`、空気孔は `silcast-air-vents-gui.json`）、またはダボの `[key GUI] PASSED:` 行を監視し、終わったらプロセスを kill する
- stdout だけを見て判定しない。曲面切断系は PASS をファイルにしか書かない
- Blender のユーザー設定を共有するので、1 本ずつ逐次に回す

2026-09-28 時点では、`draw_air_vents.py` の「native undo/redo restores the complete operation」が main でも失敗していた。空気孔を確定した後、Ctrl+Z 1 回では切削オブジェクトが消えない。
