# MLA Composite Patterns

`supported_operators.json` covers canonical ONNX nodes. `audit-model` checks
nodes individually and cannot verify that a multi-node pattern will be fused.

## RMSNorm (ONNX opset 22 and earlier)

AFE recognizes this normalized pattern and lowers it to MLA `RMSNormOp`:

```text
x * Rsqrt(ReduceMean(x * x, axis=-1, keepdims=1) + epsilon) * scale
```

Requirements:

- Static 4D input; last/channel-axis reduction with `keepdims=1`.
- Constant scalar epsilon and constant channel scale.
- The complete pattern must remain recognizable after import. The scale may be
  converted to a depth-wise 1x1 convolution.
- INT8 support; BF16 support on Modalix.

Verify that AFE produces `RMSNormOp`, assigns it to MLA without fallback, and
matches source-model outputs on representative inputs.

`RMSNormalization` is canonical from opset 23 and is outside the current
opset-22 database scope.
