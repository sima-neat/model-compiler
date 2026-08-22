---
title: "編譯"
sidebar_position: 5
---

# 編譯

使用 `Model.compile` 將一個**量化**後的模型轉換為二進位格式，以便在 SiMa MLSoC 上執行。

```python
from afe.apis.model import Model

# Load a previously quantized model
quant_model = Model.load("<quant_model_name>", "<path to quantized model file>")
```

## 使用預設選項進行編譯。

指定輸出資料夾：

```python
quant_model.compile(output_path="<output_folder_path>")
```

輸出的結果是一個名為「量化模型檔案」的 `.tar.gz` 壓縮檔。它包含：

| 內容 | 目的 |
| --- | --- |
| `.elf` 檔案 | 已在 MLA 上執行。 |
| `.so` 檔案 | 在需要時於 Cortex-A65 處理器上執行。 |
| `.yaml` 檔案 | 執行統計資料分析 |
| `_mpk.json` | 處理器外掛程式設定／流程管線中繼資料 |

## 鑲嵌圖案 {#tessellation}

**鑲嵌**控制輸入和輸出張量如何在 DRAM 中排列，以供 MLA 使用。將張量**直接傳送到 MLA 並從 MLA 傳出**，輸入採用 `HWC` 格式，輸出採用 `HWC16` 格式，可繞過 EV74 資料重新排序單元，從而降低延遲。這是**建議的預設設定**，適用於直接饋送至加速器的模型。[第一個模型範例](./compile-your-first-model.md) 預設啟用此功能。

在編譯時，針對每個張量傳遞鑲嵌參數：

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

透過 `sima-cli neat install model-compiler/examples` 安裝的第一個模型範例會自動設定好這些參數。
只有在您的流程需要使用 EV74 重新排序路徑時，才將鑲嵌參數設定為未設定 (`tessellate_parameters=None`)。

## 編譯時，批次大小設定為大於 1。

設定**所需的**批次大小：

```python
quant_model.compile(output_path="<output_folder_path>", batch_size=16)
```

:::note
編譯器會實作它能處理的最大批次大小，最多到使用者要求的數值。它不會保證批次大小完全符合使用者要求。若要查看實際實作的批次大小，請搜尋 `_mpk.json` 中的 `desired_batch_size` 和 `actual_batch_size`。

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

## 檢查檔案。

編譯器不會顯示壓縮檔的內容。請使用以下指令來列出：

```python
import tarfile

with tarfile.open("<name_of_archive.tar.gz>") as f:
    for filename in f.getnames():
        print(filename)
```

## 每層的執行時統計資料

每個編譯後的檔案都包含一個 `*_mla_stats.yaml` 檔案，其中包含編譯器估算的每個 MLA 層次的週期次數：

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

這些值是靜態排程的起始和結束週期。它們不包含來自指令或記憶體讀取的停頓週期。若要取得完整的執行時統計資料（包括記憶體週期），請在 Palette 中的 Neat 加速器模式下，於硬體上執行 `.elf` 模型。
