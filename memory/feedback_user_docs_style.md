---
name: feedback_user_docs_style
description: 利用者向けドキュメント（README / docs/）はユーザーのブログ寄りの文体で書く。短い文、1 文ごとの改行、TL;DR、絵文字
type: feedback
---

利用者向けの README / `docs/` は、ユーザー本人のブログ（<https://geson-anko.github.io>、ソースは <https://github.com/Geson-anko/Geson-anko.github.io> の `content/blog/`）の文体に寄せる。見出しや機能一覧の絵文字は pamiq-core（<https://mlshukai.github.io/pamiq-core/>）を参考にする。

- 1 文を短くし、1 文ごとに改行する。話題が変わるところでは空行で段落を分け、GitHub 上でも詰まって見えないようにする（GitHub の Markdown は、ただの改行を画面上の改行にしない）
- 各ページの冒頭に `## TL;DR` を置き、要点を 3〜5 個の箇条書きにする
- 「〜しましょう」「〜ですね」「〜でしょう」のように語りかけ、要点は **太字** にする。ブログ冒頭の「みなさんこんにちは」のような挨拶は入れない
- 見出し・要点・注意書きに絵文字を付ける（例: 🚀 はじめに、⚠️ 注意、💡 ヒント）。付けすぎて読みにくくしない
- 注意書きは `> ⚠️ **注意**: ...` の形の引用で書く。GitHub の `> [!WARNING]` 形式は、pre-commit の mdformat が `\[!WARNING\]` にエスケープして表示が壊れるので使わない

**Why:** 2026-09-29、最初の版（長い一文が続き、改行が少なく、絵文字もない説明調）に対して、「私っぽくない」「改行が少なく、一文が長くて読みにくい」「絵文字も効果的に使うべき」と指摘された。ドキュメントの形式は GitHub の Markdown のままでよく、MkDocs サイトは作らないと確認済み。

**How to apply:** 利用者向けの文書を書くとき・直すときに適用する。開発者向けの `CLAUDE.md` / skill / 仕様書は対象外（[[feedback_planning_doc_language]]）。利用者向け文書を書くタイミングは [[feedback_defer_user_docs]] に従う。
