---
title: Graph surgery
sidebar_position: 3
---

# Graph surgery

Graph surgery edits a model's computational graph before compilation so it maps
cleanly onto the MLA — replacing or removing operators the compiler can't consume
directly, and reshaping tensors to the formats the backend expects. It is the
step that turns an otherwise-incompatible model (see
[Model compatibility](./model-compatibility.md)) into one that compiles to a
single, fully MLA-assigned artifact.

## When you need it

- An operator is unsupported and must be replaced with a supported equivalent.
- A tensor isn't 4D, but the MLA backend requires 4D (N, H, W, C) tensors.
- A node prevents full MLA mapping, causing the model to split into multiple
  segments instead of one.
- A section of the graph should be restructured (e.g. into parallel paths) to
  avoid an unsupported operation.

## Techniques

- **Operator replacement** — substitute an unsupported operator with a supported
  alternative (for example, rewrite a 2D `Gemm` as a 4D `Conv`).
- **Tensor reshaping** — convert non-4D tensors to the 4D format the MLA backend
  requires.
- **Node removal** — eliminate unsupported nodes so the graph maps entirely to
  the MLA.
- **Graph restructuring** — rewrite a section of the model using parallel paths
  to route around unsupported operations.

## Tooling

The `sima_utils.onnx.onnx_helpers` module provides helpers for these edits,
including `remove_nodes_by_name_list()`, `rewrite_gemm_as_conv()`,
`find_initializer_value()`, `update_io_shape()`, and `run_model()` to verify the
modified model still produces correct outputs.

For the full walkthrough, worked examples, and the complete API, see
[Model graph surgery](https://docs.sima.ai/pages/model-sdk/model_graph_surgery.html).
