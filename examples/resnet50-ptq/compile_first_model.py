#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Compile your first model — ResNet-50 PTQ end-to-end.

Loads an ONNX ResNet-50, calibrates on a folder of images, quantizes to INT8
(or BF16), optionally validates accuracy, and compiles to an MPK ``.tar.gz``.

MLA tessellation is **enabled by default** (inputs HWC, outputs HWC16, driven
directly to/from the MLA, bypassing the EV74 reorder unit). Disable it with
``--no-mla-tessellation`` if your pipeline needs the EV74 reorder path.

Example:
    python3 compile_first_model.py --boardtype modalix
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
    sdk_net.compile(output_path=args.output, tessellate_parameters=tess)
    log.info("Compiled MPK archive written to %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
