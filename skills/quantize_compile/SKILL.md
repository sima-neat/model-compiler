---
name: sima-model-quantize-compile
description: Quantize and compile ONNX or PyTorch models for SiMa Modalix, including QAT QDQ exports, calibration, and verification.
---

# Quantize and Compile Models for SiMa Modalix

Use `scripts/quantize_compile.py` for the standard local workflow. AFE selects
the Gen2 Modalix target and current layout, tessellation, any-shape-on-MLA, and
verification defaults. Gen1 is not supported.

## Environment

Activate the Model Compiler environment:

```bash
activate-model-compiler
```

If it is unavailable, install the package for the host architecture with
`sima-cli neat install model-compiler/<amd64|arm64>`. The unqualified target
uses the latest published main artifact. Append `@develop` only when explicitly
testing the current develop compiler, or append a release tag to pin a release.

## Workflow

1. Validate the source path, format, and input/output contract.
2. If outputs will feed SiMa BoxDecode, read
   `../model_surgery/references/boxdecode.md` before changing the graph.
3. For ONNX, resolve symbolic dimensions before compilation and run the
   model-surgery operator audit. Treat its result as preliminary screening:
   inspect applicable constraints and do not claim MLA placement from the audit.
4. Use model surgery when an incompatibility or BoxDecode contract change must
   be addressed.
5. Use model optimization only when performance work is requested or a relevant
   bottleneck has been identified. Validate and re-screen any changed graph.
6. Quantize and compile for Modalix. Run verification when requested.

For PyTorch without an exported ONNX graph, the ONNX operator audit does not
apply. Do not claim compatibility before AFE import and compiler placement have
been inspected.

## Commands

This helper supports FP32 4D image inputs. For non-image or mixed-dtype models,
use the import API with matching input names, shapes, dtypes, and calibration
layout instead of this command.

ONNX input names are inferred from the model. Do not pass `--input_names` for
ONNX; runtime inputs use the order stored in the graph, excluding initializers.
Static shapes are inferred in that same order:

```bash
python3 skills/quantize_compile/scripts/quantize_compile.py \
  --model_path /abs/path/model.onnx \
  --model_format onnx \
  --build_dir ./build
```

PyTorch requires explicit names, shapes, and NCHW layout:

```bash
python3 skills/quantize_compile/scripts/quantize_compile.py \
  --model_path /abs/path/model.pt \
  --model_format pytorch \
  --model_layout NCHW \
  --input_names input \
  --input_shapes 1,3,224,224 \
  --build_dir ./build
```

For dynamic ONNX, pass one `--input_shapes` value per runtime input in graph
order. Calibration options include `--real_data`, `--dataset_images`,
`--num_calib_samples`, and `--calib_method`.
Precision options are `--bf16-weights` and `--bf16-activations`; workflow
options include `--verify`, `--analyse-error`, and `--no-compile`.

INT8 quantization defaults to `--requant_mode sima` for faster quantization.
If the resulting accuracy is insufficient, retry with
`--requant_mode tflite`; it is slower but may improve accuracy.

### QAT QDQ exports

For FP32 4D image QAT exports, use the default ONNX command with INT8 settings.
For non-image or mixed-dtype exports, use the import API as noted above.
Use the normal `load_model()` path and preserve QDQ hints; do not set internal
`is_quantized=True`.
Omit `--real_data` to supply random calibration placeholders: AFE retains
QDQ scales and zero points instead of re-estimating those ranges. Inputs must
match the model's interface and valid domain. Regions quantized without QDQ
hints need representative calibration data; accuracy checks need real data.

## Memory Errors

If compilation is killed or runs out of host memory, lower MLA simulator
parallelism and retry the same command:

```bash
export SIMA_MLA_SIM_PARALLEL=<lower-thread-count>
```

Lower values reduce peak memory but can increase compilation time. Do not
prescribe `1` by default.

## Completion

A compilation request is complete when the requested artifacts exist under
`<build_dir>/<model_basename>/` and requested verification has run. Report any
unverified accuracy, unresolved compatibility constraint, fallback placement,
or unmeasured performance claim instead of presenting it as confirmed.

## References

- [QAT ONNX import and compilation](../../docs/guides/quantization.md#qat-onnx-to-compiled-model)
- [Quantize-and-compile helper source](scripts/quantize_compile.py)
