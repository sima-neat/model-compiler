---
name: sima-model-optimization
description: Optimize MLA-compatible graphs for latency, memory, or throughput while preserving model behavior.
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

- inspect applicable `supported_operators.json` constraints;
- check relevant composite-pattern requirements; and
- use compiler placement evidence when full MLA residency matters.

Compilation is not required to apply a mathematically proven graph-only rewrite,
but it is required to confirm placement or a hardware-dependent benefit.

## Workflow

1. Establish the requested metric or identified bottleneck and preserve a
   baseline when measured improvement is required.
2. Inspect static shapes, dtypes, opset, initializers, output contracts, and
   available compiler evidence.
3. Read `references/optimization_patterns.md` and apply only patterns whose
   match conditions and guards are proven for the graph.
4. Prefer a maintainable source-model change; otherwise make the smallest
   equivalent ONNX rewrite.
5. Validate behavior and report applied patterns, equivalence results, and any
   benefit that still requires compilation or measurement.

## Rules

- Full MLA placement does not prove that a graph is optimally represented.
- Preserve public input/output contracts unless the user requests a change.
- When outputs feed BoxDecode, preserve the contract documented in
  `../model_surgery/references/boxdecode.md`.
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
