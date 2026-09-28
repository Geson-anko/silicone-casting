---
name: feedback_planning_doc_language
description: 仕様書・計画・CLAUDE.md・skill・Claude エージェント定義の本文は日本語で書く
type: feedback
---

仕様書・実装計画・`CLAUDE.md`・`.claude/skills/*/SKILL.md`・`.claude/agents/*.md` の指示本文、コミットメッセージの内容部、PR 本文、`README.ja.md`、`docs/` は **日本語** で書く。

コードそのもの（識別子・docstring・コード内コメント）と `README.md` は **英語**。skill / agent の frontmatter `description` も英語混じりでよい（トリガー語として日本語のフレーズも併記する）。

**Why:** ユーザーは日本語でやり取りしており、参照元の 2 リポジトリ (MLShukai/vrcpilot, MLShukai/ResoniteIO) も同じ使い分けを採っている。ドキュメントを英語で書くとユーザー自身のレビューコストが上がる一方、コードは Blender / Python の慣習に合わせる方が読みやすい。

**How to apply:** 新しいドキュメントを書くときは、それが「人間が読む説明」なら日本語、「コードの一部」なら英語、と判断する。skill の `description` にはユーザーが実際に打ちそうな日本語フレーズを Triggers として入れる。
