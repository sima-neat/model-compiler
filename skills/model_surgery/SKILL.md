---
name: sima-model-surgery
description: Use when analyzing or modifying ONNX graphs for SiMa MLA compatibility, including unsupported-op detection, surgery planning, and post-surgery validation against supported_operators.json.
---

# General ONNX Model Surgery for SiMa MLA

## Purpose
Use this skill to perform graph surgery on ONNX models so they are more likely to quantize/compile on SiMa MLA.

This skill generalizes the model surgery approach used by `tool-model-to-pipeline` surgeons (`yolov8`, `yolov9`, `yolov10`, `yolo11`, `yolo11-seg`, `yolox`) into one repeatable workflow:
- detect unsupported or risky operators first,
- apply focused rewrites,
- validate topology and operator support again.

## Use When
- A model fails quantization/compile due to unsupported ops or constraints.
- You need a structured surgery loop before running compile.
- You want operator decisions grounded in `supported_operators.json`.

## Platform Note
- `bfloat16` operator support in this skill’s support DB is for `Modalix` platform only.
- For non-Modalix targets, use `int8` as the primary compatibility policy unless target-specific guidance says otherwise.
- If target is unspecified, assume `Modalix` and run both `int8` and `bfloat16` audits.

## Prerequisites
- Activate ModelSDK environment:
```bash
source ~/sdk-extensions/model-sdk/model-sdk-venv/bin/activate
```
- `onnx` must be available in the active Python env.
- `skills/model_surgery/data/supported_operators.json` is the default support DB used by the guard script.

## Workflow
1. Run `audit-model` first (required gate) before surgery or compilation.
2. Build surgery plan from unsupported ops and notes/constraints.
3. Apply smallest safe graph edits.
4. Re-audit and run ONNX checks/inference sanity test.
5. Hand model to quantize/compile flow.

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
- Prefer local, isolated edits over broad graph rewrites.
- Preserve tensor names/shape contracts at model outputs.
- For repeated head/postprocess blocks, apply one rewrite pattern consistently.
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

Then run compile/verification using the quantize+compile skill.

## Notes
- This skill is architecture-agnostic; it does not hardcode YOLO-only node names.
- For family-specific pipelines, you can still reuse specialized surgeon logic, but keep the guardrail step from this skill.

## Reference
- `tool-model-to-pipeline` surgeons (tag `v2.0.0`), reference implementation patterns:
  `https://github.com/SiMa-ai/tool-model-to-pipeline/tree/v2.0.0/model_to_pipeline/surgeons`
- This skill remains self-contained; local `data/supported_operators.json` is the compatibility source of truth.
