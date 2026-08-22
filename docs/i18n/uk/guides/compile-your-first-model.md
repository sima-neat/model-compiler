---
title: "Створіть свою першу модель."
sidebar_position: 1
---

# Створіть свою першу модель.

Ця інструкція показує, як за допомогою Model Compiler провести ONNX модель **ResNet-50** через процес **пост-тренувального квантування (PTQ)**. Результатом є скомпільований архів MPK у форматі `.tar.gz` для середовища виконання Neat.

Процес складається з чотирьох етапів:

1. **Завантажте** модель.
2. За замовчуванням використовуйте квантування до INT8, або BF16, якщо це необхідно.
3. **Перевірте** її точність.
4. **Скомпілюйте** його для виконання на MLSoC.

## Необхідні умови / вимоги.

- `sima-cli` встановлено (див. [інструкцію зі встановлення sima-cli](https://github.com/sima-neat/sima-cli)).
- Model Compiler встановлено в Neat SDK або на хост-машині Ubuntu. Введіть.
  середовище з:

```bash
activate-model-compiler
```

## Отримайте приклад.

На хост-системі з встановленою Neat SDK або Ubuntu, де встановлено Model Compiler, встановіть приклади Model Compiler за допомогою `sima-cli`:

```bash
sima-cli neat install model-compiler/examples
```

Залиште середовище Model Compiler активним протягом усього процесу.

Запустіть приклад «quantize-and-compile». Скрипт генерує ONNX модель ResNet-50 і завантажує загальнодоступні дані калібрування Open Images, якщо їх ще немає:

```bash
cd resnet50-ptq
python3 compile.py
```

Коли надаються вхідні дані для перевірки, програма має ідентифікувати золотистого ретривера як зображення, що належить до класу 207 у базі даних ImageNet, і створити скомпільований архів:

```text
Validation image prediction:
  class 207: 'golden retriever' -> 98.82%
Quantization complete.
Compiling model. Output directory: .../compiled_resnet50
Compiled MPK archive written to: .../compiled_resnet50/quantized_resnet50_mpk.tar.gz
```

Використовуйте отриманий `.tar.gz` для [перевірки точності та продуктивності](./validate-accuracy-performance.md),
або використовуйте його для [створення застосунку для обробки даних у конвеєрі](/develop-apps/).

Наступні розділи пояснюють кожен етап. [Повний скрипт](#full-script)
наведено в кінці. MLA-теселяція **увімкнена за замовчуванням**, тому скомпільована
модель безпосередньо передає дані прискорювачу. Див.
[Компіляція > Теселяція](./model-compilation.md#tessellation).

## Як це працює.

### 1. Завантажте модель.

Завантажте ONNX модель ResNet-50 у внутрішнє представлення SDK.

```python
from afe.apis.loaded_net import load_model
from afe.apis.defines import gen1_target, gen2_target
from afe.load.importers.general_importer import onnx_source
from afe.ir.tensor_type import ScalarType

MODEL_PATH = "resnet50.onnx"
TARGET = gen2_target  # gen2_target = Modalix, gen1_target = MLSoC

# Model information
input_name, input_shape, input_type = ("input", (1, 3, 224, 224), ScalarType.float32)
input_shapes_dict = {input_name: input_shape}
input_types_dict = {input_name: input_type}

# Load the ONNX model
importer_params = onnx_source(str(MODEL_PATH), input_shapes_dict, input_types_dict)
loaded_net = load_model(importer_params, target=TARGET)
```

Вхідний тензор `"input"` має розмірність `(1, 3, 224, 224)` — розмір пакета дорівнює одному, три
кольорові канали, 224×224 пікселів — і тип `float32`. `onnx_source` описує, як
зчитувати модель (сам файл ONNX не змінюється); `load_model` перетворює її
на `LoadedNet`, готову до квантування. `TARGET` вибирає платформу:
`gen1_target` для MLSoC, `gen2_target` для Modalix.

### 2. Підготуйте набір даних для калібрування.

Для квантування потрібен невеликий, репрезентативний набір даних для калібрування. Цей набір даних визначає коефіцієнти масштабування, які відображають значення FP32 в цілочисельний діапазон, запобігаючи надмірному обрізанню або втраті точності.

```python
import cv2
import numpy as np

from sima_utils.data.data_generator import DataGenerator
from afe.core.utils import convert_data_generator_to_iterable

MODEL_INPUT_NAME = "input"
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

def preprocess(image: np.ndarray, size=(224, 224)) -> np.ndarray:
    """Resize to 224x224, scale to [0, 1], normalize. Returns HWC float32."""
    image = cv2.resize(image, size).astype(np.float32) / 255.0
    return ((image - IMAGENET_MEAN) / IMAGENET_STD).astype(np.float32)

# Build a DataGenerator from preprocessed NHWC calibration images.
calibration_images = np.stack([preprocess(image) for image in raw_calibration_images])
calib_data = convert_data_generator_to_iterable(
    DataGenerator({MODEL_INPUT_NAME: calibration_images}))
```

:::note
Дані калібрування, що передаються до `DataGenerator`, повинні бути у форматі **NHWC**
(`[batch, height, width, channels]`), навіть якщо вхідний тензор моделі має формат
**NCHW** (`[batch, channels, height, width]`) — як у цьому прикладі, де
формат вхідних даних ONNX дорівнює `(1, 3, 224, 224)`. Наведений вище приклад вже генерує NHWC,
оскільки `preprocess` повертає зображення у форматі HWC. Якщо ваш процес попередньої обробки
генерує масиви у форматі NCHW, виконайте їх транспонування перед створенням
набору даних для калібрування:

```python
# Convert NCHW -> NHWC
calibration_images = np.transpose(calibration_images, (0, 2, 3, 1))
calib_data = convert_data_generator_to_iterable(
    DataGenerator({MODEL_INPUT_NAME: calibration_images}))
```
:::

Використовуйте репрезентативні зображення, отримані з того ж набору даних, що й для вашого робочого навантаження під час розгортання.

### 3. Квантування

Після завантаження моделі та підготовки даних для калібрування виконайте її квантування. У наданому прикладі за замовчуванням використовується INT8, оскільки це найбільш поширений формат. Під час квантування деяких моделей у формат INT8 можуть з’являтися попередження про переповнення; перевірте квантовану модель перед використанням скомпільованого результату:

```python
from afe.apis.defines import QuantizationParams, quantization_scheme, CalibrationMethod
from afe.core.utils import convert_data_generator_to_iterable

quant_configs = QuantizationParams(
    calibration_method=CalibrationMethod.from_str('mse'),
    activation_quantization_scheme=quantization_scheme(
        asymmetric=True, per_channel=False, bits=8),
    weight_quantization_scheme=quantization_scheme(
        asymmetric=False, per_channel=True, bits=8),
)

sdk_net = loaded_net.quantize(
    calib_data,
    quant_configs,
    model_name="quantized_resnet50",
)
```

У цьому прикладі використовується 8-бітове асиметричне квантування для кожного тензора для активацій і 8-бітове симетричне квантування для кожного каналу для ваг. Щодо параметрів BF16 і калібрування, див. **[Квантування](./quantization.md)**.

### 4. Перевірте точність.

Перш ніж виконати компіляцію, запустіть квантовану модель у програмному забезпеченні за допомогою `sdk_net.execute(...)` і переконайтеся, що вона, як і раніше, правильно класифікує дані:

```python
import numpy as np

def postprocess_output(output: np.ndarray, labels: list[str]):
    probabilities = output[0][0]
    idx = int(np.argmax(probabilities))
    name = labels[idx] if idx < len(labels) else "?"
    return idx, name, probabilities[idx]

# A known image: a Golden Retriever is ImageNet class 207.
with open("data/imagenet_labels.txt") as f:
    labels = [line.strip() for line in f]
dog = preprocess(cv2.cvtColor(cv2.imread("data/golden_retriever_207.jpg"), cv2.COLOR_BGR2RGB))
output = sdk_net.execute(inputs={"input": np.expand_dims(dog, axis=0)})
idx, name, score = postprocess_output(output, labels)
print(f"class {idx}: '{name}' -> {100.0 * score:.2f}%")
```

Точний прогноз із високим ступенем достовірності, наприклад,
`207 'golden retriever' -> 98.82%`, підтверджує, що попередня обробка та квантування узгоджені. Неправильна класифікація зазвичай вказує на невідповідність у попередній обробці або на проблему з квантуванням, яку необхідно виправити.

### 5. Зберіть (усі частини) разом.

Після успішної перевірки збережіть і скомпілюйте модель:

```python
sdk_net.save(model_name="quantized_resnet50", output_directory=args.output)
tess = mla_tessellate_params(sdk_net) if args.mla_tessellation else None
sdk_net.compile(output_path=args.output, tessellate_parameters=tess)
```

Результатом є `.tar.gz` архів, який містить скомпільовані програми MLA, а також
`_mpk.json` файл метаданих і файл зі статистикою виконання. Див.[Компіляція](./model-compilation.md)** для вмісту архіву, визначення розміру пакетів і параметрів теселяції.

## Повний сценарій {#full-script}

Повний анотований код програми наведено нижче. Він також доступний у пакеті прикладів для компілятора моделей як `resnet50-ptq/compile.py`, а також у
[ResNet-50 PTQ example source](https://github.com/sima-neat/model-compiler/tree/main/examples/resnet50-ptq)
на GitHub:

```bash
sima-cli neat install model-compiler/examples
cd resnet50-ptq
```

Скрипт запускається для вашої власної ONNX моделі та папки з калібрувальними зображеннями:

```bash
python3 compile.py \
  --model resnet50.onnx \
  --calib_images ./calib_images \
  --output ./compiled_resnet50
# optional accuracy check:
#   --validate golden_retriever_207.jpg --labels imagenet_labels.txt
```

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Compile your first model — ResNet-50 PTQ end-to-end.

Loads an ONNX ResNet-50, calibrates on a folder of images, quantizes to INT8
by default, optionally validates accuracy, and compiles to an MPK ``.tar.gz``.

MLA tessellation is **enabled by default** (inputs HWC, outputs HWC16, driven
directly to/from the MLA, bypassing the EV74 reorder unit). Disable it with
``--no-mla-tessellation`` if your pipeline needs the EV74 reorder path.

Example:
    python3 compile.py
"""

import argparse
import logging
import os
import pickle
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from afe.apis.loaded_net import load_model
from afe.apis.defines import (
    gen1_target, gen2_target,
    QuantizationParams, quantization_scheme, bfloat16_scheme, CalibrationMethod,
    TensorTessellateParameters, TensorDRAMLayout,
)
from afe.load.importers.general_importer import onnx_source
from afe.ir.tensor_type import ScalarType
from afe.ir.node import node_is_tuple
from afe.core.utils import convert_data_generator_to_iterable
from sima_utils.data.data_generator import DataGenerator

# ImageNet preprocessing constants (ResNet-50 was trained with these).
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
INPUT_SHAPE = (1, 3, 224, 224)  # NCHW
EXAMPLE_ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = EXAMPLE_ROOT / "models" / "resnet50_model.onnx"
DEFAULT_CALIBRATION_DATASET = EXAMPLE_ROOT / "data" / "openimages_v7_images_and_labels.pkl"
DEFAULT_VALIDATE_IMAGE = EXAMPLE_ROOT / "data" / "golden_retriever_207.jpg"
DEFAULT_LABELS = EXAMPLE_ROOT / "data" / "imagenet_labels.txt"
PRECISION_CHOICES = ("auto", "bf16", "int8")

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("compile")


def preprocess(image: np.ndarray, size=(224, 224)) -> np.ndarray:
    """Resize to 224x224, scale to [0, 1], normalize. Returns HWC float32."""
    image = cv2.resize(image, size).astype(np.float32) / 255.0
    return ((image - IMAGENET_MEAN) / IMAGENET_STD).astype(np.float32)


def load_calibration_images(folder: str, num_samples: int) -> np.ndarray:
    """Read up to `num_samples` images from `folder` into an NHWC batch."""
    exts = (".jpg", ".jpeg", ".png", ".bmp")
    paths = [os.path.join(folder, f) for f in sorted(os.listdir(folder))
             if f.lower().endswith(exts)][:num_samples]
    if not paths:
        raise FileNotFoundError(f"No calibration images found in {folder}")
    images = [preprocess(cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB)) for p in paths]
    return np.stack(images)  # (N, 224, 224, 3) — the SDK expects NHWC


def load_calibration_dataset(path: Path, num_samples: int) -> np.ndarray:
    """Read calibration images from the generated Open Images pickle."""
    with path.open("rb") as file_obj:
        dataset = pickle.load(file_obj)

    images = dataset.get("data")
    if not isinstance(images, list) or not images:
        raise ValueError(f"Calibration dataset does not contain image data: {path}")
    if len(images) < num_samples:
        raise ValueError(
            f"Calibration dataset has {len(images)} image(s), but {num_samples} were requested: {path}"
        )

    return np.stack([preprocess(image) for image in images[:num_samples]])


def run_helper(script: Path, *args: str) -> None:
    cmd = [sys.executable, str(script), *args]
    log.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(EXAMPLE_ROOT))


def ensure_default_model(model_path: Path) -> None:
    if model_path.is_file():
        return
    log.info("Model not found at %s; downloading and exporting ResNet-50.", model_path)
    run_helper(EXAMPLE_ROOT / "models" / "download_resnet50.py")
    if not model_path.is_file():
        raise FileNotFoundError(f"Model generation did not create expected file: {model_path}")


def calibration_dataset_size(dataset_path: Path) -> int:
    if not dataset_path.is_file():
        return 0
    with dataset_path.open("rb") as file_obj:
        dataset = pickle.load(file_obj)
    images = dataset.get("data") if isinstance(dataset, dict) else None
    if not isinstance(images, list):
        return 0
    return len(images)


def ensure_default_calibration_dataset(dataset_path: Path, num_samples: int) -> None:
    existing_samples = calibration_dataset_size(dataset_path)
    if existing_samples >= num_samples:
        return
    if existing_samples:
        log.info(
            "Calibration dataset at %s has %d samples; regenerating with %d samples.",
            dataset_path,
            existing_samples,
            num_samples,
        )
    else:
        log.info("Calibration dataset not found at %s; downloading Open Images samples.", dataset_path)
    run_helper(
        EXAMPLE_ROOT / "data" / "download_openimages_calibration.py",
        "--samples", str(num_samples),
        "--output", str(dataset_path),
    )
    generated_samples = calibration_dataset_size(dataset_path)
    if generated_samples < num_samples:
        raise RuntimeError(
            f"Calibration download created {generated_samples} image(s), "
            f"but {num_samples} were requested: {dataset_path}"
        )


def mla_tessellate_params(quant_model):
    """Map every MLA input to HWC and every MLA output to HWC16 (direct MLA)."""
    mla = quant_model._net.nodes["MLA_0"]
    in_tess = TensorTessellateParameters(
        tile_shape=(0, 0, 0, 0), enable_mla=True, dram_layout=TensorDRAMLayout.HWC)
    out_tess = TensorTessellateParameters(
        tile_shape=(0, 0, 0, 0), enable_mla=True, dram_layout=TensorDRAMLayout.HWC16)
    params = {name: in_tess for name in mla.input_names}
    out_node = mla.ir.nodes[mla.ir.output_node_name]
    out_names = out_node.input_node_names if node_is_tuple(out_node) else [out_node.name]
    for name in out_names:
        params[f"{name}_output"] = out_tess
    return params


def validate(sdk_net, image_path: str, labels_path: str, input_name: str) -> None:
    """Run the quantized model on one image and print the top-1 class."""
    with open(labels_path) as f:
        labels = [line.strip() for line in f]
    image = preprocess(cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB))
    output = sdk_net.execute(inputs={input_name: np.expand_dims(image, axis=0)})
    probabilities = output[0][0]
    idx = int(np.argmax(probabilities))
    name = labels[idx] if idx < len(labels) else "?"
    print("Validation image prediction:", flush=True)
    print(f"  class {idx}: '{name}' -> {100.0 * probabilities[idx]:.2f}%", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile your first model (ResNet-50 PTQ).")
    ap.add_argument(
        "--model",
        default=None,
        help=f"Path to the ResNet-50 ONNX model. Defaults to {DEFAULT_MODEL}.",
    )
    ap.add_argument(
        "--calib_images",
        default=None,
        help="Folder of calibration images. Defaults to generated Open Images calibration data.",
    )
    ap.add_argument("--output", default="./compiled_resnet50", help="Output directory.")
    ap.add_argument("--device", "--boardtype", default="modalix", choices=["modalix", "mlsoc"],
                    help="Target hardware (modalix=gen2, mlsoc=gen1).")
    ap.add_argument("--input_name", default="input", help="Model input tensor name.")
    ap.add_argument("--num_calib_samples", type=int, default=50, help="Calibration sample count.")
    ap.add_argument(
        "--precision",
        choices=PRECISION_CHOICES,
        default="auto",
        help="Quantization precision. Defaults to int8.",
    )
    ap.add_argument("--bf16", action="store_true", help="Compatibility alias for --precision bf16.")
    ap.add_argument("--validate", metavar="IMAGE",
                    help="Validate the quantized model on IMAGE (requires --labels).")
    ap.add_argument("--labels", help="ImageNet labels file, one class per line.")
    ap.add_argument("--no-mla-tessellation", action="store_false", dest="mla_tessellation",
                    help="Disable direct-MLA tessellation (use the EV74 reorder path).")
    ap.set_defaults(mla_tessellation=True)
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    target = gen2_target if args.device == "modalix" else gen1_target
    precision = "bf16" if args.bf16 else args.precision
    if precision == "auto":
        precision = "int8"
    if precision == "bf16" and args.device != "modalix":
        ap.error("BF16 is only supported for Modalix. Use --device modalix or --precision int8.")

    model_path = Path(args.model).expanduser().resolve() if args.model else DEFAULT_MODEL
    ensure_default_model(model_path)

    # 1. Load the ONNX model.
    importer = onnx_source(
        str(model_path),
        {args.input_name: INPUT_SHAPE},
        {args.input_name: ScalarType.float32},
    )
    loaded_net = load_model(importer, target=target)
    log.info("Loaded %s for %s", model_path, args.device)

    # 2. Prepare the calibration dataset.
    if args.calib_images:
        calib_images = load_calibration_images(args.calib_images, args.num_calib_samples)
    else:
        ensure_default_calibration_dataset(DEFAULT_CALIBRATION_DATASET, args.num_calib_samples)
        calib_images = load_calibration_dataset(DEFAULT_CALIBRATION_DATASET, args.num_calib_samples)
    calib_data = convert_data_generator_to_iterable(
        DataGenerator({args.input_name: calib_images}))
    log.info("Prepared %d calibration samples", len(calib_images))

    # 3. Quantize. INT8 is the default; BF16 remains explicit while compiler support matures.
    log.info("Quantizing with %s precision", precision.upper())
    if precision == "bf16":
        quant_configs = QuantizationParams(
            calibration_method=CalibrationMethod.from_str("mse"),
            activation_quantization_scheme=bfloat16_scheme(),
            weight_quantization_scheme=bfloat16_scheme(),
        )
    else:
        quant_configs = QuantizationParams(
            calibration_method=CalibrationMethod.from_str("mse"),
            activation_quantization_scheme=quantization_scheme(asymmetric=True, per_channel=False, bits=8),
            weight_quantization_scheme=quantization_scheme(asymmetric=False, per_channel=True, bits=8),
        )
    sdk_net = loaded_net.quantize(calib_data, quant_configs, model_name="quantized_resnet50")
    print("Quantization complete.", flush=True)

    # 4. (Optional) Validate accuracy.
    validate_image = Path(args.validate).expanduser().resolve() if args.validate else DEFAULT_VALIDATE_IMAGE
    labels_path = Path(args.labels).expanduser().resolve() if args.labels else DEFAULT_LABELS
    if validate_image.is_file() and labels_path.is_file():
        validate(sdk_net, str(validate_image), str(labels_path), args.input_name)
    elif args.validate or args.labels:
        ap.error("--validate and --labels must both point to existing files")

    # 5. Compile (MLA tessellation on by default).
    sdk_net.save(model_name="quantized_resnet50", output_directory=args.output)
    tess = mla_tessellate_params(sdk_net) if args.mla_tessellation else None
    if tess:
        log.info("MLA tessellation enabled (inputs HWC, outputs HWC16)")
    output_dir = Path(args.output).expanduser().resolve()
    print(f"Compiling model. Output directory: {output_dir}", flush=True)
    sdk_net.compile(output_path=args.output, tessellate_parameters=tess)
    compiled_archive = output_dir / "quantized_resnet50_mpk.tar.gz"
    if compiled_archive.is_file():
        print(f"Compiled MPK archive written to: {compiled_archive}", flush=True)
    else:
        archives = sorted(output_dir.glob("*_mpk.tar.gz"))
        if archives:
            print(f"Compiled MPK archive written to: {archives[-1]}", flush=True)
        else:
            print(f"Compiled model artifacts written to: {output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Наступні кроки.

Використовуйте скомпільований файл `.tar.gz` для створення вашого першого конвеєра виконання або продовжуйте вивчати
детальні посібники з **[квантування](./quantization.md)** та **[компіляції](./model-compilation.md)**.
