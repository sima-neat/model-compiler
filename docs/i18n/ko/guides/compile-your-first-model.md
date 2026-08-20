---
title: "첫 번째 모델을 컴파일하세요."
sidebar_position: 1
---

# 첫 번째 모델을 컴파일하세요.

이 튜토리얼에서는 **ResNet-50** ONNX 모델을 Model Compiler를 사용하여 **사후 학습 양자화(PTQ)** 워크플로를 거칩니다. 결과는 Neat 런타임용으로 컴파일된 `.tar.gz` MPK 아카이브입니다.

이 워크플로는 네 단계로 구성됩니다.

1. **모델을 로드**합니다.
2. 기본적으로 INT8로 양자화하고, 요청 시에는 BF16으로 양자화합니다.
3. **정확성**을 확인하십시오.
4. MLSoC에서 실행할 수 있도록 컴파일하세요.

## 필수 조건

- `sima-cli`가 설치되었습니다([sima-cli 설정 가이드](https://github.com/sima-neat/sima-cli) 참조).
- Model Compiler 설치된 위치 Neat SDK 또는 Ubuntu 호스트에 설치합니다. 다음을 입력하세요.
  다음 환경에서:

```bash
activate-model-compiler
```

## 예제를 가져오세요.

Model Compiler가 설치된 Neat SDK 또는 Ubuntu 호스트에서 `sima-cli`를 사용하여 Model Compiler 예제를 설치합니다.

```bash
sima-cli neat install model-compiler/examples
```

튜토리얼의 나머지 부분에서는 Model Compiler 환경을 활성 상태로 유지하십시오.

양자화 및 컴파일 예제를 실행합니다. 이 스크립트는 ResNet-50 ONNX 모델을 생성하고, 필요한 경우 공개 Open Images 교정 데이터를 다운로드합니다.

```bash
cd resnet50-ptq
python3 compile.py
```

검증 입력이 제공되면 실행 과정에서 골든 리트리버 이미지를 ImageNet 클래스 207으로 분류하고, 컴파일된 아카이브를 생성해야 합니다.

```text
Validation image prediction:
  class 207: 'golden retriever' -> 98.82%
Quantization complete.
Compiling model. Output directory: .../compiled_resnet50
Compiled MPK archive written to: .../compiled_resnet50/quantized_resnet50_mpk.tar.gz
```

결과적으로 생성된 `.tar.gz` 파일을 사용하여 [정확도와 성능을 검증](./validate-accuracy-performance.md)하거나,
또는 이를 사용하여 [파이프라인 애플리케이션을 구축](/develop-apps/)할 수 있습니다.

다음 섹션에서는 각 단계를 설명합니다. [전체 스크립트](#full-script)는
마지막에 나타납니다. MLA 테셀레이션은 **기본적으로 활성화**되어 있으므로 컴파일된
모델이 가속기에 직접 전달됩니다. [컴파일 > 테셀레이션](./model-compilation.md#tessellation)을 참조하십시오.

## 작동 방식

### 1. 모델을 불러옵니다.

ONNX ResNet-50 모델을 SDK의 내부 표현 방식으로 로드합니다.

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

입력 텐서 `"input"`는 `(1, 3, 224, 224)` 형태를 가집니다. 즉, 배치 크기는 1, 색상 채널은 3개, 224x224 픽셀이며, 데이터 유형은 `float32`입니다. `onnx_source`는 모델을 읽는 방법을 설명합니다(실제 ONNX 파일은 변경되지 않음). `load_model`은 모델을 양자화를 위해 사용할 수 있는 `LoadedNet`으로 변환합니다. `TARGET`은 플랫폼을 선택합니다. MLSoC에는 `gen1_target`를, Modalix에는 `gen2_target`를 사용합니다.

### 2. 보정 데이터 세트를 준비합니다.

양자화에는 작고 대표적인 보정 데이터 세트가 필요합니다. 이 데이터 세트는 FP32 값을 정수 범위로 매핑하는 스케일링 요소를 설정하여 과도한 클리핑이나 정밀도 손실을 방지합니다.

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
`DataGenerator`에 전달되는 보정 데이터는 **NHWC** 레이아웃(`[batch, height, width, channels]`)으로 제공되어야 합니다. 모델의 입력 텐서가 **NCHW**(`[batch, channels, height, width]`)인 경우에도 마찬가지입니다. 예를 들어, ONNX 입력 형식이 `(1, 3, 224, 224)`인 경우입니다. 위의 예제는 이미 NHWC 형식을 생성합니다. 이는 `preprocess`가 HWC 이미지를 반환하기 때문입니다. 전처리 파이프라인에서 NCHW 배열을 생성하는 경우, 보정 데이터 세트를 생성하기 전에 배열을 전치해야 합니다.

```python
# Convert NCHW -> NHWC
calibration_images = np.transpose(calibration_images, (0, 2, 3, 1))
calib_data = convert_data_generator_to_iterable(
    DataGenerator({MODEL_INPUT_NAME: calibration_images}))
```
:::

배포할 워크로드와 동일한 입력 분포에서 대표적인 이미지를 사용하세요.

### 3. 양자화

모델을 로드하고 보정 데이터를 준비한 후 양자화를 수행합니다. 패키지 예제는 기본적으로 INT8을 사용하는데, 이는 널리 지원되는 방식이기 때문입니다. 일부 모델은 INT8 양자화 중에 포화 경고를 표시할 수 있습니다. 따라서 컴파일된 출력을 사용하기 전에 양자화된 모델을 검증하십시오.

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

이 예제에서는 활성화 값에 대해 8비트 비대칭 텐서별 양자화를 사용하고, 가중치에는 8비트 대칭 채널별 양자화를 사용합니다. BF16 및 보정 옵션에 대한 자세한 내용은 **[Quantization](./quantization.md)**를 참조하십시오.

### 4. 정확성 검증

컴파일하기 전에 양자화된 모델을 소프트웨어에서 `sdk_net.execute(...)`를 사용하여 실행하고, 여전히 올바르게 분류하는지 확인하세요.

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

정확하고 신뢰도가 높은 예측, 예를 들어 `207 'golden retriever' -> 98.82%`는 전처리 및 양자화가 올바르게 수행되었음을 나타냅니다. 오분류는 일반적으로 전처리 과정의 불일치 또는 재조정이 필요한 양자화 문제를 나타냅니다.

### 5. 컴파일

검증이 완료되면 모델을 저장하고 컴파일합니다.

```python
sdk_net.save(model_name="quantized_resnet50", output_directory=args.output)
tess = mla_tessellate_params(sdk_net) if args.mla_tessellation else None
sdk_net.compile(output_path=args.output, tessellate_parameters=tess)
```

결과는 다음과 같습니다. `.tar.gz` 컴파일된 MLA 프로그램이 포함된 아카이브입니다.
`_mpk.json` 메타데이터 파일과 실행 통계 파일입니다. 자세한 내용은 다음을 참조하십시오.[컴파일](./model-compilation.md)** 아카이브 콘텐츠, 배치 크기 및 테셀레이션 옵션에 대해.

## 전체 대본

완전한 주석이 추가된 프로그램은 아래에 있습니다. 또한, 이 프로그램은 `resnet50-ptq/compile.py`로, 그리고 [ResNet-50 PTQ 예제 소스](https://github.com/sima-neat/model-compiler/tree/main/examples/resnet50-ptq)로 GitHub에서 확인할 수 있습니다.

```bash
sima-cli neat install model-compiler/examples
cd resnet50-ptq
```

이 스크립트는 **사용자 지정** ONNX 모델과 보정 이미지 폴더를 대상으로 실행됩니다.

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

## 다음 단계

컴파일된 `.tar.gz` 파일을 사용하여 첫 번째 런타임 파이프라인을 구축하거나, 심층적인 **[양자화](./quantization.md)** 및 **[컴파일](./model-compilation.md)** 가이드로 계속 진행하세요.
