---
title: "Квантування"
sidebar_position: 4
---

# Квантування

Після того, як ви імпортуєте навчену модель у `LoadedNet` за допомогою `load_model()`, виконайте квантування
за допомогою `LoadedNet.quantize` (див. [Довідник API](./api-reference/)).
SiMa.ai на кремнієвій платформі виконує операції **INT8** і **BF16** на прискорювачі машинного навчання (MLA), а також операції з плаваючою комою на блоці обробки додатків (APU) і блоці комп’ютерного зору (CVU).

Функції попередньої та подальшої обробки виконуються на APU та CVU. Шари моделі, такі як згортка та об’єднання, виконуються на MLA. Квантизатор автоматично розподіляє граф між обчислювальними блоками. **Квантуються лише ті частини, які виконуються на MLA**.

:::note Навчання з урахуванням квантування (QAT).
На цій сторінці описано метод квантування після навчання (PTQ). Квантування з урахуванням процесу навчання використовує окремий алгоритм і не розглядається в цьому посібнику.
:::

## Квантування за замовчуванням.

Використовуйте `default_quantization` як базову конфігурацію INT8 перед створенням власних конфігурацій.

```python
from afe.apis.defines import default_quantization

quant_model = loaded_net.quantize(
    calibration_data=calib_data,
    quantization_config=default_quantization,
    model_name="my_model",
)
```

Вирівнювання каналів — це необов’язковий етап попередньої обробки, який зрівнює розподіл ваг між каналами. Увімкніть його за допомогою `QuantizationParams.with_channel_equalization`.

## Схеми квантування.

Використовуйте `quantization_scheme(...)`, щоб визначити схему. Для **ваг** підтримується лише симетричне квантування. Для **активацій** підтримується лише квантування для кожного тензора.

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

Квантування BFloat16 доступне в **Modalix** (попередня версія для розробників). Створіть схему BF16 за допомогою `bfloat16_scheme()`. Застосуйте її до активацій та/або ваг за допомогою `QuantizationParams.with_activation_quantization` / `with_weight_quantization`. Див. [Сумісність моделей](./model-compatibility.md) для підтримки BF16 для кожного оператора.

## Методи калібрування.

Калібрування визначає діапазони квантування для кожного шару. Метод **MSE** є стандартним. Доступні методи:

| Метод | Конструктор |
| --- | --- |
| Гістограма середньоквадратичної похибки (значення за замовчуванням) | `HistogramMSEMethod()` |
| Мінімум/максимум | `MinMaxMethod()` |
| Мінімальне/максимальне значення ковзної середньої | `MovingAverageMinMaxMethod()` |
| Ентропія гістограми. | `HistogramEntropyMethod()` |
| Перцентиль гістограми | `HistogramPercentileMethod(percentile, num_bins)` |

Використовуйте `CalibrationMethod.from_str(...)` як конструктор:

```python
quant_configs = default_quantization.with_calibration(CalibrationMethod.from_str('mse'))

# Or a percentile method with custom percentile and bin count:
quant_configs = default_quantization.with_calibration(HistogramPercentileMethod(91.0, 2048))
```

## Зміна параметрів конфігурації.

Використовуйте `QuantizationParams` та допоміжні функції `with_*`, щоб замінити окремі налаштування:
`with_activation_quantization`, `with_weight_quantization`,
`with_unquantized_nodes`, `with_requantization_mode`, `with_bias_correction`,
`with_calibration`, `with_channel_equalization` та
`with_custom_quantization_configs`. Див. [довідник API](./api-reference/) для отримання повної інформації.
