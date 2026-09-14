---
name: sima-model-optimization
description: Optimize an MLA-compatible source or ONNX graph before quantization and compilation using reviewed structural rewrites and numerical equivalence checks. Use model surgery instead for unsupported operators or output-contract compatibility.
---

# Optimize Models for SiMa MLA

## Purpose

Use after the model-surgery audit confirms MLA compatibility. Find structural
inefficiencies without requiring a full compilation, apply matching patterns
from `references/optimization_patterns.md`, and preserve model behavior.

## Workflow

1. Inspect the source model and ONNX graph, including static shapes, dtypes,
   opset, initializers, and output contracts.
2. Confirm that the exact graph passes the `model_surgery` operator audit.
3. Read `references/optimization_patterns.md` and match patterns using each
   pattern's conditions and guardrails.
4. Prefer a source-model change when it is maintainable; otherwise make the
   smallest equivalent ONNX rewrite.
5. Validate the optimized graph and report applied patterns, equivalence
   results, and benefits that still require compilation or measurement.

## Rules

- Full MLA placement does not prove that a graph is optimally represented.
- Apply an optimization only when all `Match` conditions hold.
- Preserve externally visible input and output contracts unless the user
  explicitly requests a contract change.
- For detection, pose, segmentation, or SuperPoint outputs, preserve the
  BoxDecode contract in `../model_surgery/references/boxdecode.md`.
- Do not claim a latency, throughput, or memory improvement from graph structure
  alone when the benefit depends on compiler scheduling or hardware behavior.
- Rely on current compiler defaults for automatic layout conversion,
  tessellation, and any-shape-on-MLA unless a reviewed pattern says otherwise.

## Validation

At minimum:

- run the ONNX checker and shape inference when applicable;
- compare original and optimized outputs with representative inputs;
- state the tolerance or task-level metric used;
- rerun the `model_surgery` operator audit.

Compile or benchmark when the user needs measured performance, when a pattern is
hardware-dependent, or before presenting an estimated benefit as confirmed.
