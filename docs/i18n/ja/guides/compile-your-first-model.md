---
title: "最初のモデルをコンパイルする"
sidebar_position: 1
---

# 最初のモデルをコンパイルする

このチュートリアルでは、**ResNet-50** ONNX モデルを Model Compiler を使用して、**Post-Training Quantization (PTQ)** ワークフローにかけます。その結果、`.tar.gz` 形式の MPK アーカイブが作成され、Neat ランタイムで使用できるようになります。

このワークフローは、以下の 4 つの段階で構成されます。

1. **モデルを読み込みます。**
2. デフォルトでは INT8 に量子化し、必要に応じて BF16 に量子化します。
3. **正確性を検証する**。
4. MLSoC 上で実行できるように、コンパイルしてください。

## 前提条件

- `sima-cli` がインストールされました（[sima-cli のセットアップガイド](https://github.com/sima-neat/sima-cli) を参照）。
- Model Compiler を、Neat SDK または Ubuntu ホストにインストールします。次に、以下を入力してください。
  次の環境で：

```bash
activate-model-compiler
```

## サンプルを入手する

Model Compiler がインストールされている Neat SDK または Ubuntu ホストで、`sima-cli` を使用して、Model Compiler のサンプルをインストールします。

```bash
sima-cli neat install model-compiler/examples
```

チュートリアルの最後まで、Model Compiler 環境をアクティブな状態に保ってください。

量子化とコンパイルのサンプルを実行します。このスクリプトは、ResNet-50 ONNX モデルを生成し、まだ存在しない場合は、公開されている Open Images のキャリブレーションデータをダウンロードします。

```bash
cd resnet50-ptq
python3 compile.py
```

検証用の入力データが与えられた場合、プログラムはゴールデン・レトリバーをImageNetのクラス207として分類し、コンパイルされたアーカイブを生成する必要があります。

```text
Validation image prediction:
  class 207: 'golden retriever' -> 98.82%
Quantization complete.
Compiling model. Output directory: .../compiled_resnet50
Compiled MPK archive written to: .../compiled_resnet50/quantized_resnet50_mpk.tar.gz
```

生成された`.tar.gz`ファイルを使用して、[精度とパフォーマンスを検証](./validate-accuracy-performance.md)するか、または、それを使用して[パイプラインアプリケーションを構築](/develop-apps/)します。

以下のセクションでは、各段階について説明します。[完全なスクリプト](#full-script)は、最後に示されます。MLAテッセレーションは**デフォルトで有効**になっているため、コンパイルされたモデルは直接アクセラレータに送られます。詳細は、[コンパイル > テッセレーション](./model-compilation.md#tessellation)を参照してください。

## 仕組み

### 1. モデルを読み込む

ONNX ResNet-50 モデルを SDK の内部表現に読み込みます。

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

入力テンソル `"input"` は、バッチサイズが1、3つのカラーチャネル、224×224ピクセルの形状 `(1, 3, 224, 224)` であり、型は `float32` です。`onnx_source` は、モデル（ONNX ファイル自体は変更されません）を読み込む方法を記述します。`load_model` は、モデルを量子化の準備ができた `LoadedNet` に変換します。`TARGET` はプラットフォームを選択します。MLSoC の場合は `gen1_target` を、Modalix の場合は `gen2_target` を選択します。

### 2. 校正データセットを準備する。

量子化には、小さく、代表的なキャリブレーションデータセットが必要です。このデータセットは、FP32値を整数範囲にマッピングするためのスケーリング係数を設定し、過剰なクリッピングや精度の低下を防ぎます。

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
`DataGenerator` に渡されるキャリブレーションデータは、**NHWC** 形式 (`[batch, height, width, channels]`) でなければなりません。これは、モデルへの入力テンソルが **NCHW** (`[batch, channels, height, width]`) 形式であっても同様です。この例のように、ONNX の入力形状が `(1, 3, 224, 224)` の場合です。上記の例では、すでに NHWC 形式が出力されます。これは、`preprocess` が HWC 形式の画像を出力するためです。前処理パイプラインで NCHW 形式の配列が生成される場合は、キャリブレーションデータセットを構築する前に、それらを転置してください。

```python
# Convert NCHW -> NHWC
calibration_images = np.transpose(calibration_images, (0, 2, 3, 1))
calib_data = convert_data_generator_to_iterable(
    DataGenerator({MODEL_INPUT_NAME: calibration_images}))
```
:::

デプロイメントのワークロードで使用するのと同じ入力分布から、代表的な画像を抽出して使用してください。

### 3. 量子化する

モデルを読み込み、キャリブレーションデータを準備した後、量子化を実行します。パッケージ化されたサンプルでは、デフォルトでINT8が使用されます。これは、広くサポートされている方法であるためです。INT8量子化中に、一部のモデルで飽和に関する警告が表示される場合があります。コンパイルされた出力を使用する前に、量子化されたモデルを検証してください。

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

この例では、活性化関数に対して 8 ビットの非対称テンソルごとの量子化を、重みに対して 8 ビットの対称チャネルごとの量子化を使用しています。BF16 およびキャリブレーションのオプションについては、**[量子化](./quantization.md)** を参照してください。

### 4. 正確性を検証する。

コンパイルする前に、量子化されたモデルをソフトウェアで実行し、`sdk_net.execute(...)` を使用して、依然として正しく分類できることを確認してください。

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

正確で信頼性の高い予測、例えば`207 'golden retriever' -> 98.82%`は、前処理と量子化が適切に調整されていることを示します。誤った分類は、通常、前処理の不整合または量子化の問題を示しており、再調整が必要です。

### 5. コンパイルする

検証に合格したら、モデルを保存してコンパイルしてください。

```python
sdk_net.save(model_name="quantized_resnet50", output_directory=args.output)
tess = mla_tessellate_params(sdk_net) if args.mla_tessellation else None
sdk_net.compile(output_path=args.output, tessellate_parameters=tess)
```

出力は、コンパイルされたMLAプログラム、`_mpk.json`メタデータファイル、および実行統計ファイルを含む`.tar.gz`形式のアーカイブです。アーカイブの内容、バッチサイズ、およびテッセレーションオプションについては、**[Compilation](./model-compilation.md)**を参照してください。

## 脚本全文

完全なアノテーション付きのプログラムは以下に示します。また、これは、`resnet50-ptq/compile.py`として、および[ResNet-50 PTQのサンプルソース](https://github.com/sima-neat/model-compiler/tree/main/examples/resnet50-ptq)として、モデルコンパイラのサンプルパッケージでも利用できます。GitHubで公開されています。

```bash
sima-cli neat install model-compiler/examples
cd resnet50-ptq
```

このスクリプトは、**お客様自身の** ONNX モデルと、キャリブレーション画像の入ったフォルダーに対して実行されます。

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

## 今後の手順

コンパイルされた`.tar.gz`ファイルを使用して、最初のランタイムパイプラインを構築するか、より詳細な**[量子化](./quantization.md)**と**[コンパイル](./model-compilation.md)**のガイドに進んでください。
