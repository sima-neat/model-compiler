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

> **TODO(florianvoss):** Add a standalone `execute` accuracy example — load the
> compiled model, run a representative input set, compare against the reference
> outputs, and describe acceptable tolerances.

## Measure performance

To measure on-device latency, throughput, power, and energy, use the ready-to-run
benchmark walkthrough in the beginner tutorials:

- **[Benchmark Your Model](/tutorials/benchmark-your-model)** — run a compiled
  model with deterministic synthetic tensors and print the headline latency,
  throughput, power, and energy.

> **TODO(florianvoss):** Summarize how to read the benchmark metrics and how they
> map back to compilation choices (batch size, tessellation).
