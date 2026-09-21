# MLA Optimization Patterns

## `llima-nchw-attention`

- **Match:** Attention with Q `[B,D,H,Q]`, K/V `[B,D,H,L]`, scores
  `[B,L,H,Q]`, an additive broadcast-compatible mask, and optional GQA. Require
  `H` to be divisible by the KV-head count and preserve scaling, RoPE, cache,
  soft-capping, head order, and mask semantics.
- **Rewrite:** Use:

  ```text
  Einsum("nchw,nchq->nqhw")
  Add(mask)
  Softmax(axis=1)
  Einsum("nchw,nqhc->nqhw")
  Split(axis=2) -> Concat(axis=1) -> [B,H*D,1,Q]
  ```

  Expand GQA heads with `Split`/repeated `Concat` when it
  produces the same ordering.
- **Guards:** Do not rewrite attention with different normalization, head
  mapping, mask domain, cache semantics, or output ordering. Preserve chunked
  reductions required for long contexts.

## `attention-head-pack-merge`

- **Match:** A static, proven mapping between packed channels `[B,H*D,1,L]` and
  explicit heads `[B,D,H,L]`, with uniform head sizes and no intermediate
  fan-out.
- **Rewrite:** Replace head-packing or merging `Reshape/Transpose` operations
  with channel-axis `Split/Concat`, preserving exact head order.
- **Guards:** Do not infer head order from shapes alone or rewrite dynamic,
  interleaved, grouped, or permuted heads.

## `rank4-nchw-canonicalization`

- **Match:** A connected rank-1/2/3 activation region whose logical dimensions
  and every operator, axis, broadcast constant, weight, pad, and boundary can be
  mapped statically to `[N,C,H,W]`.
- **Rewrite:** Convert the whole region to NCHW. Remap permutations, weights,
  constants, pads, slices, splits, concatenations, Softmax, and reductions. A
  common sequence mapping is `[B,L,C] -> [B,C,1,L]`; add boundary adapters when
  the public contract remains unchanged.
- **Guards:** Never treat this as an isolated "add dimensions" rewrite. Stop at
  dynamic ranks, ambiguous axes, unsupported mappings, or unauthorized public
  layout changes.

## `parallel-projection-fusion`

- **Match:** At least two constant-weight `MatMul/Gemm + optional bias` or 1x1
  convolutions sharing one input, dtype, spatial interpretation, convolution
  attributes, and quantization boundary. Output channel counts must be static.
- **Rewrite:** Concatenate weights and biases in branch order on the output
  channel axis, run one 1x1 Conv, then split by the original channel counts. Use
  zero bias for a missing branch only when dtype-exact.
- **Guards:** Apply before quantization unless QDQ contracts are compatible. Do
  not fuse different groups, strides, pads, dilations, precision requirements,
  or branch-specific activations.

## `rmsnorm-fusion-preservation`

- **Match:** Channel-axis RMSNorm with static 4D input, reduction axis 1,
  `keepdims=1`, positive constant epsilon, weight `[1,C,1,1]`, no mean
  subtraction or beta, and single-purpose intermediates.
- **Rewrite:** Preserve AFE's recognized form:

  ```text
  Mul(x,x) -> ReduceMean(axis=1, keepdims=1) -> Add(epsilon)
           -> Sqrt -> Div(x, root) -> Mul(weight)
  ```

  Use `quantize_compile.py --no-simplify` when simplification changes it before
  AFE import.
- **Guards:** Do not classify LayerNorm, mean-centered normalization, different
  reduction axes, or nonconstant epsilon as RMSNorm.

## `static-control-fold-and-prune`

- **Match:** `Shape`, `Gather`, `Unsqueeze`, `Squeeze`, arithmetic, or
  concatenation control nodes depending only on initializers and dimensions
  proven static for the exported contract.
- **Rewrite:** Evaluate them with the model's ONNX opset semantics, replace their
  results with correctly typed initializers or attributes, and remove dead nodes
  and unused initializers.
- **Guards:** Preserve runtime inputs, symbolic dimensions, and values that can
  vary across supported input shapes.

