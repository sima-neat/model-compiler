---
title: Compile Your First Model
sidebar_position: 2
---

# Compile Your First Model

This walkthrough takes a **ResNet-50** ONNX model end-to-end through the
Model SDK's **Post-Training Quantization (PTQ)** workflow and produces a
compiled `.tar.gz` MPK archive ready for the Neat runtime.

PTQ is an efficient, straightforward way to shrink a model and speed up
inference with minimal accuracy loss. The workflow is:

1. **Load** the model.
2. **Quantize** it to `int8` (or `bf16`).
3. **Validate** its accuracy.
4. **Compile** it for execution on the MLSoC.

## Prerequisites

- `sima-cli` installed (see the [official guide](https://docs.sima.ai/pages/sima_cli/main.html)).
- The Model SDK environment. Enter it with:

```bash
sima-cli sdk model
```

## Get the example

Inside the Model SDK container, install the ResNet-50 demo with `sima-cli`. It
provides everything you need to run end-to-end — the ONNX model, a calibration
image set, the ImageNet labels, and a ready-to-run virtual environment:

```bash
cd /home/docker/sima-cli/
sima-cli install assets/demos/compile-resnet50-model
```

Activate the environment and run the example:

```bash
source ptq-example/.env/bin/activate
cd ptq-example/src/modelsdk_quantize_model
python3 resnet50_quant.py --boardtype modalix   # or: mlsoc
```

The run ends with a correctly classified Golden Retriever (ImageNet class 207)
and a compiled archive:

```text
***** Test Inference on a Golden Retriever (Class 207) *****
[5] --> 207: 'golden retriever' -> 98.82%

***** Compiling Model for MODALIX *****
***** Compiled Model at .../models/compiled_resnet50 *****
quantized_resnet50_mpk.tar.gz
```

Use the resulting `.tar.gz` with `mpk project create` to scaffold an MPK
project, or import it into Edgematic to build an application.

The sections below explain what the script does at each stage, and the
[full script](#full-script) is listed at the end. MLA tessellation is **enabled
by default** so the compiled model feeds the accelerator directly (see
[Compilation → Tessellation](./compilation.md#tessellation)).

## How it works

### 1. Load the model

The first step is to load an ONNX ResNet-50 into the SDK's internal
representation.

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

Quantization needs a small, representative calibration dataset to determine the
scaling factors that map FP32 values into the limited integer range without
clipping or excessive precision loss. Calibrating on real input distributions
preserves important activations while reducing compute cost.

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

A few dozen representative images are typically enough for calibration.

### 3. Quantize

With the model loaded and the calibration data prepared, quantize to INT8:

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

Here activations use 8-bit asymmetric per-tensor quantization and weights use
8-bit symmetric per-channel quantization. For BF16 and calibration options, see
**[Quantization](./quantization.md)**.

### 4. Validate accuracy

Before compiling, confirm the quantized model still classifies correctly by
executing it in software with `sdk_net.execute(...)`:

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

A correct, high-confidence prediction (e.g. `207 'golden retriever' -> 98.82%`)
confirms preprocessing and quantization are sound. A misclassification points to
a preprocessing mismatch or a quantization issue worth retuning.

### 5. Compile

Once you are satisfied, save and compile the model:

```python
sdk_net.save(model_name="quantized_resnet50", output_directory=MODELS_PATH)
sdk_net.compile(output_path=f"{MODELS_PATH}/compiled_resnet50")
```

The output is a `.tar.gz` archive containing the compiled MLA program(s), an
`_mpk.json` metadata file, and an execution-statistics file. See
**[Compilation](./compilation.md)** for the full archive contents, batch sizing,
and tessellation options.

## Full script

The complete, annotated program is below. It is also available in the
model-sdk repo as
[`examples/compile_first_model.py`](https://github.com/sima-neat/model-sdk/blob/main/examples/compile_first_model.py).
Unlike the bundled demo above, this version runs against **your own** ONNX model
and a folder of calibration images:

```bash
python3 examples/compile_first_model.py \
  --model resnet50.onnx \
  --calib_images ./calib_images \
  --device modalix \
  --output ./compiled_resnet50
# optional accuracy check:
#   --validate golden_retriever_207.jpg --labels imagenet_labels.txt
```

```python
#!/usr/bin/env python3
"""Compile your first model — ResNet-50 PTQ end-to-end.

Loads an ONNX ResNet-50, calibrates on a folder of images, quantizes to INT8
(or BF16), optionally validates accuracy, and compiles to an MPK .tar.gz.

MLA tessellation is enabled by default (inputs HWC, outputs HWC16, driven
directly to/from the MLA, bypassing the EV74 reorder unit). Disable it with
--no-mla-tessellation if your pipeline needs the EV74 reorder path.
"""

import argparse
import logging
import os

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

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("compile_first_model")


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
    ap.add_argument("--model", required=True, help="Path to the ResNet-50 ONNX model.")
    ap.add_argument("--calib_images", required=True, help="Folder of calibration images.")
    ap.add_argument("--output", default="./compiled_resnet50", help="Output directory.")
    ap.add_argument("--device", default="modalix", choices=["modalix", "mlsoc"],
                    help="Target hardware (modalix=gen2, mlsoc=gen1).")
    ap.add_argument("--input_name", default="input", help="Model input tensor name.")
    ap.add_argument("--num_calib_samples", type=int, default=50, help="Calibration sample count.")
    ap.add_argument("--bf16", action="store_true", help="Quantize to BF16 (Modalix) instead of INT8.")
    ap.add_argument("--validate", metavar="IMAGE",
                    help="Validate the quantized model on IMAGE (requires --labels).")
    ap.add_argument("--labels", help="ImageNet labels file, one class per line.")
    ap.add_argument("--no-mla-tessellation", action="store_false", dest="mla_tessellation",
                    help="Disable direct-MLA tessellation (use the EV74 reorder path).")
    ap.set_defaults(mla_tessellation=True)
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    target = gen2_target if args.device == "modalix" else gen1_target

    # 1. Load the ONNX model.
    importer = onnx_source(
        args.model,
        {args.input_name: INPUT_SHAPE},
        {args.input_name: ScalarType.float32},
    )
    loaded_net = load_model(importer, target=target)
    log.info("Loaded %s for %s", args.model, args.device)

    # 2. Prepare the calibration dataset.
    calib_images = load_calibration_images(args.calib_images, args.num_calib_samples)
    calib_data = convert_data_generator_to_iterable(
        DataGenerator({args.input_name: calib_images}))
    log.info("Prepared %d calibration samples", len(calib_images))

    # 3. Quantize (INT8 by default; BF16 with --bf16).
    if args.bf16:
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
    log.info("Quantization complete")

    # 4. (Optional) Validate accuracy.
    if args.validate:
        if not args.labels:
            ap.error("--validate requires --labels")
        validate(sdk_net, args.validate, args.labels, args.input_name)

    # 5. Compile (MLA tessellation on by default).
    sdk_net.save(model_name="quantized_resnet50", output_directory=args.output)
    tess = mla_tessellate_params(sdk_net) if args.mla_tessellation else None
    if tess:
        log.info("MLA tessellation enabled (inputs HWC, outputs HWC16)")
    sdk_net.compile(output_path=args.output, tessellate_parameters=tess)
    log.info("Compiled MPK archive written to %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Next steps

Use the compiled `.tar.gz` to build your first runtime pipeline, or continue to
the in-depth **[Quantization](./quantization.md)** and **[Compilation](./compilation.md)**
guides.
