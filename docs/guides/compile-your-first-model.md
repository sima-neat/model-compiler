---
title: Compile Your First Model
sidebar_position: 1
---

# Compile Your First Model

This walkthrough takes a **ResNet-50** ONNX model through the Model Compiler
**Post-Training Quantization (PTQ)** workflow. The result is a compiled
`.tar.gz` MPK archive for the Neat runtime.

The workflow has four stages:

1. **Load** the model.
2. **Quantize** it to INT8 by default, or BF16 when requested.
3. **Validate** its accuracy.
4. **Compile** it for execution on the MLSoC.

## Prerequisites

- `sima-cli` installed (see the [sima-cli setup guide](https://github.com/sima-neat/sima-cli)).
- Model Compiler installed in the Neat SDK or on an Ubuntu host. Enter the
  environment with:

```bash
activate-model-compiler
```

## Get the example

On the Neat SDK or Ubuntu host where Model Compiler is installed, install the
Model Compiler examples with `sima-cli`:

```bash
sima-cli neat install model-compiler/examples
```

Keep the Model Compiler environment active for the rest of the walkthrough.

Run the quantize-and-compile example. The script generates the ResNet-50 ONNX
model and downloads public Open Images calibration data if they are not already
present:

```bash
cd resnet50-ptq
python3 compile.py
```

When validation inputs are provided, the run should classify a Golden Retriever
as ImageNet class 207 and produce a compiled archive:

```text
***** Test Inference on a Golden Retriever (Class 207) *****
[5] --> 207: 'golden retriever' -> 98.82%

***** Compiling Model for MODALIX *****
***** Compiled Model at .../models/compiled_resnet50 *****
quantized_resnet50_mpk.tar.gz
```

Use the resulting `.tar.gz` with `mpk project create` to create an MPK project,
or import it into Edgematic to build an application.

The following sections explain each stage. The [full script](#full-script)
appears at the end. MLA tessellation is **enabled by default**, so the compiled
model feeds the accelerator directly. See
[Compilation > Tessellation](./model-compilation.md#tessellation).

## How it works

### 1. Load the model

Load the ONNX ResNet-50 model into the SDK's internal representation.

```python
from afe.apis.loaded_net import load_model
from afe.apis.defines import gen1_target, gen2_target
from afe.load.importers.general_importer import onnx_source
from afe.ir.tensor_type import ScalarType

MODEL_PATH = "resnet50.onnx"
TARGET = gen2_target  # gen2_target = Modalix, gen1_target = MLSoC (Davinci)

# Model information
input_name, input_shape, input_type = ("input", (1, 3, 224, 224), ScalarType.float32)
input_shapes_dict = {input_name: input_shape}
input_types_dict = {input_name: input_type}

# Load the ONNX model
importer_params = onnx_source(str(MODEL_PATH), input_shapes_dict, input_types_dict)
loaded_net = load_model(importer_params, target=TARGET)
```

The input tensor `"input"` has shape `(1, 3, 224, 224)` — batch size one, three
color channels, 224×224 pixels — and type `float32`. `onnx_source` describes how
to read the model (the ONNX file itself is unchanged); `load_model` converts it
into a `LoadedNet` ready for quantization. `TARGET` selects the platform:
`gen1_target` for MLSoC, `gen2_target` for Modalix.

### 2. Prepare a calibration dataset

Quantization needs a small, representative calibration dataset. The dataset
sets scaling factors that map FP32 values into the integer range while avoiding
excessive clipping or precision loss.

```python
from sima_utils.data.data_generator import DataGenerator

MODEL_INPUT_NAME = "input"

def preprocess(image, input_shape=(224, 224)):
    """Resize to 224x224, scale to [0,1], and normalize with ImageNet stats."""
    mean = [0.485, 0.456, 0.406]
    stddev = [0.229, 0.224, 0.225]
    image = cv2.resize(image, input_shape)
    image = image / 255.0
    image = (image - mean) / stddev
    return image

# Build a DataGenerator from your calibration images and map the preprocessing.
images_generator = DataGenerator({MODEL_INPUT_NAME: calibration_images})
images_generator.map({MODEL_INPUT_NAME: preprocess})
```

Use representative images from the same input distribution as your deployment
workload.

### 3. Quantize

After you load the model and prepare calibration data, quantize it. The
packaged example defaults to INT8 because it is the broadly supported path.
Some models may emit saturation warnings during INT8 quantization; validate the
quantized model before using the compiled output:

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
    convert_data_generator_to_iterable(images_generator),
    quant_configs,
    model_name="quantized_resnet50",
    arm_only=False,
)
```

This example uses 8-bit asymmetric per-tensor quantization for activations and
8-bit symmetric per-channel quantization for weights. For BF16 and calibration
options, see
**[Quantization](./quantization.md)**.

### 4. Validate accuracy

Before you compile, run the quantized model in software with
`sdk_net.execute(...)` and confirm that it still classifies correctly:

```python
import numpy as np

def postprocess_output(output: np.ndarray):
    probabilities = output[0][0]
    max_idx = np.argmax(probabilities)
    return max_idx, probabilities[max_idx]

# A known image: a Golden Retriever is ImageNet class 207.
dog = preprocess(cv2.cvtColor(cv2.imread("golden_retriever_207.jpg"), cv2.COLOR_BGR2RGB))
pp = np.expand_dims(dog, axis=0).astype(np.float32)
label, score = postprocess_output(sdk_net.execute(inputs={"input": pp}))
print(f"class {label} -> {score:.2%}")   # expect 207 'golden retriever'
```

A correct, high-confidence prediction, such as
`207 'golden retriever' -> 98.82%`, confirms that preprocessing and
quantization are aligned. A misclassification usually indicates a preprocessing
mismatch or a quantization issue to retune.

### 5. Compile

After validation passes, save and compile the model:

```python
sdk_net.save(model_name="quantized_resnet50", output_directory=MODELS_PATH)
sdk_net.compile(output_path=f"{MODELS_PATH}/compiled_resnet50")
```

The output is a `.tar.gz` archive that contains the compiled MLA programs, an
`_mpk.json` metadata file, and an execution-statistics file. See
**[Compilation](./model-compilation.md)** for archive contents, batch sizing,
and tessellation options.

## Full script

The complete annotated program is below. It is also available in the Model
Compiler examples package as `resnet50-ptq/compile.py`:

```bash
sima-cli neat install model-compiler/examples
cd resnet50-ptq
```

The script runs against **your own** ONNX model and a folder of calibration
images:

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


def ensure_default_calibration_dataset(dataset_path: Path, num_samples: int) -> None:
    if dataset_path.is_file():
        return
    log.info("Calibration dataset not found at %s; downloading Open Images samples.", dataset_path)
    run_helper(
        EXAMPLE_ROOT / "data" / "download_openimages_calibration.py",
        "--samples", str(num_samples),
        "--output", str(dataset_path),
    )
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Calibration download did not create expected file: {dataset_path}")


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
    log.info("Prediction: %d '%s' -> %.2f%%", idx, name, 100.0 * probabilities[idx])


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

## Next steps

Use the compiled `.tar.gz` to build your first runtime pipeline, or continue to
the in-depth **[Quantization](./quantization.md)** and **[Compilation](./model-compilation.md)**
guides.
