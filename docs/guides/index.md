---
title: Compile Your Model
sidebar_label: Overview
sidebar_position: 1
---

# Compile Your Model

The **Model Compiler** is the SiMa.ai toolchain that turns a trained model into an
artifact the Neat runtime can execute on the MLSoC. It exposes the `afe` Python
package, which you use to **import** a model, **quantize** it to a
lower-precision data type the accelerator runs efficiently, **simulate** it to
check accuracy, and **compile** it to the `.tar.gz` MPK archive consumed by the
runtime.

This section walks you through that workflow and then documents each step in
depth.

:::tip Compiling generative AI models?
LLMs and other generative models use a different toolchain. See
**[LLiMa → GenAI compilation](/llima/compilation_genai)**.
:::

## Start here

- **[Compile Your First Model](./compile_your_first_model.md)** — an end-to-end
  ResNet-50 walkthrough: load an ONNX model, calibrate, quantize to INT8,
  validate accuracy, and compile to an MPK archive.

## Reference guides

- **[Quantization](./quantization.md)** — INT8 (default) and BF16 quantization,
  plus calibration methods.
- **[Compilation](./compilation.md)** — the `.compile()` API, batch sizing, MLA
  tessellation, and the contents of the compiled `.tar.gz`.
- **[Supported Operators](./supported_operators.md)** — the operators the MLA
  compiler supports and their precision/constraint matrix.
- **[API Reference](./api-reference/)** — the auto-generated `afe.apis` Python
  API surface.
