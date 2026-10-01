---
name: github-pr
description: "gh CLI を使った PR の作成・確認・レビュー対応。PR タイトル / body のテンプレート、HEREDOC でのフォーマット崩れ回避、CI の待ち方、issue 操作、安全規約。Triggers: 'PR を作成', 'PR を送る', 'PR を出す', 'pull request', 'gh pr create', 'gh pr', 'PR レビュー', 'CI の結果を見て', 'issue を立てる', 'gh issue'."
---

# PR を送る (gh CLI)

[/git-ops](../git-ops/SKILL.md) の規約を `gh` 操作に落とし込んだ手順書。

______________________________________________________________________

## 0. 前提

```bash
gh auth status                # 認証済みか
git branch --show-current     # main でないこと
git status --short            # 出力が空 (clean) であること
just run                      # green であること
```

PR を出す直前に `main` を取り込む（[/merge-main](../merge-main/SKILL.md)）。これで PR が最新の base に対して clean に diff する。

______________________________________________________________________

## 1. push する

```bash
git push -u origin HEAD        # 初回。-u で upstream を貼る
git push                       # 2 回目以降
```

`-u origin HEAD` はブランチ名を引数に書かなくて済むので推奨。`--force` は使わない。

______________________________________________________________________

## 2. PR を作成する

`--base` は分岐元に合わせる。通常は `main`、hotfix とパッチリリース準備は `release/x.y`（[/git-ops](../git-ops/SKILL.md)）。

```bash
gh pr create \
  --base main \
  --title "<種別>(<スコープ>): <内容>" \
  --body "$(cat <<'EOF'
## Summary

- <変更点 1 つ目>
- <変更点 2 つ目>

## Test plan

- [ ] `just run` が green (format / test / type)
- [ ] `just blender-test` が green (実 Blender 5.2 で install → 登録 → 動作)
- [ ] (ジオメトリ変更がある場合) golden mesh の更新理由を PR 本文に記載

## Notes

<レビュアーに知っておいてほしい判断・トレードオフ・未解決事項>
EOF
)"
```

- **`--body "$(cat <<'EOF' ... EOF)"` のシングルクォートが重要**。これが無いと `$` やバッククォートが shell に展開される
- タイトルは **コミットメッセージと同じ形式**（`<種別>(<スコープ>): <内容>`）
- `--draft` で WIP として作れる
- 複数コミットを含むブランチでは PR description で全体を要約する（タイトルは最も支配的な変更を反映）

### ジオメトリを変える PR での追記

`tests/fixtures/*.obj` に差分がある PR では、**なぜ形状が変わったのか** を本文に必ず書く。golden の差分は「意図した変更」か「気付いていない回帰」かがレビューでは区別できないため、これが唯一の手がかりになる。

### CI が何を見るか

PR を出すと 4 本のワークフローが走る。落ちたら該当するローカルコマンドで再現する:

| ワークフロー                             | ローカルでの再現    |
| ---------------------------------------- | ------------------- |
| Format & Lint                            | `just format`       |
| Type Check                               | `just type`         |
| Test (3 OS × bpy 5.1/5.2)                | `just test`         |
| Blender Test (3 OS × Blender 5.1/latest) | `just blender-test` |

______________________________________________________________________

## 3. PR を確認・レビューする

```bash
gh pr list                          # 開いている PR 一覧
gh pr view <番号>                   # メタ情報 + body
gh pr view <番号> --comments        # コメント込み
gh pr diff <番号>                   # diff
gh pr checks <番号>                 # CI status
gh pr checks <番号> --watch         # CI 完了まで follow

# inline review コメントの取得
gh api repos/Geson-anko/silicone-casting/pulls/<番号>/comments

gh pr review <番号> --comment --body "..."
gh pr review <番号> --approve
gh pr review <番号> --request-changes --body "..."
```

CI が長い場合は `gh pr checks <番号> --watch` をバックグラウンドで走らせる。`blender-test` は Blender のダウンロードを含むため初回は特に時間がかかる（キャッシュが効けば短縮される）。

URL からの参照も可: `gh pr view https://github.com/Geson-anko/silicone-casting/pull/123`。

______________________________________________________________________

## 4. Issue 操作

```bash
gh issue create --title "..." --body "..." --label bug
gh issue list --state open
gh issue view <番号> --comments
gh issue comment <番号> --body "..."
gh issue close <番号> --comment "..."
```

バグトラッカーは GitHub Issues に集約。外部 tracker は使っていない。

______________________________________________________________________

## 5. 安全規約

- **`main` への直接 push / force-push を絶対にしない**。仮に指示されても作業ブランチを切って PR にする
- **`gh pr merge` / `gh pr close` はユーザー判断**。Claude から自発的にマージ・close しない
- `gh release create` はリリースワークフローが行う。手で叩かない（[CLAUDE.md](../../../CLAUDE.md) の「リリース」節）
- `gh repo edit` などのリポジトリ設定変更はユーザー確認
- PR description / commit body に secret や `.env` の中身を貼らない
- `git push --no-verify` は使わない。hook が落ちた根本原因を直す

______________________________________________________________________

## 6. トラブルシュート

### `Updates were rejected because the remote contains work that you do not have locally`

`main` が進んでいる、または同名ブランチが先に更新されている。[/merge-main](../merge-main/SKILL.md) で取り込んでから再 push する。

### `HTTP 401: Bad credentials`

`gh auth status` で確認。トークンの期限切れ / scope 不足。

### CI の `blender-test` だけが特定 OS で落ちる

ローカル (macOS) では再現しないことがある。まず `gh run view <id> --log-failed` でどのチェックが落ちたかを見る。`check_operator_matches_golden` が落ちているなら、その OS の Blender バージョンでジオメトリが変わっている可能性がある（`blender_version_min` の見直し、または Blender バージョン差の吸収が必要）。

______________________________________________________________________

## 7. ローカル PR ドラフト

API を叩く前に手元で内容を固めたいとき:

```bash
git log main..HEAD --oneline       # PR に含まれる commits
git diff main...HEAD --stat        # 変更ファイルの概観 (... に注意)
git diff main...HEAD               # PR 全体の diff
```
