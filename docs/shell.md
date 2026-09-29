# 壁と Boolean（Inherit Shape / Solidify / Boolean）

[README に戻る](../README.md)

どれも Object Mode で操作する。

## 🔗 Inherit Shape

マスターに手を加えずに、同じ形のオブジェクトを作る。型の壁はこのオブジェクトに付ける。

![Inherit Shape の欄。1 が Inherit Shape ボタン、2 がコレクションの指定欄、3 が Inherit Collection Shape ボタン](images/inherit-shape.png)

マスターをアクティブにして **Inherit Shape** を押すと、`<マスター名>.inherit` が同じ位置にでき、**それだけが選択・アクティブ** になる。

- メッシュ自体は空。**Inherit Shape**（Boolean Union）モディファイアでマスターを参照している
- マスターは変わらない。マスターを編集すると `.inherit` も追従する
- マスターを消す・動かすと `.inherit` も消える・動くので、マスターは残しておく（非表示は可）

**Inherit Collection Shape** は、指定したコレクション内（子コレクションを含む）の全メッシュを Union した形を参照する。

- 作られる場所はシーンの一番上のコレクション
- メッシュ以外が入ったコレクションはエラー
- Scene Collection そのものは指定不可

## 🧱 Solidify

選択中のすべてのメッシュに、厚みを付ける **Silicone Casting Solidify** モディファイアを付ける。

![Solidify の欄。1 が Thickness、2 が Flip Direction、3 が Even Thickness、4 が Solidify ボタン、5 が Apply Solidify ボタン](images/solidify.png)

- **Thickness**: 壁の厚さ（[単位の扱い](units.md)）
- **Flip Direction**: オフ（既定）で法線の向き＝外側へ厚みを付け、内側は元の形のまま。オンで内側へ
- **Even Thickness**: オン（既定）で角でも厚さを保つ

もう一度押すと、同じモディファイアが新しい設定に更新される（重ねて増えない）。

設定値はボタンを押したときに読み込まれる。値を変えただけでは、付いているモディファイアは変わらない。

### 型の壁を作る手順

| 手順 | 操作                                                                            | 操作する時点で選択・アクティブなもの          | 結果                                                        |
| ---- | ------------------------------------------------------------------------------- | --------------------------------------------- | ----------------------------------------------------------- |
| 1    | **Inherit Shape** を押す                                                        | マスター（クリックしてアクティブにしておく）  | `<マスター名>.inherit` ができ、選択・アクティブがそれに移る |
| 2    | **Thickness** を入れ、**Flip Direction** をオフにして **Solidify** を押す       | `.inherit`（手順 1 で自動的に選択されたまま） | `.inherit` に外向きの壁が付く。マスターは変わらない         |
| 3    | シリコーンの量を測る: マスターをクリックして選び直し、**Measure Volume** を押す | マスター                                      | マスターの体積 = 型の空洞 = 必要なシリコーンの量            |
| 4    | （必要なら）樹脂の量を測る: `.inherit` だけを選び、**Measure Volume** を押す    | `.inherit`                                    | 壁だけの体積 = 印刷する樹脂の量                             |

> ⚠️ **注意**: 手順 2 の後にそのまま Measure Volume を押すと、`.inherit`（壁）が測られる。
> シリコーンの量は、マスターを選び直して測る（[何を測るか](measurement.md#%E4%BD%95%E3%82%92%E6%B8%AC%E3%82%8B%E3%81%8B)）。

### Apply Solidify

**Silicone Casting Solidify だけ** をメッシュに焼き込み、そのモディファイアを外す。

焼き込みはオブジェクト自身のメッシュに対して行い、他のモディファイアの効果は含めない（他のモディファイアは残る）。

> ⚠️ **注意**: **Inherit Shape で作ったオブジェクトには使わない。**
> 自身のメッシュが空なので、壁が消えてマスターの形だけに戻る（**Ctrl+Z** で戻せる）。
> 形をまとめて確定するなら、全モディファイアを適用する [Separate Loose Parts](surface-cut.md#-separate-loose-parts) を使う。

メッシュを他のオブジェクトと共有しているオブジェクトには使えない。

## ➖ Boolean

**アクティブなオブジェクト** に、**Operand**（別のメッシュ）を使う Boolean モディファイアを追加する。

![Boolean の欄。1 が Operand、2 が Solver、3 が Difference・Union・Intersect のボタン](images/boolean.png)

- **Difference**: アクティブから Operand を引く
- **Union**: 足す
- **Intersect**: 重なった部分だけを残す
- **Solver**: **Manifold**（閉じたメッシュ向けで最速）、**Exact**（既定。重なりや同一平面に強い）、**Float**（単純で速いが重なりに弱い）

Operand 自体は変わらない。押すたびにモディファイアが 1 つ追加される。

### ボタンが押せないとき

- Object Mode ではない
- アクティブなオブジェクトがメッシュでない、または選択されていない
- **Operand** が空
- **アクティブなオブジェクトと Operand が同じ**

Shift+クリックで複数選ぶと、**最後にクリックしたもの** がアクティブになる。

加工される型を最後にクリックする。

![Operand にするオブジェクトを最後にクリックしてアクティブにしてしまい、Boolean のボタンが押せなくなっている状態](images/boolean-disabled.png)

> ⚠️ **注意**: **Operand** の欄は、Surface Cut の Operand と **同じ設定**。片方で変えると、もう片方も変わる。
> Operand のオブジェクトはシーンに残るので、STL 出力や体積計測の選択に含めない（非表示にしても Boolean は効く）。
