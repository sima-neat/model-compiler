---
title: "量子化"
sidebar_position: 4
---

# 量子化

学習済みのモデルを `LoadedNet` に `load_model()` を使用してインポートした後、`LoadedNet.quantize` を使用して量子化します（[API Reference](./api-reference/) を参照）。

SiMa.ai シリコンは、機械学習アクセラレータ（MLA）上で **INT8** および **BF16** を、アプリケーション処理ユニット（APU）およびコンピュータビジョンユニット（CVU）上で浮動小数点演算を実行します。

前処理および後処理関数は、APUおよびCVU上で実行されます。畳み込みやプーリングなどのモデルレイヤーは、MLA上で実行されます。量子化器は、グラフを計算ユニット間で自動的に分割します。**MLA上で実行される部分のみが量子化されます**。

:::note 量子化を考慮した学習（QAT）
このページでは、学習後の量子化（PTQ）について説明します。量子化を考慮した学習は、別のワークフローを使用するため、このガイドでは扱いません。
:::

## デフォルトの量子化

カスタム構成を作成する前に、`default_quantization` をベースラインの INT8 構成として使用してください。

```python
from afe.apis.defines import default_quantization

quant_model = loaded_net.quantize(
    calibration_data=calib_data,
    quantization_config=default_quantization,
    model_name="my_model",
)
```

チャンネル等化は、チャンネル間で重みの分布を均一にするためのオプションの事前処理ステップです。これを有効にするには、`QuantizationParams.with_channel_equalization` を使用します。

## 量子化方式

ある方式を定義するには、`quantization_scheme(...)`を使用します。**重み**については、対称量子化のみがサポートされます。**活性化関数**については、テンソルごとの量子化のみがサポートされます。

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

**Modalix**（開発者向けプレビュー版）では、BFloat16量子化が利用可能です。`bfloat16_scheme()`を使用してBF16スキームを構築し、`QuantizationParams.with_activation_quantization`および/`with_weight_quantization`を使用して、活性化関数および/または重みに適用します。演算子ごとのBF16サポートについては、[モデル互換性](./model-compatibility.md)を参照してください。

## 校正方法

キャリブレーションによって、各レイヤーの量子化範囲が決定されます。デフォルトの方法は**MSE**です。利用可能な方法は以下のとおりです。

| 方法 | コンストラクタ |
| --- | --- |
| ヒストグラムMSE（デフォルト） | `HistogramMSEMethod()` |
| 最小値/最大値 | `MinMaxMethod()` |
| 移動平均による最小値/最大値 | `MovingAverageMinMaxMethod()` |
| ヒストグラムのエントロピー | `HistogramEntropyMethod()` |
| ヒストグラムのパーセンタイル | `HistogramPercentileMethod(percentile, num_bins)` |

コンストラクタとして `CalibrationMethod.from_str(...)` を使用してください。

```python
quant_configs = default_quantization.with_calibration(CalibrationMethod.from_str('mse'))

# Or a percentile method with custom percentile and bin count:
quant_configs = default_quantization.with_calibration(HistogramPercentileMethod(91.0, 2048))
```

## 設定パラメータのオーバーライド

個々の設定を上書きするには、`QuantizationParams`と、以下のヘルパー関数である`with_*`を使用します。

`with_activation_quantization`、`with_weight_quantization`、
`with_unquantized_nodes`、`with_requantization_mode`、`with_bias_correction`、
`with_calibration`、`with_channel_equalization`、および
`with_custom_quantization_configs`。完全な機能については、[API reference](./api-reference/)を参照してください。
