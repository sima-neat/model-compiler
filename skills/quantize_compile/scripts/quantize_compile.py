#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SiMa.ai Model Quantization and Compilation Utility
This script provides a command-line interface to quantize and compile machine learning models
for SiMa.ai Modalix hardware.

Key Features:
- Supports ONNX and PyTorch models.
- Automated ONNX simplification and shape inference.
- Flexible calibration data support (Dummy or Real images).
- Comprehensive quantization error analysis.
- Hardware-specific target optimizations.
"""

import argparse
import json
import logging
import os
import sys
import numpy as np
from PIL import Image
import torch
import onnx
from onnxsim import simplify

# SiMa Model Compiler Imports
from afe.apis.defines import (
    default_quantization, quantization_scheme,
    RequantizationMode, CalibrationMethod, bfloat16_scheme,
    InputName
)
from afe.load.importers.general_importer import onnx_source, pytorch_source
from afe.apis.loaded_net import load_model
from afe.apis.error_handling_variables import enable_verbose_error_messages
from afe.apis.release_v1 import get_model_sdk_version
from sima_utils.data.data_generator import DataGenerator
from afe.core.utils import convert_data_generator_to_iterable

# Custom Logger to bypass SDK interference
class PrintLogger:
    def info(self, msg):
        print(f"[INFO] {msg}")
        sys.stdout.flush()
    def warning(self, msg):
        print(f"[WARN] {msg}")
        sys.stdout.flush()
    def error(self, msg):
        print(f"[ERROR] {msg}")
        sys.stdout.flush()

logger = PrintLogger()

# Constants
_ONNX_IR_VERSION = 8
DIVIDER = "-" * 60


def build_quantization_manifest(*, bf16_activations, bf16_weights):
    """Describe the effective precision selected by the quantization config."""
    effective_bf16_activations = bf16_activations or bf16_weights
    return {
        "activation_precision": "bfloat16" if effective_bf16_activations else "int8",
        "weight_precision": "bfloat16" if bf16_weights else "int8",
        "device": "modalix",
    }


class ModelProcessor:
    def __init__(self, args):
        self.args = args
        self.input_shapes = (
            [tuple(map(int, shape.split(','))) for shape in args.input_shapes]
            if args.input_shapes else None
        )

        if args.model_format == "onnx":
            if args.input_names:
                raise ValueError(
                    "--input_names is only valid for PyTorch models. "
                    "ONNX inputs use the order stored in the graph."
                )
            model_proto = onnx.load(args.model_path)
            initializer_names = {
                initializer.name for initializer in model_proto.graph.initializer
            }
            model_inputs = [
                model_input for model_input in model_proto.graph.input
                if model_input.name not in initializer_names
            ]
            self.input_names = [model_input.name for model_input in model_inputs]

            if self.input_shapes is None:
                self.input_shapes = []
                for model_input in model_inputs:
                    shape = tuple(
                        dimension.dim_value if dimension.HasField("dim_value") else 0
                        for dimension in model_input.type.tensor_type.shape.dim
                    )
                    if any(dimension <= 0 for dimension in shape):
                        raise ValueError(
                            f"Input '{model_input.name}' has dynamic shape {shape}; "
                            "provide --input_shapes."
                        )
                    self.input_shapes.append(shape)
        else:
            if not args.input_names or self.input_shapes is None:
                raise ValueError(
                    "PyTorch models require --input_names and --input_shapes."
                )
            if args.model_layout != "NCHW":
                raise ValueError("PyTorch models require --model_layout NCHW.")
            self.input_names = args.input_names

        if len(self.input_names) != len(self.input_shapes):
            raise ValueError("--input_names and --input_shapes must contain the same number of inputs.")

        logger.info(f"Model inputs: {dict(zip(self.input_names, self.input_shapes))}")
        self.output_path = os.path.join(args.build_dir, os.path.splitext(os.path.basename(args.model_path))[0])
        os.makedirs(self.output_path, exist_ok=True)
        
        enable_verbose_error_messages()
        logger.info(DIVIDER)
        logger.info(f"Model Compiler Version: {get_model_sdk_version()}")
        logger.info(f"Python Version: {sys.version.split()[0]}")
        logger.info(f"Output Directory: {self.output_path}")
        logger.info(DIVIDER)

    @staticmethod
    def normalize_tensor(tensor, mean, std, layout='NCHW'):
        """Applies mean/std normalization to an image tensor scaled to [0, 1]."""
        tensor = torch.tensor(tensor).float() / 255.0
        
        ch_idx = 1 if layout == 'NCHW' else 3
        if len(tensor.shape) >= 4:
            channels = tensor.shape[ch_idx]
            
            # Adjust mean/std if they don't match the channel count
            # Use defaults (0 mean, 1 std) if dimensions mismatch
            if mean is not None and len(mean) != channels:
                mean = [0.0] * channels
            if std is not None and len(std) != channels:
                std = [1.0] * channels
                
            if mean is not None and std is not None:
                view_shape = [1] * 4
                view_shape[ch_idx] = channels
                mean_t = torch.tensor(mean).view(*view_shape)
                std_t = torch.tensor(std).view(*view_shape)
                tensor = (tensor - mean_t) / std_t
        return tensor

    def preprocess_image(self, image_path, input_shape=None):
        """Loads and prepares a single image for calibration."""
        target_shape = input_shape if input_shape is not None else self.input_shapes[0]
        if self.args.model_layout == 'NCHW':
            h, w = target_shape[2], target_shape[3]
        else:
            h, w = target_shape[1], target_shape[2]

        # Match the deployed CVU image preprocessor. Calibration with Pillow's
        # default bicubic resize shifts activation ranges from the runtime's
        # bilinear input distribution.
        image = Image.open(image_path).convert("RGB").resize(
            (w, h), resample=Image.Resampling.BILINEAR
        )
        image_np = np.array(image)
        # Permute to NCHW for normalization logic, then we'll flip back to NHWC if needed
        image_t = torch.tensor(image_np).permute(2, 0, 1).unsqueeze(0)
        return self.normalize_tensor(image_t, self.args.mean, self.args.std, 'NCHW')

    def prepare_onnx(self):
        """Simplifies ONNX model and enforces required versions/shapes."""
        logger.info(f"Preparing ONNX model: {self.args.model_path}")
        simplified_path = f"{os.path.splitext(self.args.model_path)[0]}_prepared.onnx"
        
        try:
            # Build input shapes dict for all inputs
            input_shapes_dict = {
                name: list(shape) 
                for name, shape in zip(self.input_names, self.input_shapes)
            }
            logger.info(f"Simplifying with fixed shapes: {input_shapes_dict}")
            
            # Simplify with fixed input shapes to eliminate dynamic Shape/Gather ops
            model_proto, check = simplify(
                self.args.model_path,
                overwrite_input_shapes=input_shapes_dict,
                dynamic_input_shape=False
            )
            if not check:
                raise ValueError("ONNX simplification validation failed")
            
            # Reset and fix input shapes
            for info in list(model_proto.graph.value_info):
                model_proto.graph.value_info.remove(info)
            
            # Update all inputs
            for input_tensor in model_proto.graph.input:
                if input_tensor.name in input_shapes_dict:
                    target_shape = input_shapes_dict[input_tensor.name]
                    input_tensor.type.tensor_type.shape.ClearField("dim")
                    for dim_size in target_shape:
                        dim = input_tensor.type.tensor_type.shape.dim.add()
                        dim.dim_value = dim_size
            
            model_proto = onnx.shape_inference.infer_shapes(model_proto)
            model_proto.ir_version = _ONNX_IR_VERSION

            onnx.save(model_proto, simplified_path)
            logger.info(f"Prepared model saved to: {simplified_path}")
            return simplified_path
        except Exception as e:
            logger.error(f"Failed to prepare ONNX: {e}")
            return self.args.model_path

    def get_calibration_data(self):
        """Generates dummy or real calibration data based on user input."""
        if not self.args.real_data:
            logger.info("Generating dummy calibration data...")
            data_dict = {}
            for name, shape in zip(self.input_names, self.input_shapes):
                dummy_raw = np.random.randint(0, 256, size=shape)
                data_in = self.normalize_tensor(dummy_raw, self.args.mean, self.args.std, self.args.model_layout).cpu().numpy()
                if self.args.model_layout == 'NCHW':
                     data_in = data_in.transpose(0, 2, 3, 1) # SDK expects NHWC
                data_dict[name] = data_in
            return [data_dict]
        
        logger.info(f"Loading real calibration data from: {self.args.dataset_images}")
        image_exts = (".jpg", ".jpeg", ".png", ".bmp")
        image_paths = sorted(
            os.path.join(self.args.dataset_images, f)
            for f in os.listdir(self.args.dataset_images)
            if f.lower().endswith(image_exts)
        )[:self.args.num_calib_samples]
        
        if not image_paths:
            raise FileNotFoundError(f"No valid images found in {self.args.dataset_images}")

        # Feed the same image set to all model inputs.
        # If input shapes differ, each input receives the same source images resized to its own shape.
        inputs_dict = {}
        for input_name, input_shape in zip(self.input_names, self.input_shapes):
            calib_images = torch.stack(
                [self.preprocess_image(p, input_shape=input_shape) for p in image_paths]
            ).squeeze(1)
            # SDK expects NHWC input shape
            inputs_dict[InputName(input_name)] = calib_images.cpu().numpy().transpose(0, 2, 3, 1)
        return convert_data_generator_to_iterable(DataGenerator(inputs_dict))

    def run(self):
        model_path = self.args.model_path
        if self.args.model_format == 'onnx' and self.args.simplify:
            model_path = self.prepare_onnx()

        # Step 1: Import and Load
        if self.args.model_format == "onnx":
            shape_dict = (
                dict(zip(self.input_names, self.input_shapes))
                if self.args.input_shapes else None
            )
            source = onnx_source(
                model_path,
                shape_dict=shape_dict,
                layout=self.args.model_layout,
            )
        else:
            source = pytorch_source(model_path, self.input_names, self.input_shapes)

        loaded_net = load_model(source)
        logger.info("Model successfully loaded for Modalix")

        # Step 2: Quantization
        logger.info("Initializing quantization...")
        calib_data = self.get_calibration_data()
        rq_mode = (
            RequantizationMode.sima
            if self.args.requant_mode == "sima"
            else RequantizationMode.tflite
        )
        calib_method = CalibrationMethod.from_str(self.args.calib_method)

        if self.args.bf16_activations or self.args.bf16_weights: # if weights are bf16, activations must be too
            act_scheme = bfloat16_scheme()
        else:
            act_scheme = quantization_scheme(True, False, 8)

        if self.args.bf16_weights:
            weight_scheme = bfloat16_scheme()
        else:
            weight_scheme = quantization_scheme(False, True, 8)

        quantization_manifest = build_quantization_manifest(
            bf16_activations=self.args.bf16_activations,
            bf16_weights=self.args.bf16_weights,
        )

        quant_config = default_quantization.with_activation_quantization(act_scheme) \
                                   .with_weight_quantization(weight_scheme) \
                                   .with_requantization_mode(rq_mode) \
                                   .with_calibration(calib_method)

        # Derive model name from the source file
        model_basename = os.path.splitext(os.path.basename(self.args.model_path))[0]
        
        quant_model = loaded_net.quantize(
            calibration_data=calib_data,
            quantization_config=quant_config,
            model_name=model_basename,
            log_level=logging.INFO
        )

        if self.args.analyse_error:
            logger.info("Analyzing quantization error (this may take a while)...")
            quant_model.analyze_quantization_error(evaluation_data=calib_data, error_metric="mae", local_feed=True)

        quant_model.save(model_name=model_basename, output_directory=self.output_path)
        logger.info("Quantized model saved.")

        # Step 3: Compilation
        if self.args.compile:
            logger.info(f"Compiling for Modalix with batch size {self.args.batch_size}...")
            quant_model.compile(
                output_path=self.output_path,
                batch_size=self.args.batch_size,
                log_level=logging.INFO
            )
            manifest_path = os.path.join(self.output_path, "quantization_manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as manifest_file:
                json.dump(quantization_manifest, manifest_file, indent=2, sort_keys=True)
                manifest_file.write("\n")
            logger.info(f"Quantization manifest saved to: {manifest_path}")
            logger.info("Compilation complete.")

        # Step 4: Verification
        if self.args.verify:
            logger.info("Running execution comparison verification...")
            test_inputs = {}
            for name, shape in zip(self.input_names, self.input_shapes):
                # Always test with a single sample
                test_shape = (1, *shape[1:])
                raw_test = np.random.randint(0, 256, size=test_shape)
                test_data = self.normalize_tensor(raw_test, self.args.mean, self.args.std, self.args.model_layout).cpu().numpy()
                if self.args.model_layout == 'NCHW':
                     # Ensure channel-last for SDK execution
                     test_data = test_data.transpose(0, 2, 3, 1)
                test_inputs[InputName(name)] = test_data
                logger.info(f"Prepared test input '{name}' with shape {test_data.shape}")

            logger.info("Executing quantized model...")
            quant_out = quant_model.execute(inputs=test_inputs)
            
            logger.info("Executing floating point model...")
            fp_out = loaded_net.execute(inputs=test_inputs)

            if not fp_out or not quant_out:
                logger.warning("Execution returned no outputs!")

            # Check output counts
            fp_out = list(fp_out)
            quant_out = list(quant_out)
            logger.info(f"Got {len(fp_out)} outputs from FP model and {len(quant_out)} from Quant model.")

            for i, (f_out, q_out) in enumerate(zip(fp_out, quant_out)):
                diff = np.abs(f_out - q_out)
                logger.info(f"Output {i}:")
                logger.info(f"  Max Absolute Diff: {np.max(diff):.6f}")
                logger.info(f"  Mean Absolute Diff: {np.mean(diff):.6f}")

def main():
    parser = argparse.ArgumentParser(description="SiMa.ai Comprehensive Model Quantization & Compilation")
    
    # Model Metadata
    parser.add_argument("--model_path", required=True, help="Path to input model")
    parser.add_argument(
        "--model_format",
        default="onnx",
        choices=["onnx", "pytorch"],
        help="Source format",
    )
    parser.add_argument("--model_layout", default="NCHW", choices=["NCHW", "NHWC"], help="Input tensor layout")
    parser.add_argument(
        "--input_names",
        nargs="+",
        help="Input names (PyTorch only; ONNX uses graph order)",
    )
    parser.add_argument(
        "--input_shapes",
        nargs="+",
        help="Input shapes (required for PyTorch or dynamic ONNX; ONNX uses graph order)",
    )
    
    # Workflow Flags
    parser.add_argument("--build_dir", default="./build", help="Target directory for artifacts")
    parser.add_argument("--no-simplify", action="store_false", dest="simplify", help="Disable ONNX simplification")
    parser.add_argument("--no-compile", action="store_false", dest="compile", help="Skip the compilation step")
    parser.add_argument("--analyse-error", action="store_true", help="Perform per-layer error analysis")
    parser.add_argument("--verify", action="store_true", default=False, help="Run bit-accuracy comparison")
    
    # Quantization Settings
    parser.add_argument("--bf16-weights", action="store_true", help="Use BFloat16 for weights")
    parser.add_argument("--bf16-activations", action="store_true", help="Use BFloat16 for activations")
    parser.add_argument("--calib_method", default="mse", help="Calibration method (mse, entropy, etc.)")
    parser.add_argument(
        "--requant_mode",
        default="sima",
        choices=["sima", "tflite"],
        help="INT8 requantization mode (sima is faster; tflite may improve accuracy)",
    )
    
    # Calibration Data
    parser.add_argument("--real_data", action="store_true", help="Use images for calibration")
    parser.add_argument("--dataset_images", default="./calib_images", help="Path to calibration images")
    parser.add_argument("--num_calib_samples", type=int, default=50, help="Max images for calibration")
    
    # Normalization
    parser.add_argument("--mean", type=float, nargs=3, default=[0, 0, 0], help="Image mean (RGB)")
    parser.add_argument("--std", type=float, nargs=3, default=[1, 1, 1], help="Image standard deviation (RGB)")

    # Advanced SDK Tweaks
    parser.add_argument("--batch_size", type=int, default=1, help="Compilation batch size")

    args = parser.parse_args()
    processor = ModelProcessor(args)
    processor.run()

if __name__ == "__main__":
    main()
