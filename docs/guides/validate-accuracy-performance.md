---
title: Validate accuracy and performance
sidebar_position: 6
---

# Validate accuracy and performance

After compiling, confirm the model is both **correct** — its outputs match the
original float model closely enough — and **fast enough** for your deployment
target.

## Validate accuracy

Run the compiled model through the `execute` path and compare its outputs
against the original float model on representative inputs.

For a worked `execute` accuracy check (classify a known image and compare the
prediction), see the validate step in
[Compile Your First Model](./compile-your-first-model.md).

Use representative inputs from your target workload and compare against a
trusted floating-point reference. Acceptable tolerances depend on the model and
quantization scheme; start by checking top-line task metrics such as
classification accuracy or detection mAP, then inspect per-output differences
when a model-level metric regresses.

## Measure performance

To measure on-device latency, throughput, power, and energy, use the ready-to-run
benchmark walkthrough in the beginner tutorials:

- **[Benchmark Your Model](/tutorials/benchmark-your-model)** — run a compiled
  model with deterministic synthetic tensors and print the headline latency,
  throughput, power, and energy.

Use benchmark results to confirm that the selected batch size, quantization
scheme, and tessellation settings meet your application requirements. If latency
or throughput misses the target, revisit compilation options before changing the
runtime application.
