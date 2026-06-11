---
title: Validate accuracy and performance
sidebar_position: 6
---

# Validate accuracy and performance

After you compile a model, validate accuracy and measure performance before you
deploy it.

## Validate accuracy

Run the compiled model through the `execute` path. Compare its outputs against
the original float model on representative inputs.

For a worked `execute` accuracy check, see the validation step in
[Compile Your First Model](./compile-your-first-model.md).

Use representative inputs from your target workload. Compare the compiled model
against a trusted floating-point reference. Acceptable tolerances depend on the
model and quantization scheme.

Start with model-level metrics such as classification accuracy or detection
mAP. If a metric regresses, inspect per-output differences.

## Measure performance

To measure on-device latency, throughput, power, and energy, use the benchmark
walkthrough in the beginner tutorials:

- **[Benchmark Your Model](/tutorials/benchmark-your-model)** — run a compiled
  model with deterministic synthetic tensors and print the headline latency,
  throughput, power, and energy.

Use benchmark results to confirm that the selected batch size, quantization
scheme, and tessellation settings meet your application requirements. If latency
or throughput misses the target, revisit compilation options before you change
the runtime application.
