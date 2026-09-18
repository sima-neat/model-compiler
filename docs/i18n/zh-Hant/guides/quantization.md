---
title: "量化"
sidebar_position: 4
---

# 量化

在您使用 `load_model()` 將訓練好的模型導入 `LoadedNet` 之後，使用 `LoadedNet.quantize` 進行量化（請參閱 [API Reference](./api-reference/)）。
SiMa.ai 矽晶片在機器學習加速器 (MLA) 上執行 **INT8** 和 **BF16**，並在應用處理單元 (APU) 和電腦視覺單元 (CVU) 上執行浮點運算。

預處理和後處理函數在 APU 和 CVU 上執行。模型層（例如卷積和池化）在 MLA 上執行。量化器會自動將圖劃分到不同的運算單元。**只有在 MLA 上執行的部分才會進行量化**。

:::note 考量量化的訓練 (QAT)
本頁介紹訓練後量化 (PTQ)。量化感知訓練採用不同的流程，本指南不包含相關內容。
:::

## 預設量化

在建立自訂設定之前，請將 `default_quantization` 作為基準 INT8 設定使用。

```python
from afe.apis.defines import default_quantization

quant_model = loaded_net.quantize(
    calibration_data=calib_data,
    quantization_config=default_quantization,
    model_name="my_model",
)
```

通道均等化是一種可選的預處理步驟，用於使不同通道上的權重分佈保持一致。請透過以下方式啟用：
`QuantizationParams.with_channel_equalization`.

## 量化方案

使用 `quantization_scheme(...)` 來定義一個量化方案。對於**權重**，僅支援對稱量化。對於**激活值**，僅支援逐張量量化。

```python
from afe.apis.defines import quantization_scheme, default_quantization
import dataclasses

symmetric_per_tensor_8_bits  = quantization_scheme(asymmetric=False, per_channel=False, bits=8)
symmetric_per_channel_8_bits = quantization_scheme(asymmetric=False, per_channel=True,  bits=8)
asymmetric_per_tensor_8_bits = quantization_scheme(asymmetric=True,  per_channel=False, bits=8)

quant_configs = default_quantization
quant_configs = dataclasses.replace(quant_configs, weight_quantization_scheme=symmetric_per_channel_8_bits)
quant_configs = dataclasses.replace(quant_configs, activation_quantization_scheme=symmetric_per_tensor_8_bits)

quant_model = loaded_net.quantize(
    calibration_data=calib_data,
    quantization_config=quant_configs,
    model_name="my_model",
)
```

### BF16

BFloat16 量化功能已在 **Modalix** 上推出（開發者預覽版）。使用 `bfloat16_scheme()` 建立 BF16 方案。將其應用於激活值和/或權重，方法是使用 `QuantizationParams.with_activation_quantization` / `with_weight_quantization`。請參閱 [模型相容性](./model-compatibility.md)，以了解每個運算子的 BF16 支援情況。

## 校準方法

校準會決定每一層的量化範圍。**均方誤差 (MSE)** 方法是預設方法。可用的方法如下：

| 方法 | 建構函式 |
| --- | --- |
| 直方圖均方誤差（預設值） | `HistogramMSEMethod()` |
| 最小值/最大值 | `MinMaxMethod()` |
| 移動平均線之最小值／最大值 | `MovingAverageMinMaxMethod()` |
| 直方圖熵 | `HistogramEntropyMethod()` |
| 直方圖百分位數 | `HistogramPercentileMethod(percentile, num_bins)` |

將 `CalibrationMethod.from_str(...)` 作為建構函式使用：

```python
quant_configs = default_quantization.with_calibration(CalibrationMethod.from_str('mse'))

# Or a percentile method with custom percentile and bin count:
quant_configs = default_quantization.with_calibration(HistogramPercentileMethod(91.0, 2048))
```

## 覆寫設定參數

使用 `QuantizationParams` 和 `with_*` 輔助函式來覆寫個別設定：
`with_activation_quantization`、`with_weight_quantization`、
`with_unquantized_nodes`、`with_requantization_mode`、`with_bias_correction`、
`with_calibration`、`with_channel_equalization`，以及
`with_custom_quantization_configs`。請參閱
[API 參考文檔](./api-reference/)，以了解完整的量化 (quantization) 設定。
