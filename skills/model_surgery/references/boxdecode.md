# SiMa BoxDecode Output Contracts

Read this before changing model outputs that will feed SiMa BoxDecode. BoxDecode
compatibility depends on the exported tensor contract, not just the model-family
name or ONNX operator support.

## Required Checks

1. Check whether the installed Neat version provides a `BoxDecodeType` for the
   model family. If not, do not change the output graph for BoxDecode.
2. Confirm the exported heads satisfy that type's contract; a matching model
   name alone does not establish support.
3. Identify each raw head's role, order, shape, bbox encoding, and score domain.
   Keep or remove sigmoid/softmax only to match that contract.
4. Preserve feature-level order, anchors/strides, and any mask, prototype, or
   keypoint outputs when changing the graph.
5. After compilation, treat only the model pack's `*_mpk.json` as authoritative
   for tensor order, logical/physical layout, dtype, quantization, and resize
   metadata.
6. Run the compiled model through the target BoxDecode implementation and compare
   decoded boxes, scores, NMS results, and task-level accuracy with the source model.

## Family Contracts

`H` is the number of feature heads. "Variable" means the current backend both
derives `H` from the tensor count and processes all derived heads. It does not
mean arbitrary tensors or decode math are accepted.

| Decode family | Head count and tensor contract |
| --- | --- |
| `Yolo` | Legacy fixed three-head layouts with two or three tensors per head. Do not assume custom head counts. |
| `YoloV5` | The parser derives `H` from one packed prediction tensor per head, but the current backend does not initialize its anchor count. Require a release-specific, known-working model and runtime test before claiming support. |
| `YoloV7` | One packed prediction tensor per head (`H`); the decoder has four hard-coded anchor tables, so require `H <= 4`. |
| `YoloV5Seg`, `YoloV7Seg` | Do not treat as verified in the current backend. The parser derives `2H + 1`, but mask processing reads tensor slot 2 from exactly three heads while these families configure only two tensors per head. |
| `YoloV8`, `YoloV9`, `YoloV10` | Variable `H`; detection uses bbox/class pairs (`2H`). Grouped or interleaved layouts and the score domain must match the model-pack contract. |
| `YoloV8Pose` | Exactly three bbox, score/class, and keypoint groups (`9` tensors). |
| `YoloV8Seg`, `YoloV9Seg`, `YoloV10Seg` | Exactly three bbox, class-score, and mask-coefficient groups plus one trailing prototype (`10` tensors). |
| `YoloV26` | Variable `H`; grouped raw 4-channel `l/t/r/b` heads followed by class-logit heads (`2H`). BoxDecode applies sigmoid. |
| `YoloV26Pose` | Exactly three heads: grouped 4-channel bbox, 1-channel pose-score, and 51-channel keypoint tensors (`9` tensors). The parser accepts other `H`, but pose processing hard-codes three heads. |
| `YoloV26Seg` | Exactly three heads: grouped 4-channel bbox, class-logit, and 32-channel mask-coefficient tensors plus one trailing 32-channel prototype (`10` tensors). The parser accepts other `H`, but mask processing hard-codes three heads. |
| `YoloV6` | Variable `H`; interleaved raw `[bbox_ltrb, class_logit]` tensors (`2H`). |
| `YoloX` | Variable `H`; interleaved raw `[bbox_xywh, objectness_logit, class_logit]` tensors (`3H`). |
| `Ssd` | Exactly six ordered feature levels: grouped localization heads followed by confidence heads (`12` tensors). The input shape, anchors, class count, activation, and stretch preprocessing must match a built-in SSD300, SSD-MobileNet 300/320, or TorchVision SSDLite 320 recipe. SSD-MobileNet uses sigmoid; SSD300 and TorchVision use softmax. |
| `EffDet` | Variable `H`; one box-regression and one class tensor per head (`2H`). |
| `Detr` | Fixed one head with two tensors ordered `[class_scores, bbox_regression]`. |
| `RcnnStage1` | Fixed five heads with two tensors per head, interleaved by head (`10` tensors). |
| `Centernet` | Fixed one head with three tensors. |
| `SuperPoint` | Fixed two tensors: one 65-channel detector-logit tensor and one compatible descriptor grid. It produces feature points rather than boxes. |

More feature heads are supported only for families marked variable, and every
head must preserve that family's roles, ordering, spatial pairing, channel
depths, encoding, and score domain. Do not pass unrelated model outputs to
BoxDecode or use an existing type for custom decode semantics.

A public `BoxDecodeType` or parser-accepted tensor count is not sufficient proof
of working support. For rows with an implementation caveat, do not rewrite a
model for BoxDecode until the installed release has a known-working example or
an end-to-end runtime test covering that exact contract.

Changing model outputs is an API change. Report the new output contract and the
required BoxDecode type to the user; do not silently approximate model math.

## References

- [BoxDecode Decode Types](https://developer.sima.ai/software/reference/boxdecode_decode_types) — user-facing contracts and usage.
- [BoxDecodeType.h](https://github.com/sima-neat/core/blob/main/include/pipeline/BoxDecodeType.h) — public enums, packing options, and contract summaries.
- [SimaBoxDecode.cpp](https://github.com/sima-neat/core/blob/main/src/nodes/sima/SimaBoxDecode.cpp) — model-pack contract compilation and overrides.
- [BoxDecodeStageSemantics.cpp](https://github.com/sima-neat/core/blob/main/src/pipeline/internal/sima/stagesemantics/BoxDecodeStageSemantics.cpp) — normalized runtime contract semantics.
- [generic BoxDecode backend](https://github.com/sima-neat/internals/blob/270ebebbab6cf527745b2edb640e0661b38e919b/gst_plugins/vendor/sima-ai-a65-apps/genericboxdecode/src/boxdecode.cpp) — implementation snapshot used to verify the family table.

The documentation and `main` branch can be newer than the user's runtime.
For source-level decisions, use the tag that matches the installed Neat release.
