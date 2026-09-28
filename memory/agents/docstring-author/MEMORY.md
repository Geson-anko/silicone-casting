# MEMORY (docstring-author)

このエージェント固有のメモリ索引。1 メモリ 1 ファイル、ここには 1 行のリンクだけを置く。
プロジェクト全体で共有すべき知見は `memory/` 直下へ書き、`memory/MEMORY.md` に索引を足す。

## feedback

- [コメントは足りているなら足さない](feedback_comment_minimalism.md) — 過剰な加筆はしない。直すのは実装との食い違いと why 不在のコメント

## project

- [ドキュメントがドリフトする箇所](project_doc_drift_hotspots.md) — CLAUDE.md の現状記述 / public surface 例 / CHANGELOG Unreleased / golden 基盤
- [UI 文字列が届く経路を先に確認する](knowledge_ui_string_reachability.md) — 描画されないプロパティの description はツールチップにならない
- [責務分割時の docstring 監査](source_entropy_refactoring.md) — 移動先に契約説明を残し、互換ファサードは再公開だけを担うと明記する