## `layout-noop-elimination`

- **Match:** `Identity`; a reshape with identical inferred input/output shape;
  singleton-only `Reshape -> Transpose`; an inverse permutation pair; or a
  dominated equivalent layout conversion. Prove element order and inspect every
  fan-out.
- **Rewrite:** Bypass redundant nodes and reconnect consumers while preserving
  required graph-output names.
- **Guards:** Equal element count is insufficient. Preserve changes to ordering,
  broadcast rank, symbolic behavior, quantization boundaries, or layouts seen by
  another consumer.

## `singleton-reduction-specialization`

- **Match:** A reduction with known normalized axes where at least one reduced
  dimension is statically one and removing it is an identity for that operator
  and dtype.
- **Rewrite:** Remove singleton axes from the reduction. If none remain, use an
  identity or reshape that preserves the original `keepdims` output shape.
- **Guards:** Do not specialize symbolic dimensions or change dtype, NaN, Inf,
  or empty-tensor behavior.

## `binary-mask-simplification`

- **Match:** One of:

  1. `Where(Equal(mask, 0), 0, data)` with a numeric `{0,1}` mask.
  2. `Where(..., -inf, score)` immediately before Softmax, with at least one
     unmasked element in every row and no other consumer of the masked logits.

- **Rewrite:** For variant 1, use `data * mask`. For variant 2, use an equivalent
  arithmetic/additive mask with the score dtype's finite minimum.
- **Guards:** Preserve comparison polarity and broadcasting. Reject nonbinary,
  inverted, probabilistic, NaN-bearing, or transformed masks; all-masked
  Softmax rows; and paths that mix positions.

## `reshape-shuffle-to-depthtospace`

- **Match:** A static `Reshape -> Transpose -> Reshape` with exact ONNX
  `DepthToSpace` element order for block size `r` and `DCR` or `CRD` mode. Input
  is `[N,C*r*r,H,W]`, and the shuffle has no internal fan-out.
- **Rewrite:** Replace it with `DepthToSpace(blocksize=r, mode=...)`. If the next
  Conv previously consumed flattened `[C,H*r]` channels, keep the expanded
  height and reshape constant weights `[O,C*H*r,Kw] -> [O,C,H*r,Kw]`, using a
  2D kernel spanning that height. Supertonic uses:

  ```text
  [N,144,1,T] -> DepthToSpace(r=6, CRD) -> [N,4,6,6T]
  [O,24,7] weights -> [O,4,6,7]
  ```

- **Guards:** Prove mode and ordering with unique index values. Reject dynamic or
  indivisible shapes, fan-out, or convolution folding that changes padding,
  grouping, dilation, or boundary behavior.

## `finite-domain-subgraph-externalization`

- **Match:** Timestep, RoPE, schedule, or similar deterministic preprocessing
  whose complete legal runtime domain is finite and independent of activations
  or hidden state. Exact output dtype, shape, order, and branch behavior must be
  known, and table storage/transfer must be preferable to the subgraph.
- **Rewrite:** Probe the original ONNX for every legal state, store the output
  bank outside the model, replace the subgraph outputs with compact inputs,
  update the host to select and pack them, then prune the dead graph.
- **Guards:** Reject continuous, unbounded, data-dependent, or incompletely
  enumerated domains. Prove apparently shared branches equal for every state and
  include the runtime consumer when changing the input contract.

## `large-static-lookup-offload`

- **Match:** Large constant embedding/codebook tables used by deterministic
  integer lookup preprocessing. The host must reproduce indices, offsets,
  padding, invalid-index behavior, combination order, dtype, and layout exactly;
  the resulting dense activation must be a practical model boundary.
- **Rewrite:** Remove lookup tables and lookup-only ancestors from ONNX, expose
  the dense activation as an input, perform lookup and packing on the host, and
  bind the exact table/checkpoint version to the compiled runtime package.
- **Guards:** Reject trainable or mutable tables, device-state-dependent lookups,
  or cases where transfer cost outweighs the removed graph/storage. Include the
  runtime consumer because this changes the model contract.
