---
title: "양자화"
sidebar_position: 4
---

# 양자화

학습된 모델을 `load_model()`를 사용하여 `LoadedNet`에 가져온 후, `LoadedNet.quantize`를 사용하여 양자화합니다([API 참조](./api-reference/) 참조).

SiMa.ai 실리콘은 머신 러닝 가속기(MLA)에서 **INT8** 및 **BF16**으로, 애플리케이션 처리 장치(APU) 및 컴퓨터 비전 장치(CVU)에서 부동 소수점 연산을 수행합니다.

전처리 및 후처리 함수는 APU 및 CVU에서 실행됩니다. 컨볼루션 및 풀링과 같은 모델 레이어는 MLA에서 실행됩니다. 양자화기는 그래프를 컴퓨팅 장치에 걸쳐 자동으로 분할합니다. **MLA에서 실행되는 부분만 양자화됩니다**.

:::note 양자화를 고려한 훈련(QAT)
학습 후 양자화(PTQ)는 아래의 기본 양자화 섹션을 따르세요. PyTorch 모델을 다시 훈련할 수 있다면 [양자화 인식 학습](/compile-a-model/quantization-aware-training/)을 사용하여 미세 조정 중에 INT8 효과를 시뮬레이션하고 표준 QDQ ONNX 모델을 내보냅니다. 그런 다음 [QAT ONNX에서 컴파일된 모델로](#qat-onnx-to-compiled-model)를 따르세요.
:::

## 기본 양자화

사용자 지정 구성을 만들기 전에 `default_quantization`을 기본 INT8 구성으로 사용하세요.

```python
from afe.apis.defines import default_quantization

quant_model = loaded_net.quantize(
    calibration_data=calib_data,
    quantization_config=default_quantization,
    model_name="my_model",
)
```

채널 이퀄라이제이션은 채널 간의 가중치 분포를 균등하게 조정하는 선택적인 전처리 단계입니다. 다음을 사용하여 활성화할 수 있습니다.
`QuantizationParams.with_channel_equalization`.

### QAT 내보내기 {#qat-onnx-to-compiled-model}

[QDQ ONNX 모델을 일반적인 방법으로 불러온](./compile-your-first-model.md) 다음, 위의 `LoadedNet.quantize`와 [컴파일](./model-compilation.md)에서 설명하는 `Model.compile`을 사용하세요. AFE는 내보낸 QDQ의 스케일과 영점을 읽으므로 내부 플래그 `is_quantized=True`를 설정하지 마세요.

`calibration_data`는 여전히 필요하지만, QDQ로 지정된 범위는 샘플에서 다시 추정하지 않으므로 무작위 더미 입력으로 충분합니다. 입력 이름, 데이터 타입, 유효한 값, SDK 레이아웃(4D 이미지는 NHWC)을 맞추세요. QDQ 힌트 없이 양자화하는 영역에는 대표적인 보정 데이터를, 정확도 검증에는 실제 평가 데이터를 사용하세요.

## 양자화 방식

`quantization_scheme(...)`을 사용하여 양자화 방식을 정의합니다. **가중치**의 경우, 대칭 양자화만 지원됩니다. **활성화 함수**의 경우, 텐서별 양자화만 지원됩니다.

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

**Modalix**(개발자 미리보기)에서 BFloat16 양자화를 사용할 수 있습니다. `bfloat16_scheme()`를 사용하여 BF16 방식을 구축합니다. `QuantizationParams.with_activation_quantization` / `with_weight_quantization`를 사용하여 활성화 또는 가중치에 적용합니다. 연산자별 BF16 지원에 대해서는 [모델 호환성](./model-compatibility.md)를 참조하십시오.

## 교정 방법

보정은 각 레이어별 양자화 범위를 결정합니다. **MSE** 방법이 기본값입니다. 사용 가능한 방법은 다음과 같습니다.

| 방법 | 생성자 |
| --- | --- |
| 히스토그램 MSE(기본값) | `HistogramMSEMethod()` |
| 최소/최대 | `MinMaxMethod()` |
| 이동 평균 최솟값/최댓값 | `MovingAverageMinMaxMethod()` |
| 히스토그램 엔트로피 | `HistogramEntropyMethod()` |
| 히스토그램 백분위수 | `HistogramPercentileMethod(percentile, num_bins)` |

`CalibrationMethod.from_str(...)`를 생성자로 사용하세요.

```python
quant_configs = default_quantization.with_calibration(CalibrationMethod.from_str('mse'))

# Or a percentile method with custom percentile and bin count:
quant_configs = default_quantization.with_calibration(HistogramPercentileMethod(91.0, 2048))
```

## 구성 매개변수 재정의

개별 설정을 재정의하려면 `QuantizationParams`와 함께 제공되는 `with_*` 헬퍼를 사용하세요.

`with_activation_quantization`, `with_weight_quantization`,
`with_unquantized_nodes`, `with_requantization_mode`, `with_bias_correction`,
`with_calibration`, `with_channel_equalization` 및
`with_custom_quantization_configs`를 사용할 수 있습니다. 전체 내용은 [API reference](./api-reference/)를 참조하세요. (양자화)
