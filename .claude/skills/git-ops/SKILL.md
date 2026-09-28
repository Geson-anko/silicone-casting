---
name: git-ops
description: "このプロジェクトの git 戦略: ブランチ命名（種別/日付/内容）、コミットメッセージ形式（種別(スコープ): 内容）、main 直コミット禁止、コミット前の検証ゲート、golden mesh / uv.lock / dist の扱い。追跡対象のファイルを変更する可能性がある操作の前には必ず読む。Triggers: 'コミット', 'commit', 'ブランチを切る', 'branch', 'git add', 'git commit', 'git switch', 'stage', '変更を保存', 'ファイルを編集して', '実装して', 'リファクタして' — つまり tracked file に書き込む作業を始める前。"
---

# Git 運用

**この skill は、追跡対象のファイルを変更する可能性がある作業に着手する前に読む。** ブランチを切り忘れて `main` の上で実装を始めてしまうと、後からの巻き戻しが面倒になる。

______________________________________________________________________

## ブランチ

- `main`: 開発の主軸。**直接 commit しない**
- 作業ブランチ: `<種別>/<日付>/<内容>`
  - 種別: `feature` / `fix` / `refactor` / `docs` / `chore`
  - 日付: `YYYYMMDD`
  - 例: `feature/20260814/parting-surface`、`fix/20260814/solidify-sign`
- 作業ブランチは `main` から分岐する
- **`main` へのマージはユーザーが判断・実行する**。Claude から自発的に `gh pr merge` は叩かない

```bash
git branch --show-current                       # 今どこにいるか
git switch -c feature/$(date +%Y%m%d)/<slug> main
```

`main` の上にいることに気付いたら、実装を始める前にブランチを切る。既に `main` で編集してしまっていたら、`git switch -c <branch>` すれば未コミットの変更はそのまま新ブランチに移る。

______________________________________________________________________

## コミットメッセージ

`<種別>(<スコープ>): <内容>` の形式に従う。本文は日本語でよい。

- **種別**: `feat` / `fix` / `docs` / `style` / `refactor` / `test` / `chore`
- **スコープ**: `core` / `operators` / `ui` / `tests` / `manifest` / `ci` / `docs` / `claude`
  - より細かくしたいときは `core/shell` のようにモジュール名まで書く
- 例:
  - `feat(core): 分割面の自動生成を追加`
  - `fix(core/shell): solidify の thickness 符号を修正`
  - `test(tests): cube_shell の golden mesh を追加`
  - `chore(ci): blender-test を macOS arm64 に拡張`

**1 コミットに複数の関心事を混ぜない**。実装とテストとドキュメントは、同じ機能に属していても、レビューしやすさのために分けられるなら分ける。

______________________________________________________________________

## コミット前の検証ゲート

**コミット前に必ず `just run` を通す**（format → test → type）。

```bash
just run
```

ジオメトリの生成結果に影響しうる変更（`core/` や `operators/` の変更）なら、加えて実 Blender 側も確認する:

```bash
just blender-test
```

テストが落ちた状態でコミットしない。型チェックエラーを放置しない。`git commit --no-verify` は使わない（pre-commit が落ちた根本原因を直す）。

______________________________________________________________________

## このプロジェクト固有の追跡対象

| 対象                                         | 扱い                                                                                                                                         |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `uv.lock`                                    | **コミットする**。`pyproject.toml` を触ったら `uv lock` の差分も同じコミットに含める（pre-commit の `uv-lock` フックが検出する）             |
| `tests/fixtures/*.obj`                       | **コミットする**。`just fixtures` で再生成したら、なぜ形状が変わったのかをコミットメッセージに書く。理由を書けないなら、それは意図しない回帰 |
| `src/silicone_casting/blender_manifest.toml` | バージョンの単一の真実。上げるのはリリース時のみ（[CLAUDE.md](../../../CLAUDE.md) の「リリース」節）                                         |
| `dist/`                                      | gitignore 済み。ビルド成果物はコミットしない                                                                                                 |
| `.venv/` `__pycache__/`                      | gitignore 済み                                                                                                                               |
| `.claude/settings.local.json`                | gitignore 済み。共有したい権限は `.claude/settings.json` に書く                                                                              |

`.mcp.json` と `.claude/` 配下（`settings.local.json` と `worktrees/` を除く）は **追跡対象**。チームで共有する Claude Code 設定なので、変更したらコミットする。

______________________________________________________________________

## やってはいけないこと

- `main` に直接 commit / push する
- `git push --force` / `git push -f`（履歴破壊）。rebase 直後にどうしても必要なら `--force-with-lease` を使い、共有ブランチには使わない
- `git reset --hard` / `git clean -f` で未コミットの作業を捨てる（`.claude/settings.json` の `permissions.deny` でも禁止している）
- `git commit --no-verify` / `git push --no-verify` で hook を迂回する
- コンフリクトマーカー (`<<<<<<<`) が残ったまま `git add` する
- テストが赤いままコミットする

______________________________________________________________________

## 関連

- main の取り込み → [/merge-main](../merge-main/SKILL.md)
- PR 作成 → [/github-pr](../github-pr/SKILL.md)
- worktree 隔離 → [/do-on-worktree](../do-on-worktree/SKILL.md)
- リリース（タグ付け） → [CLAUDE.md](../../../CLAUDE.md) の「リリース」節
