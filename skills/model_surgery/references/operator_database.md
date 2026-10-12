# Operator Support Database Maintenance

Read this only when changing operator metadata or generated compatibility
documentation. Ordinary model audits and rewrites do not require it.

- `data/supported_operators.json` is the sole operator-support source used by
  the guard and generated customer documentation.
- Keys must match canonical ONNX `node.op_type` names. Record multi-node MLA
  patterns, such as RMSNorm through opset 22, in `composite_patterns.md` instead.
- Record hardware and software constraints in `sima_hw_sw_constraints`, 5D
  support in `fived`, and precision support in `int8` and `bfloat16`.
- Document all attribute, shape, opset, dtype, constant-input, and fallback
  conditions needed to interpret the support entry safely.

After changing the database, regenerate the English compatibility page from the
repository root:

```bash
python3 scripts/build_supported_operators_md.py
```

Include the generated page and refresh its supported translations with the
repository's `sima-i18n` workflow.
