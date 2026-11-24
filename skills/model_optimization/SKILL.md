---
name: sima-model-optimization
description: Speed up or shrink ONNX graphs that already run on the SiMa MLA (Modalix), for latency, FPS, throughput or memory, with proven-equivalent rewrites, such as fusing parallel Q/K/V or 1x1 projections, folding Transpose/Reshape/Identity layout no-ops and static Shape chains, replacing reshape shuffles with DepthToSpace, canonicalizing to rank-4 NCHW, packing attention heads, simplifying masks and singleton reductions, keeping RMSNorm fusible, precomputing finite-domain subgraphs such as timestep or RoPE embeddings, and moving large constant embedding or codebook lookups to the host. Use when the user wants lower latency, more throughput or a smaller compiled model with unchanged outputs, or compiler evidence shows a bottleneck, even before the model is shared. Not for unsupported operators, attribute limits or BoxDecode output adaptation (use `sima-model-surgery`), or a plain quantize-and-compile (use `sima-model-quantize-compile`).
---

# Optimize Models for SiMa MLA

Use this skill when performance optimization is requested or compiler evidence
identifies a relevant bottleneck. Do not invoke it solely because a customer
asked to compile a model. Use model surgery for incompatibilities or BoxDecode
output contracts.

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
3. Screen the original graph with the operator audit in the
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

Audit the simplified graph for INT8, and again with `--dtype bfloat16` when BF16
matters. Pass the original model only when every dimension was already static
and the simplifier was skipped:

```bash
python3 <skill-dir>/../sima-model-surgery/scripts/model_surgery_guard.py audit-model \
  --model /abs/path/model.static.sim.onnx \
  --dtype int8
```

For each operator a rewrite adds or keeps, read its attribute and shape
constraints with `model_surgery_guard.py query-op --op <Op>` or in that skill's
`data/supported_operators.json`.

## Rules

- Full MLA placement does not prove that a graph is optimally represented.
- Preserve public input/output contracts unless the user requests a change.
- When outputs feed BoxDecode, preserve the contract documented in
  `references/boxdecode.md` of the `sima-model-surgery` skill, which is
  installed next to this one (`<skill-dir>/../sima-model-surgery/`, where
  `<skill-dir>` is the folder holding this SKILL.md).
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
