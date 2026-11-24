---
name: sima-model-optimization
description: Speed up or shrink ONNX models that already run on the SiMa MLA (Modalix) with output-preserving graph rewrites, such as fusing Q/K/V or 1x1 projections, folding Transpose/Reshape chains, DepthToSpace for reshape shuffles, precomputing timestep embeddings and moving large embedding or codebook tables to the host, with BoxDecode outputs kept intact. Use when the user wants lower latency, higher FPS or throughput, or less memory with identical outputs, or compiler evidence shows a graph bottleneck, even before the model is shared. Not for unsupported operators, attribute limits or BoxDecode adaptation (use `sima-model-surgery`); a plain quantize-and-compile (use `sima-model-quantize-compile`); tuning the app or pipeline around the model (use `neat-application-builder`).
---

# Optimize Models for SiMa MLA

Use this skill when performance optimization is requested or compiler evidence
identifies a relevant bottleneck. Do not invoke it solely because a customer
asked to compile a model. Use the `sima-model-surgery` skill for
incompatibilities or BoxDecode output contracts.

## Compatibility Evidence

The model-surgery operator audit is preliminary screening only. It checks node
names and precision flags; it does not validate all attributes, shapes, opsets,
composite fusion, fallback, or placement. Before rewriting:

- inspect applicable `supported_operators.json` constraints (see Operator
  Screening);
- check relevant composite-pattern requirements; and
- use compiler placement evidence when full MLA residency matters.

Compilation is not required to apply a mathematically proven graph-only rewrite,
but it is required to confirm placement or a hardware-dependent benefit.

## Workflow

1. Establish the requested metric or identified bottleneck and preserve a
   baseline when measured improvement is required.
2. Inspect static shapes, dtypes, opset, initializers, output contracts, and
   available compiler evidence.
3. Screen the unmodified graph (simplified if needed) with the operator audit in the
   `sima-model-surgery` skill (see Operator Screening below) and note the
   constraints of every operator the rewrite will add or keep.
4. Read `references/optimization_patterns.md` and apply only patterns whose
   match conditions and guards are proven for the graph.
5. Prefer a maintainable source-model change; otherwise make the smallest
   equivalent ONNX rewrite.
6. Re-run the audit on the rewritten graph, validate behavior, and report
   applied patterns, equivalence results, screening results, and any benefit
   that still requires compilation or measurement.

## Operator Screening

The audit scripts and support database belong to the `sima-model-surgery`
skill, which is installed next to this one. `<skill-dir>` is the folder that
holds this SKILL.md, so that skill's files are under
`<skill-dir>/../sima-model-surgery/`. Activate the Model Compiler environment
(`activate-model-compiler`) first, then run the commands by full path from the
user's folder.

Freeze symbolic dimensions before screening, when the graph has any:

```bash
python3 <skill-dir>/../sima-model-surgery/scripts/onnx_static_simplify.py \
  --input /abs/path/model.onnx \
  --output /abs/path/model.static.sim.onnx \
  --replace batch=1
```

Replace `batch` with the model's own symbolic dimension names (one `--replace`
per name, read from the graph inputs) and check that the output reports
`Frozen dimensions:` above 0; with 0 the graph is still dynamic. Add
`--skip-simplify` when `onnxsim` is not installed; it only freezes the
dimensions.

Audit the simplified graph for INT8, and again with `--dtype bfloat16` when BF16
matters. Pass `/abs/path/model.onnx` instead only when every dimension was
already static and the simplifier was not needed:

```bash
python3 <skill-dir>/../sima-model-surgery/scripts/model_surgery_guard.py audit-model \
  --model /abs/path/model.static.sim.onnx \
  --dtype int8
```

For each operator a rewrite adds or keeps, read its attribute and shape
constraints, which the audit does not check:

```bash
python3 <skill-dir>/../sima-model-surgery/scripts/model_surgery_guard.py query-op --op <Op>
```

The same constraints are in that skill's `data/supported_operators.json`. If
`<skill-dir>/../sima-model-surgery/` does not exist, ask the user to install the
`sima-model-surgery` skill; do not guess repository paths.

## Rules

- Full MLA placement does not prove that a graph is optimally represented.
- Preserve public input/output contracts unless the user requests a change.
- When outputs feed BoxDecode, preserve the contract documented in
  `references/boxdecode.md` of the `sima-model-surgery` skill
  (`<skill-dir>/../sima-model-surgery/references/boxdecode.md`).
- Rely on current compiler layout, tessellation, and any-shape defaults unless a
  reviewed pattern requires otherwise.
- Do not claim latency, throughput, or memory gains from graph structure alone
  when the result depends on compiler scheduling or hardware behavior.

## Validation and Completion

Run the ONNX checker and shape inference when applicable, compare original and
optimized outputs on representative inputs, state the tolerance or task metric,
and repeat the preliminary operator/constraint screening.

A graph-only request delivers the changed graph, preserved contracts, and
equivalence evidence. A measured-performance request additionally delivers
baseline and resulting measurements. Clearly label placement or performance as
unconfirmed when compilation or benchmarking was not requested or available.
