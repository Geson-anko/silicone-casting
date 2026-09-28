---
name: feedback_defer_user_docs
description: ユーザー向けドキュメント (README 本文 / docs/ / CONTRIBUTING) は機能が固まるまで書かない。README は最小スタブのまま
type: feedback
---

ユーザー向けドキュメントは **依頼されるまで書かない**。`README.md` は最小限のスタブ（タイトル + 1〜2 行）に留め、`docs/` や `CONTRIBUTING.md` を勝手に新設しない。

**Why:** 2026-08-14 のスケルトン構築時、README（英日 2 本）・`CONTRIBUTING.md`・`docs/usage.md`・`docs/RELEASE.md` を書いたところ「流石に readme や docs はまだ要らない、空っぽで OK」と差し戻された。機能が固まっていない段階のドキュメントは、実装が進むたびに書き直しが発生してコストだけが乗る。

**How to apply:** 開発者・エージェント向けの運用知識は `CLAUDE.md` と `.claude/skills/` に置く（こちらは常に必要）。CI が実際に読む `CHANGELOG.md` は機能インフラなので維持する。ユーザー向けの説明が要るタイミングは、機能が実際に使える状態になってからユーザーが判断する。

関連: [[feedback_planning_doc_language]]
