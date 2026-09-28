---
name: feedback-opus-style
description: Codex 由来のコードは Claude Opus のスタイルに寄せる。公開面（Blender UI / ファイル IO / .blend 保存）以外は破壊的変更可
metadata:
  type: feedback
---

2026-09-28 にユーザーから、Codex が書いたコードを「Opus のスタイル」に直すよう依頼された（PR #26）。適用した指針:

- 複数責務の長い関数・巨大なネストクロージャは、名前で意図が分かる関数/メソッドに分解する。早期 return
- `to_xxx` や getter が内部状態を書き換えるような隠れた副作用をなくし、データフローを引数と戻り値で見せる
- 閾値・反復回数は理由付きの `Final` 定数にする（値は変えない）
- 3 要素以上のタプル返却は NamedTuple / frozen dataclass にする
- public は Google スタイルの docstring。要約は docformatter（`--wrap-summaries=79`）に折られない長さに収める
- コメントは why だけを書く。推測で書いた理由は仕様書への参照に置き換える

**Why:** 公開面を守れば、Python API とモジュール構成の破壊的変更はユーザーが許可している（[[feedback-types-and-factories]]）。

**How to apply:** 守る対象は `bl_*`、RNA 定義、`.blend` に書く名前、JSON/STL の形式、report 文字列、生成ジオメトリ。`bl_description` がないオペレータでは docstring がツールチップになるので、UI 文字列として扱う。検証は、登録クラスの `bl_*` と RNA 定義のダンプ、およびジオメトリのダイジェストを main と突き合わせて行う。
