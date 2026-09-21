# MLA Compatibility Rewrite Patterns

Use these rewrites only after `supported_operators.json` shows that the original
operator form cannot run on MLA. Keep a natively supported operator unless a
separate, measured optimization justifies changing it.

## Unsupported-stride ConvTranspose1D polyphase shuffle

MLA supports 2D and 3D ConvTranspose with dilation 1 and either `group=1` or a
depthwise configuration. Non-depthwise strides may be 1, 2, 4, 8, or 16;
depthwise strides may be 1 or 2. Lift a supported ConvTranspose1D to 2D by adding
a singleton height and retain native ConvTranspose.

For an unsupported non-depthwise stride, use the polyphase rewrite only when:

- width and weights are static;
- `group=1` and `dilation=1`;
- `kernel=2*stride`;
- `padding=ceil(stride/2)`; and
- `output_padding=stride%2`.

Replace the operation with a `(1,2)` Conv2D using stride `(1,1)` and padding
`(0,1)`. It produces `stride*Cout` phase channels. For phase `p`, copy source
taps `stride+p` and `p`, including the ConvTranspose-to-Conv channel transpose,
and repeat the source bias once per phase. Then shuffle phase channels into time:

```text
[N,stride*Cout,1,W+1]
-> Transpose NCHW-to-NHWC
-> Reshape [N,1,(W+1)*stride,Cout]
-> Transpose NHWC-to-NCHW
-> crop width to W*stride
```

The transpose pair is intentional. AFE converts the surrounding convolution
region to NHWC, so the layout conversions are absorbed—"eaten" by compiler
layout conversion—and the channel-to-time shuffle becomes a contiguous NHWC
reshape. A direct NCHW expression would require a rank-5
`Reshape -> Transpose -> Reshape` permutation.

Do not apply this rewrite to a supported native stride, grouped or dilated
ConvTranspose, dynamic width, a different kernel/padding relationship, or an
unverified phase order. Do not assume the transpose pair will be absorbed if a
fan-out or layout-sensitive operation interrupts the region.

Validate the isolated rewrite with impulse inputs that expose phase and tap
ordering, compare full-model outputs after the crop, and inspect the AFE graph to
confirm the transpose pair was absorbed. OmniVoice uses this rewrite only for
Higgs decoder strides 3 and 5; strides 8, 4, and 2 remain native ConvTranspose2D.
The reference implementation is `PolyphaseConvTranspose2d` in
`OmniVoice-sima/tools/export_static_higgs_decoder.py`.
