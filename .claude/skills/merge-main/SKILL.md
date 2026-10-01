---
name: merge-main
description: "作業の最後、PR を出す直前に main をリモート最新へ更新し作業ブランチへ取り込んでコンフリクトを解消する手順。rebase ではなく merge を使う方針、golden mesh / uv.lock のコンフリクト解消法、取り込み後の再検証。Triggers: 'PR を出す前', 'main を最新化', 'main をマージ', 'main に追従', 'merge main', 'コンフリクト解消', 'sync main', 'コンフリクトした'."
---

# PR の直前に main を取り込む

作業の最後、PR を出す **直前** に実行する。`origin/main` を作業ブランチへ merge し、conflict を解消してから PR を立てる。これにより PR が最新の base に対して clean に diff する。

hotfix など `release/x.y` を base にする PR では、以下の `main` を `release/x.y` に読み替える（`git fetch origin release/x.y` → `git merge origin/release/x.y`）。`main` は取り込まない。

[/git-ops](../git-ops/SKILL.md) と整合。**`main` への直接 commit / push はしない**。取り込みは作業ブランチ側で行う。

このリポジトリは **rebase ではなく merge** で main を取り込む（merge commit が残ることを許容し、自ブランチの commit hash を書き換えない）。

______________________________________________________________________

## 前提チェック

```bash
git status --short            # 出力が空であること (clean)
git branch --show-current     # main でないこと
```

未コミットの変更があるなら先に commit する。中途半端なら `git stash` で退避し、merge 後に `git stash pop`。

______________________________________________________________________

## 手順

### 1. リモート最新を取得

```bash
git fetch origin main
```

`git pull` ではなく `fetch` を使う（ローカル `main` を介さず `origin/main` を直接 merge 対象にする）。

### 2. main が進んでいるか確認

```bash
git log HEAD..origin/main --oneline
```

- **出力が空** → 取り込み不要。そのまま PR 作成へ
- **commit が並ぶ** → 次へ

### 3. merge

```bash
git merge origin/main
```

conflict が無ければ merge commit（または fast-forward）。message はデフォルトでよい。

### 4. conflict 解消

```bash
git status
git diff --name-only --diff-filter=U    # conflict した file 一覧
```

各 file の `<<<<<<<` / `=======` / `>>>>>>>` を解消する。

- **両者の意図を保持する**。main 側の変更を握り潰さない / 自分の変更も捨てない。`--ours` / `--theirs` で機械的に片方を採るのは、本当にもう一方が不要か確認してから
- 判断が割れる conflict（両方が同じ関数を別意図で書き換えた等）は **勝手に決めず、何が衝突しているか名指しでユーザーに確認する**（CLAUDE.md 開発原則 1）
- 解消したら `git add <file>`、全部済んだら `git merge --continue`
- 中断したくなったら `git merge --abort`

### このプロジェクトで conflict しやすいもの

| 対象                                 | 解消方法                                                                                                                                                                                                 |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uv.lock`                            | **手で潰さない**。`pyproject.toml` を先に解消してから `uv lock` を再実行し、その結果で上書きする                                                                                                         |
| `tests/fixtures/*.obj`               | **手で潰さない**。`src/` 側を先に解消してから `just fixtures` で再生成する。ただし **両側がジオメトリを変えている場合は再生成では解決しない** — 双方の意図が両立するか判断が要るので、ユーザーに確認する |
| `blender_manifest.toml` の `version` | リリース側 (`main`) の値を採る。作業ブランチでバージョンを上げていたなら、それはリリース手順の逸脱なので見直す                                                                                           |
| `CHANGELOG.md` の `## [Unreleased]`  | 両方のエントリを残す。順序は問わない                                                                                                                                                                     |
| `.claude/skills/` `.claude/agents/`  | 両者の意図を読んで統合する。片方を機械的に採らない                                                                                                                                                       |

### 5. 取り込み後の検証

テキスト conflict が無くても論理は壊れうる。**省略しない**。

```bash
just run           # format → test → type
just blender-test  # ジオメトリに関わる変更が両側にあった場合
```

`just fixtures` で再生成した差分が出たら commit に含める。テストが落ちたら、main 側の変更と自分の変更の **意味的な衝突** を疑う。

### 6. push して PR 作成

```bash
git push
```

以降は [/github-pr](../github-pr/SKILL.md) の `gh pr create` 手順へ。

______________________________________________________________________

## やってはいけないこと

- ローカル `main` に commit / push する
- conflict を `git checkout --theirs .` 等で一括上書きする
- conflict マーカーを残したまま `git add` / commit する
- 取り込み後に `just run` を省略する
- `git push --force`（merge による取り込みは履歴を書き換えないので force は不要）

______________________________________________________________________

## rebase を使いたくなったら

このリポジトリは **merge を既定** とする。`git pull --rebase` は自ブランチの commit hash を書き換え、push 済みブランチでは `--force-with-lease` が必要になる。共有 / レビュー中のブランチでは履歴の安定性を優先する。rebase が必要な特殊事情があるなら、理由をユーザーに確認してから行う。
