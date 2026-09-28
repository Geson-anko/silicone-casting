---
name: doc-drift-hotspots
description: 機能の追加・削除のたびにドリフトする箇所（CLAUDE.md の現状記述と public surface 例、CHANGELOG の Unreleased、golden 基盤の記述）
metadata:
  type: project
---

機能が入れ替わるたびに古くなる箇所が決まっている。ドキュメント整備の依頼では毎回
ここを確認する。

- **CLAUDE.md「プロジェクト状況」末尾の一文**（レイヤ表の直後）— 「現状の実装は〜」。
  実装中の機能を名指ししているので、機能が入れ替わると必ずずれる
- **CLAUDE.md「プロジェクト状況」のサイドバー構成記述** — 2026-08-15 の体積計測で追記した
  「親パネル + Measurement / Processing のサブパネル」。パネルを増やす・機能をセクション間で
  移すとずれる。機能一覧と構成の 2 段構えなので、機能追加時は両方を見る
- **CLAUDE.md「Blender の public surface」の `bl_idname` の例** — 削除済みオペレータが
  例として残りやすい
- **CLAUDE.md「コマンド」の単一テスト実行例** — テストファイル名を直書きしている
- **CHANGELOG.md の `## [Unreleased]`** — 未リリースなので、削除された機能は
  `### Removed` を足すのではなく `### Added` の記述ごと差し替えるのが正しい。
  同じ理由で、未リリース節では「〜に分割した」「〜へ移した」という **変更履歴的な
  書き方をしない**（読者はその旧状態を一度も見ていない）。結果としての構造を述べる
- **golden mesh 基盤** — `tests/_helpers.py` / `tests/generate_fixtures.py` /
  `justfile` の `fixtures` / pytest の `golden` マーカーは残っているが、
  `tests/fixtures/` は空（ディレクトリ自体が無い）。Blender 標準モディファイアの
  出力に golden は作らない方針なので、この状態は正常。**具体的な fixture 名を例に
  出さない**こと

**Why:** 2026-08-14 の Solidify 機能着地時、`make_shell` 削除の取りこぼしが上記の
複数箇所に残っていた。同じ形の取りこぼしが今後も起きる。

**How to apply:** `git log --oneline main..HEAD` で削除された識別子を拾い、
`grep -rn "<識別子>" --include=*.md --include=*.py` でリポジトリ全体を掃く。
`memory/specs/` と `.claude/skills/` のヒットは対象外（前者は spec-planner の成果物、
後者はコミットメッセージの例示）。

関連: [[comment-minimalism]]
