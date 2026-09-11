# 手入力式シリコーン配合計算表

## 目的

パーツごとの必要体積を手入力し、2液型シリコーンの必要重量とA剤・B剤の
体積／重量を専用の計算表で即時に確認できるようにする。

## 計算

体積はmL、重量はg、密度はg/mLで扱い、混合比 `RatioA:RatioB` は重量比とする。

```text
k = Volume / (RatioA / DensityA + RatioB / DensityB)
WeightA = k * RatioA
WeightB = k * RatioB
VolumeA = WeightA / DensityA
VolumeB = WeightB / DensityB
```

体積0の行は全ての派生値を0とする。表示する体積と重量は小数2桁固定とする。
初期値はA/B共通密度1.1 g/mL、重量比1:1。

## 保存データ

`Scene.silicone_casting` に次を保存する。

- A/B共通密度を使うか
- A密度、B密度、A比率、B比率
- 行順と各行の `enabled`、`selected`、`part_name`、`volume_ml`

派生値は保存せず、表示時に入力値から再計算する。Shift選択用アンカーは
`SKIP_SAVE` とし、UIListのアクティブ行番号も同様に保存せず、ファイル再読込後は
両方を解除する。共通密度が有効な間はA密度をA/B両方へ用いるが、非表示のB密度値は
保持する。

## UIと行操作

既存の体積計測は変更せず、Measurementパネルの下部へMixture Calculatorを
開くボタンを追加する。ボタンは既存Nパネルの横へ横長のポップオーバーを開き、
新しいBlenderウィンドウや3Dビュー領域は作成しない。各パーツを次の1行で表示する。

選択、Enabled、Name、Volume (mL)、Weight (g)、A Volume (mL)、
B Volume (mL)、A Weight (g)、B Weight (g)

無効行も入力は編集できるが、派生表示をグレー化して集計から除外する。
列幅は固定値にせず全体幅へ追従する比率配分とし、選択とEnabledを狭く、Nameを
最も広く、数値列を同じ比率にする。
選択行が1件以上ある場合だけ、選択かつ有効な行の `Selected` 小計を表示する。
最後の `Total` は常に全有効行を集計する。

UIList標準のフィルターから、`Name` を大文字小文字を区別しない部分一致で検索できる。
検索は表示行だけを絞り込み、選択状態、`Selected` 小計、`Total` には影響しない。

通常クリックした行はBlender標準のリストハイライトで示す。複数選択時の非アクティブ
行は左端の押下された行番号で示し、選択用チェックボックスは表示しない。行番号を使う
選択操作は次の通り。

- 通常クリック: 単独選択
- Ctrlクリック: 個別トグル
- Shiftクリック: アンカーから連続選択
- Ctrl+Shiftクリック: アンカーからの範囲を追加

`+` は末尾へ既定行を追加し、`-` は選択行を一括削除する。上下操作は選択行の
相対順序を保って各連続ブロックを1段移動する。削除・移動後はアンカーを解除する。

## JSON 入出力

Export JSON は密度設定、重量比、全行の名前・体積・Enabled・選択状態を保存する。
Import JSON は全内容を検証後、設定と行を置換する。アクティブ行と選択アンカーは解除する。
形式は `format: silicone_casting`、`version: 1`、`kind: MIXTURE`、`data` の JSON とする。
不正な型・範囲・形式バージョンは設定を変更せずエラーにする。

## 対象外

オブジェクトとのリンク、自動計測取り込み、CSV入出力、行複製は扱わない。
