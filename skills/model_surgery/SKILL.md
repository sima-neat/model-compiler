---
name: sima-model-surgery
description: Fix SiMa MLA operator incompatibilities or adapt model outputs for SiMa BoxDecode.
---

# Model Surgery for SiMa MLA

Use this skill to audit an ONNX graph or make the smallest source-model/ONNX
change required for MLA compatibility or a BoxDecode output contract. Use model
optimization for performance-only rewrites of an otherwise compatible graph.

## Environment and Platform

Activate the Model Compiler environment before using the ONNX helpers:

```bash
activate-model-compiler
```

The support database's BF16 entries apply to Modalix. If the target is
unspecified, assume Modalix and screen both INT8 and BF16 when that distinction
matters to the request.

## Workflow

1. Identify the requested outcome: audit, compatibility rewrite, BoxDecode
   adaptation, or compilation support.
2. Inspect the source model, exported ONNX, static shapes, dtypes, opset, public
   tensor contracts, and available compiler logs.
3. Run the operator audit and inspect the constraints for every relevant
   operator. This is preliminary screening, not confirmation of MLA placement.
4. Load only the references needed for the graph:
   - `references/boxdecode.md` when outputs will actually feed SiMa BoxDecode;
   - `references/composite_patterns.md` when fusion of a multi-node pattern such
     as RMSNorm matters;
   - `references/compatibility_patterns.md` when an operator form or attribute
     requires a rewrite;
   - `references/operator_database.md` only when maintaining support metadata or
     generated compatibility documentation.
5. For a rewrite, prefer a maintainable source-model change; otherwise make the
   smallest safe ONNX edit.
6. Re-screen the changed graph, run ONNX validation, and compare behavior with
   the original model.
7. Quantize or compile only when the user requested that outcome.

## Operator Audit

```bash
python3 skills/model_surgery/scripts/model_surgery_guard.py audit-model \
  --model /abs/path/model.onnx \
  --dtype int8
```

Useful queries:

```bash
python3 skills/model_surgery/scripts/model_surgery_guard.py query-op --op Gather
python3 skills/model_surgery/scripts/model_surgery_guard.py list-supported --dtype bfloat16
```

The audit checks operator names and precision flags. It cannot establish that
attributes, shapes, opsets, composite patterns, or placement satisfy every MLA
constraint.

For symbolic dimensions, use the static simplifier before screening:

```bash
python3 skills/model_surgery/scripts/onnx_static_simplify.py \
  --input /abs/path/model.onnx \
  --output /abs/path/model.static.sim.onnx \
  --replace batch=1
```

## Rewrite Validation

- Preserve public tensor names, shapes, ordering, dtype, layout, and score
  domain unless the requested contract intentionally changes them.
- Compare the original and modified model on representative inputs. Report the
  numerical tolerance for equivalent rewrites or a task-level metric for an
  intentional output/math change.
- If representative data or compiler placement evidence is unavailable, state
  that limitation explicitly.

## Completion

- An audit delivers findings, applicable constraints, and unresolved placement
  or fusion questions; it does not compile or modify the model.
- A rewrite delivers the modified graph or source change, its public contract,
  repeated screening, and equivalence evidence.
- A compilation-support request continues through the quantize/compile workflow
  and delivers its requested artifacts and verification.
- Requested measured performance work includes baseline and resulting
  measurements; route performance-only graph changes to model optimization.
