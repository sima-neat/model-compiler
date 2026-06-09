---
name: sima-model-quantize-compile
description: Use when quantizing and compiling a standard ONNX model for the SiMa platform, including dependency bootstrap via sima-cli, optional real-data calibration, verification, and target-specific compilation for modalix or davinci.
---

# Quantize and Compile Standard ONNX Models for SiMa

## Purpose
Use `skills/quantize_compile/scripts/quantize_compile.py` to quantize and compile standard ONNX models for SiMa (`modalix` or `davinci`).

## Use When
- You have an ONNX model and need SiMa quantized/compiled artifacts.
- You want a default, repeatable flow for Codex or Claude agents.

## Prerequisites
- you must activate the Model Compiler virtual environment first:
```bash
activate-model-sdk
```
- Ensure `sima-frontend` installed (provides `afe` modules).
- Python deps: `onnx`, `onnxsim`, `torch`, `numpy`, `Pillow` must be available in the environment.

If required deps are missing:
```bash
sima-cli login
sima-cli install sdk-extensions/model
```

## Default Workflow
1. Run operator audit first (required gate before quantize/compile; use `model_surgery` policy).
2. Validate model path and input/output interface.
3. If model has symbolic dimensions, staticify/simplify it with `model_surgery` helper.
4. Run quantization (with ONNX simplification enabled by default).
5. Compile for target device.
6. Optionally run verification (`--verify`).

## Pre-Compile Audit (Required)
Run graph compatibility audit before quantization/compilation, following
`skills/model_surgery/SKILL.md` target/dtype policy.

Typical command:
```bash
python3 skills/model_surgery/scripts/model_surgery_guard.py audit-model \
  --model /abs/path/model.onnx \
  --dtype int8
```

## Default Command
```bash
python3 skills/quantize_compile/scripts/quantize_compile.py \
  --model_path /abs/path/model.onnx \
  --model_format onnx \
  --device modalix \
  --build_dir ./build
```

## Recommended Reproducible Command
```bash
python3 skills/quantize_compile/scripts/quantize_compile.py \
  --model_path /abs/path/model.onnx \
  --model_format onnx \
  --input_names input \
  --input_shapes 1,3,224,224 \
  --output_names output \
  --device davinci \
  --build_dir ./build \
  --real_data \
  --dataset_images /abs/path/calib_images \
  --num_calib_samples 50 \
  --calib_method mse \
  --requant_mode sima \
  --verify
```

## Key Flags
- `--device {modalix|davinci}`
- `--input_names --input_shapes --output_names`
- `--real_data --dataset_images --num_calib_samples`
- `--bf16-weights --bf16-activations`
- `--calib_method --requant_mode`
- `--verify`, `--analyse-error`
- `--no-compile` for quantize-only runs

## Output
Artifacts are written to:
- `<build_dir>/<model_basename>/`

## Notes
- Auto-shape detection may fail on dynamic ONNX inputs; pass explicit `--input_shapes`.
- For symbolic/dynamic ONNX dimensions, run:
```bash
python3 skills/model_surgery/scripts/onnx_static_simplify.py \
  --input /abs/path/model.onnx \
  --output /abs/path/model.static.sim.onnx \
  --replace batch=1
```
- `--mla-tesselation` exists for advanced MLA direct mode (argument spelling is `tesselation` in the script).
