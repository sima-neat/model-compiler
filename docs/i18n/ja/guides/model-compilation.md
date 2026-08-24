---
title: "コンパイル"
sidebar_position: 5
---

# コンパイル

`Model.compile` を使用して、量子化された**モデル**を、SiMa MLSoC で実行可能なバイナリ形式に変換します。

```python
from afe.apis.model import Model

# Load a previously quantized model
quant_model = Model.load("<quant_model_name>", "<path to quantized model file>")
```

## デフォルトのオプションでコンパイルする

出力先のフォルダーを指定してください。

```python
quant_model.compile(output_path="<output_folder_path>")
```

出力は、量子化されたモデルファイルの名前にちなんで名付けられた`.tar.gz`形式のアーカイブです。これには、以下のものが含まれます。

| 目次 | 目的 |
| --- | --- |
| `.elf`ファイル | MLAで実行されました。 |
| `.so`ファイル | Cortex-A65上で実行（必要な場合にのみ）。 |
| `.yaml` ファイル | 実行統計のプロファイリング |
| `_mpk.json` | プロセッサープラグインの設定／パイプラインのメタデータ |

## テッセレーション {#tessellation}

**テッセレーション**は、MLA（乗算加算ユニット）で使用される入力および出力テンソルがDRAMにどのように配置されるかを制御します。入力テンソルを`HWC`形式で、出力テンソルを`HWC16`形式で、MLAに**直接送受信**することで、EV74データ再配置ユニットをバイパスし、遅延を削減します。これは、アクセラレータに直接データを供給するモデルに対して**推奨されるデフォルト**設定です。[first-model example](./compile-your-first-model.md)では、デフォルトでこの設定が有効になっています。

コンパイル時に、テンソルごとにテッセレーションパラメータを渡します。

```python
from afe.apis.defines import TensorTessellateParameters, TensorDRAMLayout

input_tess  = TensorTessellateParameters(tile_shape=(0, 0, 0, 0), enable_mla=True,
                                          dram_layout=TensorDRAMLayout.HWC)
output_tess = TensorTessellateParameters(tile_shape=(0, 0, 0, 0), enable_mla=True,
                                          dram_layout=TensorDRAMLayout.HWC16)

tess_params = {}
mla_node = quant_model._net.nodes["MLA_0"]
for name in mla_node.input_names:
    tess_params[name] = input_tess
# (resolve MLA output names and map them to output_tess — see the example script)

quant_model.compile(output_path="<output_folder_path>", tessellate_parameters=tess_params)
```

`sima-cli neat install model-compiler/examples`によってインストールされた最初のモデルの例では、この設定が自動的に行われます。
EV74の再配置パスがパイプラインに必要な場合にのみ、テッセレーションの設定を解除してください（`tessellate_parameters=None`）。

## バッチサイズが1より大きい場合にコンパイルする。

**希望する**バッチサイズを設定してください。

```python
quant_model.compile(output_path="<output_folder_path>", batch_size=16)
```

:::note
コンパイラは、要求された値まで、可能な限り最大のバッチサイズを実装します。ただし、要求されたサイズと完全に一致することを保証するものではありません。実際に実装された内容を確認するには、`_mpk.json` 内の `desired_batch_size` と `actual_batch_size` を参照してください。

```json
"name": "MLA_0",
"processor": "MLA",
"config_params": {
    "desired_batch_size": 16,
    "actual_batch_size": 12,
    "number_of_quads_to_user": 4
}
```
:::

## アーカイブの確認

コンパイラはアーカイブの内容を出力しません。以下のコマンドでリスト表示してください。

```python
import tarfile

with tarfile.open("<name_of_archive.tar.gz>") as f:
    for filename in f.getnames():
        print(filename)
```

## レイヤーごとの実行時統計情報

各コンパイルされたアーカイブには、コンパイラによって推定された MLA レイヤーごとのサイクル数を含む `*_mla_stats.yaml` ファイルが含まれています。

```yaml
4:
  name: MLA_0/conv2d_add_relu_3
  start_cycle: 63615
  end_cycle: 71558
5:
  name: MLA_0/conv2d_add_relu_4
  start_cycle: 71559
  end_cycle: 79502
```

これらの値は、静的なスケジュールに基づく開始サイクルと終了サイクルです。命令またはメモリのフェッチによる停止時間は含まれません。メモリサイクルを含む、完全な実行時統計を取得するには、PaletteのNeatアクセラレーターモードで、ハードウェア上で`.elf`モデルを実行してください。
