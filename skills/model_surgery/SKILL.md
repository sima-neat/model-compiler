---
name: sima-model-surgery
description: Use when analyzing or modifying model graphs for SiMa MLA compatibility or optimization, including source-model rewrites, ONNX surgery, YOLO graph optimization, unsupported-op detection, and post-surgery validation against supported_operators.json.
---

# General Model Surgery for SiMa MLA

## Purpose
Use this skill to inspect a model, choose the lowest-effort surgery path, apply targeted graph edits, and validate the result so it is more likely to quantize/compile and run efficiently on SiMa MLA.

This skill generalizes the model surgery approach into one repeatable workflow:
- detect unsupported or risky operators first,
- prefer source-model rewrites when the Python model code is available,
- edit exported ONNX directly when source rewrites are not practical,
- apply focused rewrites,
- validate topology, operator support, and numerical behavior again.

## Use When
- A model fails quantization/compile due to unsupported ops or constraints.
- A YOLO model needs compatibility or output-graph optimization before compile.
- You need a structured surgery loop before running compile.
- You want operator decisions grounded in `supported_operators.json`.

## Platform Note
- `bfloat16` operator support in this skill’s support DB is for `Modalix` platform only.
- For non-Modalix targets, use `int8` as the primary compatibility policy unless target-specific guidance says otherwise.
- If target is unspecified, assume `Modalix` and run both `int8` and `bfloat16` audits.

## Prerequisites
- Activate Model Compiler environment:
```bash
activate-model-compiler
```
- `onnx` must be available in the active Python env.
- `skills/model_surgery/data/supported_operators.json` is the default support DB used by the guard script.

## Workflow
1. Inspect the available artifacts: source Python model, exported ONNX, compiler logs, and target dtype/platform.
2. Run `audit-model` on the exported ONNX first (required gate) before surgery or compilation.
3. Build a surgery plan from unsupported ops, YOLO/output-graph needs, and support DB notes/constraints.
4. Prefer changing the source model code and re-exporting when that is available and simpler to maintain.
5. Otherwise, apply the smallest safe ONNX graph edits.
6. Re-audit, run ONNX checks, and compare original vs modified inference outputs.
7. Hand model to quantize/compile flow.

## Bundled Helpers
- Download model from URL or HF Hub:
```bash
python3 skills/model_surgery/scripts/download_onnx.py --url <onnx_url> --output-dir ./models
python3 skills/model_surgery/scripts/download_onnx.py --hf-repo <org/repo> --hf-file <model>.onnx --output-dir ./models
```
- Freeze symbolic dimensions and simplify:
```bash
python3 skills/model_surgery/scripts/onnx_static_simplify.py \
  --input /abs/path/model.onnx \
  --output /abs/path/model.static.sim.onnx \
  --replace batch=1 \
  --replace seq_len=256
```

## Operator Audit Command
```bash
python3 skills/model_surgery/scripts/model_surgery_guard.py audit-model \
  --model /abs/path/model.onnx \
  --dtype int8
```

Run this before any graph surgery and before quantize/compile.

Useful variants:
```bash
python3 skills/model_surgery/scripts/model_surgery_guard.py query-op --op Gather
python3 skills/model_surgery/scripts/model_surgery_guard.py list-supported --dtype bfloat16
```

Use `--dtype bfloat16` only when evaluating Modalix compatibility.

## Surgery Heuristics
- Prefer source-model rewrites when they are available; they are usually easier to review and keep across model updates.
- Prefer local, isolated edits over broad graph rewrites.
- Preserve tensor names/shape contracts at model outputs.
- For YOLO and repeated head/postprocess blocks, apply one rewrite pattern consistently and keep runtime output expectations explicit.
- If an op is unsupported, consult `notes` and `sima_hw_sw_constraints` in `supported_operators.json` first.
- For concrete rewrite examples, see `references/patterns.md`.

## Validation
After edits, run:
```bash
python3 skills/model_surgery/scripts/model_surgery_guard.py audit-model \
  --model /abs/path/model_surgery.onnx \
  --dtype int8 \
  --json
```

Also validate numerical behavior before compile:
- Run the original and modified model on the same representative inputs.
- For shape/layout rewrites that should preserve math, require numerical or near-numerical equivalence and report the tolerance used.
- For intentional math, output-format, or postprocess changes, compare model-level behavior instead and call out why exact tensor equivalence is not expected.
- If no representative input is available, say that numerical validation is incomplete instead of treating topology validation as sufficient.

Then run compile/verification using the quantize+compile skill.

## Notes
- This skill is architecture-agnostic; it does not hardcode YOLO-only node names.
- YOLO is a first-class use case because output/head rewrites can improve compiler compatibility and runtime integration.
- For family-specific pipelines, you can still reuse specialized surgeon logic, but keep the guardrail step from this skill.

## Reference
- `tool-model-to-pipeline` surgeons (tag `v2.0.0`), reference implementation patterns:
  `https://github.com/SiMa-ai/tool-model-to-pipeline/tree/v2.0.0/model_to_pipeline/surgeons`
- This skill remains self-contained; local `data/supported_operators.json` is the compatibility source of truth.
