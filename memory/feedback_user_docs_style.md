---
name: feedback_user_docs_style
description: 利用者向けドキュメント（README / docs/）は pamiq-core 風の簡潔な言い切り（常体）で書く。短い文、1 文ごとの改行、TL;DR、絵文字
type: feedback
---

利用者向けの README / `docs/` は、pamiq-core（<https://mlshukai.github.io/pamiq-core/>、ソースは <https://github.com/MLShukai/pamiq-core>）のような **簡潔な言い切り口調** で書く。日本語では常体（「〜する。」「〜になる。」「〜できる。」）にする。

- 敬体（〜します）やブログ風の語りかけ（〜しましょう、〜ですね、〜でしょう）は使わない
- 1 文を短くし、1 文ごとに改行する。話題が変わるところでは空行で段落を分け、GitHub 上でも詰まって見えないようにする（GitHub の Markdown は、ただの改行を画面上の改行にしない）
- 各ページの冒頭に `## 📝 TL;DR` を置き、要点を 3〜5 個の箇条書きにする
- 見出し・機能一覧・注意書きに絵文字を付ける（pamiq の「🎯 / ✨ / 🚀」や、絵文字付きの機能一覧のように）。付けすぎない
- 注意書きは `> ⚠️ **注意**: ...` の形の引用で書く。GitHub の `> [!WARNING]` 形式は、pre-commit の mdformat が `\[!WARNING\]` にエスケープして表示が壊れるので使わない

**Why:** 2026-09-29 に、最初の版（長い一文が続き、改行が少なく、絵文字もない説明調）について「私っぽくない」「改行が少なく、一文が長くて読みにくい」「絵文字も効果的に使うべき」と指摘された。いったんユーザーのブログ（geson-anko.github.io）寄りの語りかけ調に直したところ、「ブログ風ではなく pamiq-core 風の簡潔な言い切り口調が良い」と訂正された。形式は GitHub の Markdown のままでよく、MkDocs サイトは作らないことも確認済み。

**How to apply:** 利用者向けの文書を書くとき・直すときに適用する。開発者向けの `CLAUDE.md` / skill / 仕様書は対象外（[[feedback_planning_doc_language]]）。利用者向け文書を書くタイミングは [[feedback_defer_user_docs]] に従う。
