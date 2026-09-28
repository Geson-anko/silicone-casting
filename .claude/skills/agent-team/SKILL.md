---
name: agent-team
description: "マルチエージェントによる 設計 → テスト/実装 → 統合/レビュー → ドキュメンテーション のフロー。5 エージェント (spec-planner / spec-driven-implementer / spec-test-author / code-quality-reviewer / docstring-author) の責務分離、フェーズごとの並列起動数、Agent tool での並列起動と SendMessage / orchestrator による連携規約。Triggers: 'エージェントチームで', 'agent team', 'マルチエージェントで進めて', 'チームで実装', '設計から実装まで通して', '仕様を固めて実装して'."
---

# エージェントチーム戦略

「エージェントチームで行う」という指示があり具体的な手順が示されていない場合、このサイクルに従う。利用可能なカスタムエージェントは [.claude/agents/](../../agents/) に定義されており、Agent tool の `subagent_type` に名前を渡して起動する。

各エージェントの責務は **厳密に分離** されており、互いの担当領域に踏み込まない。

| エージェント              | 書く対象                                    | 触ってはいけない対象                           |
| ------------------------- | ------------------------------------------- | ---------------------------------------------- |
| `spec-planner`            | 仕様書 `memory/specs/*.md`（コードなし）    | コード全般                                     |
| `spec-driven-implementer` | `src/silicone_casting/`                     | `tests/`（テストは絶対に編集しない）           |
| `spec-test-author`        | `tests/`（`fixtures/` 含む）                | `src/silicone_casting/`                        |
| `code-quality-reviewer`   | `src/` 内部（public API は不変）            | `tests/`、`bl_idname`、プロパティ名、`__all__` |
| `docstring-author`        | docstring・コメント・`docs/`・UI 説明文字列 | ロジック                                       |

______________________________________________________________________

## 実装サイクル

### フェーズ 1: 設計

**`spec-planner`** が要件を分析し、インターフェース設計と実装計画を `memory/specs/` に策定する。コードは書かない。

仕様が固まったら orchestrator が内容を確認し、モジュール / 機能単位に分割可能かを判断する。分割できるならフェーズ 2 の並列度がそのまま決まる。

### フェーズ 2: 実装 + テスト（並列）

**`spec-driven-implementer` と `spec-test-author` を並列起動**。仕様を共通の入力とし、実装者は `src/` を、テスト著者は `tests/` を書く。**テストは実装を見ずに仕様から書く**（実装に引きずられないことで、テストが仕様書として機能する）。

- 1 つの仕様に対して常に **2 エージェント並列**
- 仕様が独立した N 個のモジュールに分割可能なら、**2N エージェント並列**

### フェーズ 3: 実装修正ループ

テストが揃ったら `spec-driven-implementer` がテストを通すように `src/` **だけ** を修正する。**テストコードは絶対に触らない**。

テストが間違っていると思われる場合は、実装者が orchestrator に質問を返し、orchestrator が `spec-test-author` にリレーする。テストの修正可否を判定するのは `spec-test-author` の責務。

独立モジュールごとに `spec-driven-implementer` を並列起動できる。質問が必要なモジュールだけ `spec-test-author` を再起動する。

### フェーズ 4: テストクリア

`just run`（format → test → type）がパスし、ジオメトリに関わる変更なら `just blender-test` もパスしたら次へ。

### フェーズ 5: 統合 / リファクタリング

**`code-quality-reviewer`** が public API を一切変えずにリファクタリングする（重複排除・簡素化・命名・型精緻化）。`tests/` は触らない。各ステップで `just test` を回して green を保つ。

独立モジュールごとに並列起動できる。

### フェーズ 6: ドキュメンテーション

**`docstring-author`** が docstring・コメント・`docs/`・`CHANGELOG.md`・UI 説明文字列を整える。ロジックには触らない。

______________________________________________________________________

## 並列化（論理的に可能な最大数で並列実行する）

並列性の最大化はマルチエージェント運用の中心戦略。独立した担当は Agent tool 呼び出しを **1 メッセージに複数並べて** 同時に開始し、逐次にするのは依存関係がある場合だけとする。詳細は [/maximize-parallels](../maximize-parallels/SKILL.md)。

**並列化の前提**:

- 担当領域が disjoint（同じ file を 2 つのエージェントが同時に編集しない）
- 並列起動した結果は orchestrator が統合する。コンフリクトが起きたら逐次に切り替える
- メインの作業ツリーを汚したくない大きめのサブタスクは [/do-on-worktree](../do-on-worktree/SKILL.md) で隔離する

**このプロジェクトでの分割の目安**: `core/` のジオメトリ関数、`operators/` のオペレータ、`ui/` のパネル / プロパティは、それぞれ独立に実装・テストできることが多い。仕様がこの 3 層に分けて書かれていれば 3 モジュール = 6 エージェント並列が自然な単位。

______________________________________________________________________

## エージェント間通信のルール

サブエージェントの最終報告は orchestrator（親 Claude）にだけ返る。エージェント間の連絡は orchestrator が中継し、既に起動したエージェントに追加作業を頼むときは新規起動せず `SendMessage` でそのエージェントを続行させる（文脈が保たれる）。最終的な判断と統合は orchestrator が担う:

- 実装者からテスト著者への質問 → 実装者が orchestrator に質問を返し、orchestrator が `spec-test-author` に `SendMessage` でリレーする
- 仕様の解釈が分かれる場合 → orchestrator がユーザーに明確化を依頼するか、`spec-planner` を再起動して仕様を更新する
- リファクタリングで public API を変えたくなった場合 → `code-quality-reviewer` は実施せず改善案として報告。実施判断は orchestrator / ユーザー
- `docstring-author` がバグや設計上の問題を見つけた場合 → 直さず報告。orchestrator が `spec-driven-implementer` に回すか、仕様レベルの問題なら `spec-planner` に戻す

______________________________________________________________________

## サイクル完了後

1. `just run` と `just blender-test` が green であることを orchestrator 自身が確認する
2. [/git-ops](../git-ops/SKILL.md) の規約でコミットする
3. PR を出すなら [/merge-main](../merge-main/SKILL.md) → [/github-pr](../github-pr/SKILL.md)
4. 各エージェントが得た知見は `memory/agents/<name>/` に、プロジェクト全体の知見は `memory/` に記録されているか確認する
