---
name: blender-mcp
description: "Blender MCP 経由で実 Blender を触りながら機能を確かめる手順。just dev で GUI 起動 + MCP サーバー起動、MCP のセットアップ (.mcp.json / BlenderMCP アドオン)、コード変更のたびに just dev を再実行する必要、同時 1 インスタンス制約、自動テストとの使い分け。Triggers: 'just dev', 'blender mcp', 'Blender で確認', '実機で見たい', '実際に動かして', 'Blender を起動', 'スクリーンショット', 'ビューポート', '目視で確認', 'UI を確認'."
---

# Blender MCP で実機を触る

自動テスト（[/testing-strategy](../testing-strategy/SKILL.md)）が担保できないもの — **UI の見た目、操作感、生成ジオメトリの視覚的な妥当性** — を確かめるための手順。

______________________________________________________________________

## 自動テストとの使い分け

| 確かめたいこと                                     | 手段                                                       |
| -------------------------------------------------- | ---------------------------------------------------------- |
| ジオメトリが仕様どおりか                           | tier 1 (`just test`)。数値で assert できるものは必ずこちら |
| install / 登録 / 実 Blender 上の動作               | tier 2 (`just blender-test`)                               |
| **パネルの配置・ラベル・並び順が意図どおりか**     | **MCP**                                                    |
| **生成された型が「造形として妥当」に見えるか**     | **MCP**                                                    |
| **操作の流れが自然か（選択 → パラメータ → 実行）** | **MCP**                                                    |
| **想定外の形状が出たときの原因調査**               | **MCP**                                                    |

MCP で見つけた問題は、**再現する自動テストに落としてから直す**。MCP での目視確認は探索と最終確認のためのもので、回帰検出の手段にはならない。

______________________________________________________________________

## セットアップ

### 1. MCP サーバー（repo 側）

[.mcp.json](../../../.mcp.json) にコミット済み:

```json
{ "mcpServers": { "blender": { "type": "stdio", "command": "uvx", "args": ["blender-mcp"], "env": {} } } }
```

`.claude/settings.json` の `enabledMcpjsonServers: ["blender"]` により、サーバー自体は承認プロンプトなしで有効になる。個々の MCP ツール呼び出しは allow に入れていないので、実行時に承認を求められる。`uvx` が PATH に必要（`uv` を入れてあれば入っている）。

### 2. BlenderMCP アドオン（Blender 側 / マシンごとに 1 回）

1. <https://github.com/ahujasid/blender-mcp> から `addon.py` を取得
2. Blender: **Edit → Preferences → Add-ons → Install** で `addon.py` を選択
3. **Interface: Blender MCP** を有効化

このアドオンは開発対象の `silicone_casting` とは無関係な別物。`blender --command extension` の出力に `BlenderMCP addon registered` が混ざるのはこれが原因で、無害。

### 3. 接続

`just dev` が Blender を GUI 起動し、BlenderMCP アドオンを有効化して MCP サーバーまで立ち上げる（[tools/launch_dev.py](../../../tools/launch_dev.py)）。**N パネルにある BlenderMCP の接続ボタンを手で押す必要はない。**

MCP は background モードでは使えないので、`just dev` は必ず GUI で起動する。Claude Code 側は `.mcp.json` 反映のため一度再起動しておくこと。

______________________________________________________________________

## 開発中の実機確認ループ

```bash
just dev
```

これだけ。`build` → `install-file --enable` → GUI 起動 → MCP サーバー起動までを一息でやる。

**コードを変えたら `just dev` を再実行する。** Blender は起動中に差し替えた extension のモジュールを再読込しないため、Blender を立ち上げ直さないと古いコードのまま動く。ここを飛ばして「変更が反映されない」と悩むのが最も多い失敗。

`just dev` は Blender が終了するまでブロックするので、**Claude から実行するときは Bash の `run_in_background` で走らせる**（そうしないとセッションが固まるうえ、MCP サーバーも操作できない）。

`just dev` はシーンにもウィンドウレイアウトにもユーザー設定にも触らない。素の Blender にアドオンが載っているだけの状態で立ち上がるので、パネルは **N** キーでサイドバーを開いて **Silicone Casting** タブを選ぶ。

### 確認の流れ

1. シーンをリセットして既知の状態から始める（既存オブジェクトが残っていると原因の切り分けができない）
2. マスターとなるメッシュを 1 つ置く
3. サイドバーの **Silicone Casting** タブからパラメータを設定してオペレータを実行する
4. 結果を **スクリーンショットで確認** する。ワイヤーフレーム表示にすると内部構造が見える
5. 数値も取る（頂点数・寸法・体積）。目視だけだと「それらしく見えるが数値が違う」を見逃す

______________________________________________________________________

## 制約と注意

- **MCP サーバーは同時 1 インスタンスのみ**。複数の Claude セッション / worktree から同時に使わない（[/do-on-worktree](../do-on-worktree/SKILL.md) の共有 state の項）
- **`just blender-test` と同時に使わない**。tier 2 は `extension install-file` で Blender のユーザー設定を書き換えるため、MCP 接続中の Blender と食い違う
- **MCP 経由でシーンを壊しても構わない前提で使う**。保存したい作業ファイルを開いた状態で実験しない
- MCP から実行した Python は **Blender のユーザー設定やシーンを永続的に変えうる**。破壊的な操作をする前に、何が起きるかを一言説明してからにする
- Blender のロケールが日本語だと、`primitive_cube_add` が作るオブジェクト名が `立方体` になる。名前でオブジェクトを引くコードを書くときは注意（tier 2 の `run.py` は `source.name` から組み立てることで回避している）

______________________________________________________________________

## うまくいかないとき

| 症状                           | 原因と対処                                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| MCP ツールが見えない           | Claude Code を再起動する。`.mcp.json` が repo ルートにあるか、`/mcp` で `blender` が connected か確認               |
| MCP サーバーが立たない         | `just dev` のログに `[just dev] WARNING:` が出ていないか。BlenderMCP アドオン未導入ならそこに指示が出る             |
| ポートが埋まっている           | 他の Blender / MCP インスタンスが残っている。`lsof -nP -iTCP:9876 -sTCP:LISTEN` で確認して落とす                    |
| コードを変えたのに反映されない | `just dev` を **再実行**したか（Blender は起動中に extension を再読込しない）                                       |
| アドオンが有効にならない       | `blender --command extension list` で入っているか確認。`just validate` でマニフェストを検証                         |
| 生成形状が tier 1 と違う       | Blender のバージョン差か、シーンのスケール / 変換行列の影響。`just blender-test` で golden と突き合わせて切り分ける |
