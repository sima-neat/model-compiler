# Quantize and Compile Standard ONNX Models for SiMa

## Purpose
Use `skills/quantize_compile/scripts/quantize_compile.py` to quantize and compile standard ONNX models for SiMa (`modalix` or `davinci`).

## Use When
- You have an ONNX model and need SiMa quantized/compiled artifacts.
- You want a default, repeatable flow for Codex or Claude agents.

## Prerequisites
- `sima-frontend` installed (provides `afe` modules).
- Python deps: `onnx`, `onnxsim`, `torch`, `numpy`, `Pillow`.

If required deps are missing:
```bash
sima-cli login
sima-cli install sdk-extensions/model
```

## Default Workflow
1. Validate model path and input/output interface.
2. Run quantization (with ONNX simplification enabled by default).
3. Compile for target device.
4. Optionally run verification (`--verify`).

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
- `--mla-tesselation` exists for advanced MLA direct mode (argument spelling is `tesselation` in the script).
