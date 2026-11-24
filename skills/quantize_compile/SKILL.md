---
name: sima-model-quantize-compile
description: Quantize and compile ONNX or PyTorch models that are not LLMs or VLMs (CNNs, detectors, segmentation, vision transformers, audio and other non-LLM models) for SiMa Modalix with the Model Compiler, covering INT8 or BF16 quantization, calibration, QAT QDQ exports, compilation and verification. Use when the user asks to quantize, calibrate, compile or verify such a model for Modalix or the MLA. Not for LLMs or VLMs, including quantize-and-compile or compile-only requests (use `sima-llima-compile-run`); operator audits or unsupported-operator rewrites (use `sima-model-surgery`); performance-only rewrites (use `sima-model-optimization`); triaging compiler failure reports or GitHub issues (use `sima-model-compiler-issue-triage`).
---

# Quantize and Compile Models for SiMa Modalix

Use `scripts/quantize_compile.py` for the standard local workflow. AFE selects
the Gen2 Modalix target and current layout, tessellation, any-shape-on-MLA, and
verification defaults. Gen1 is not supported.

## Paths

`<skill-dir>` below is the folder that holds this SKILL.md (for example
`~/.claude/skills/sima-model-quantize-compile` once installed). Run the helper
by its full `<skill-dir>/scripts/...` path so the commands work from the user's
own folder. Other Neat skills are installed next to this one, so the
`sima-model-surgery` skill's files are under `<skill-dir>/../sima-model-surgery/`.

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

LLMs and VLMs (Hugging Face or GGUF checkpoints such as Llama, Qwen, Gemma or
LLaVA) compile with LLiMa, not with this workflow: use the
`sima-llima-compile-run` skill, also when the request is to quantize and compile.

1. Validate the source path, format, and input/output contract.
2. If outputs will feed SiMa BoxDecode, read `references/boxdecode.md` in the
   `sima-model-surgery` skill before changing the graph.
3. For ONNX, resolve symbolic dimensions before compilation and run the
   operator audit from the `sima-model-surgery` skill. Treat its result as
   preliminary screening: inspect applicable constraints and do not claim MLA
   placement from the audit.

   ```bash
   python3 <skill-dir>/../sima-model-surgery/scripts/onnx_static_simplify.py \
     --input /abs/path/model.onnx \
     --output /abs/path/model.static.sim.onnx \
     --replace batch=1
   python3 <skill-dir>/../sima-model-surgery/scripts/model_surgery_guard.py audit-model \
     --model /abs/path/model.static.sim.onnx \
     --dtype int8
   ```

   Skip the simplifier when every dimension is already static, and audit again
   with `--dtype bfloat16` when BF16 matters. `model_surgery_guard.py query-op
   --op <Op>` shows one operator's constraints.
4. Use the `sima-model-surgery` skill when an incompatibility or BoxDecode
   contract change must be addressed.
5. Use the `sima-model-optimization` skill only when performance work is
   requested or a relevant bottleneck has been identified. Validate and
   re-screen any changed graph.
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
python3 <skill-dir>/scripts/quantize_compile.py \
  --model_path /abs/path/model.onnx \
  --model_format onnx \
  --build_dir ./build
```

PyTorch requires explicit names, shapes, and NCHW layout:

```bash
python3 <skill-dir>/scripts/quantize_compile.py \
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

- [QAT ONNX import and compilation](https://github.com/sima-neat/model-compiler/blob/main/docs/guides/quantization.md)
  (section "QAT exports")
- Quantize-and-compile helper source: `scripts/quantize_compile.py`
