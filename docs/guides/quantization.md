---
title: Quantization
sidebar_position: 4
---

# Quantization

Once a trained model is imported into the `LoadedNet` form with `load_model()`,
quantize it with `LoadedNet.quantize` (see the [API Reference](./api-reference/)).
SiMa.ai silicon runs **INT8** and **BF16** on the Machine Learning Accelerator
(MLA), and floating-point operations on the Application Processing Unit (APU)
and Computer Vision Unit (CVU).

Pre/post-processing functions run on the APU and CVU; model layers such as
convolution and pooling run on the MLA. The quantizer partitions the graph
across compute units automatically and **only the parts that run on the MLA are
quantized**.

## Default quantization

`default_quantization` is a baseline configuration that quantizes a model the
default way (INT8) and is a good starting point for custom configs.

```python
from afe.apis.defines import default_quantization

quant_model = loaded_net.quantize(
    calibration_data=calib_data,
    quantization_config=default_quantization,
    model_name="my_model",
)
```

Channel equalization is an optional preprocessing step that equalizes weight
distributions across channels and can improve quantization quality. Enable it
with `QuantizationParams.with_channel_equalization`.

## Quantization schemes

Use `quantization_scheme(...)` to define a scheme. For **weights**, only
symmetric quantization is supported; for **activations**, only per-tensor
quantization is supported.

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

BFloat16 quantization is available on **Modalix** (developer preview). Build a
BF16 scheme with `bfloat16_scheme()` and apply it to activations and/or weights
via `QuantizationParams.with_activation_quantization` /
`with_weight_quantization`. See [Supported Operators](./supported-operators.md)
for per-operator BF16 support.

## Calibration methods

Calibration determines per-layer quantization ranges. The **MSE** method
consistently produces good results and is the default. Available methods:

| Method | Constructor |
| --- | --- |
| Histogram MSE (default) | `HistogramMSEMethod()` |
| Min/Max | `MinMaxMethod()` |
| Moving-average Min/Max | `MovingAverageMinMaxMethod()` |
| Histogram entropy | `HistogramEntropyMethod()` |
| Histogram percentile | `HistogramPercentileMethod(percentile, num_bins)` |

`CalibrationMethod.from_str(...)` is a convenient constructor:

```python
quant_configs = default_quantization.with_calibration(CalibrationMethod.from_str('mse'))

# Or a percentile method with custom percentile and bin count:
quant_configs = default_quantization.with_calibration(HistogramPercentileMethod(91.0, 2048))
```

## Overriding configuration parameters

`QuantizationParams` exposes `with_*` helpers to override individual settings:
`with_activation_quantization`, `with_weight_quantization`,
`with_unquantized_nodes`, `with_requantization_mode`, `with_bias_correction`,
`with_calibration`, `with_channel_equalization`, and
`with_custom_quantization_configs`. See the
[API reference](./api-reference/) for the full surface.
