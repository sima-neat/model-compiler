# Model Surgery Patterns (Reference)

Use this file as optional reference material for architecture-specific rewrite ideas.
It is not required reading for every surgery task.

## Common Patterns from Existing YOLO Surgeons
- Postprocess decomposition with `Split`, `Concat`, `Conv`, `Softmax`, `Add`, `Sub`, `Mul`, `Div`.
- Replacing output formatting subgraphs with explicit per-scale outputs.
- Attention-path rewrites (for some models), such as replacing fragile `MatMul` paths with hardware-friendlier formulations.

## Practical Guidance
- Start from `audit-model` unsupported/unknown operator findings.
- Apply local edits with minimal surface area.
- Re-run `audit-model` and ONNX validation after each change set.
