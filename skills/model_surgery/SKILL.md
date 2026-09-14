---
name: sima-model-surgery
description: Make source-model or ONNX compatibility changes for SiMa MLA, including unsupported operators or attributes, BoxDecode output contracts, YOLO surgery, and validation against supported_operators.json. Use model optimization instead for performance-only rewrites of an already compatible graph.
---

# General Model Surgery for SiMa MLA

## Purpose
Use this skill to inspect a model, apply the smallest required compatibility
changes, and validate that it can proceed to quantization and compilation.

This skill generalizes the model surgery approach into one repeatable workflow:
- detect unsupported or risky operators first,
- prefer source-model rewrites when the Python model code is available,
- edit exported ONNX directly when source rewrites are not practical,
- apply focused compatibility rewrites,
- validate topology, operator support, and numerical behavior again.

## Use When
- A model fails quantization/compile due to unsupported ops or constraints.
- A YOLO model needs compatibility or an output-contract rewrite before compile.
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
- `skills/model_surgery/data/supported_operators.json` is the sole operator-support source used by the guard and generated customer documentation.
- Database keys must match canonical ONNX `node.op_type` names exactly. Keep engineering and customer-facing constraints together in `sima_hw_sw_constraints` and `customer_constraints`, and record 5D support explicitly in `fived`.
- The database covers canonical ONNX operators only. Document multi-node MLA patterns, such as RMSNorm through opset 22, in `references/composite_patterns.md`.
- After changing operator metadata, run `python3 scripts/build_supported_operators_md.py` from the repository root and include the regenerated compatibility page.

## Workflow
1. Inspect the available artifacts: source Python model, exported ONNX, compiler logs, and target dtype/platform.
2. For detection, pose, segmentation, or SuperPoint models, read `references/boxdecode.md` and confirm if the installed Neat version has a matching `BoxDecodeType` and the exported heads satisfy its contract.
3. Run `audit-model` on the exported ONNX before surgery or compilation.
4. Check `references/composite_patterns.md` for relevant MLA composite patterns; the node-level audit cannot verify fusion.
5. Build a surgery plan from unsupported ops, composite-pattern requirements, output-graph needs, and support DB notes/constraints.
6. Prefer changing the source model code and re-exporting when that is available and simpler to maintain.
7. Otherwise, apply the smallest safe ONNX graph edits.
8. Re-audit, run ONNX checks, and compare original vs modified inference outputs.
9. Hand model to quantize/compile flow.

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
- If an op is unsupported, consult `notes` and `sima_hw_sw_constraints` in `supported_operators.json` first.
- For MLA composite-pattern requirements, see `references/composite_patterns.md`.
- For rewrites of unsupported operator forms or attributes, see
  `references/compatibility_patterns.md`.

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
