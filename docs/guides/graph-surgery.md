---
title: Graph surgery
sidebar_position: 3
---

# Graph surgery

Graph surgery modifies an ONNX graph so the Model Compiler can compile and
deploy the model on a SiMa device.

## Understand graph surgery

Graph surgery changes the structure of a neural-network computation graph. Use
it when a model needs targeted changes before quantization, compilation, or
deployment.

Common reasons include:

- Customize a pre-trained model.
- Adapt a model for a target device.
- Replace or reshape graph operations that block efficient compilation.

## Use SiMa tools for graph surgery

The Model Compiler is updated regularly with support for additional operators.
Some models still need graph surgery before all layers can run on the MLA.

For example, you might reshape non-4D tensors to 4D or replace unsupported
operators with supported alternatives.

The Model Compiler includes the `sima-utils` package. Import the ONNX helper
module before you modify a graph:

``` python
from sima_utils.onnx import onnx_helpers as oh
```

For the full helper API, see the API reference.

## Analyze MLA coverage

The SiMa MLSoC uses these execution backends:

- MLA
- CVU (EV74)
- APU (A65)

During compilation, the Model Compiler assigns operators to the MLA when
possible. Operators that cannot run on the MLA map to the CVU or APU. This can
split the model into multiple MLA segments and produce multiple `.elf` files.

For best performance, modify the model so more of it runs on the MLA. If the
whole model maps to the MLA, compilation produces a single `.elf` file.

Start by locating the layers that do not map to the MLA. Then decide which
operators to replace or reshape. This requires both Model Compiler output and
knowledge of ML operators, DSP processing, and MLA support.

## Modify the graph

Use this workflow when you perform graph surgery:

1. Compile the model with the Model Compiler.
2. Identify layers that do not map to the MLA. Save and inspect the SiMa IR graph
   in Netron, or enable verbose Model Compiler logging.
3. Modify the identified layers. If the layers appear throughout the model,
   split the model first and modify one section at a time.
4. Save the modified model. If you split the model, merge the modified
   subgraphs.
5. Run inference with the original model and the modified model. Compare the
   outputs.
6. Compile the modified model with the Model Compiler.
7. Confirm that compilation produces a single `.elf` file when full MLA coverage
   is the goal.

For data-reshaping changes such as `Reshape`, `Slice`, `Concat`, and
`Transpose`, the original and modified outputs should match numerically. If the
change modifies math ordering, exact matches are not expected. In those cases,
evaluate the numerical difference and model-level accuracy.

For MLA operator support, see [Model compatibility](./model-compatibility.md).

## Review ONNX graph structure

ONNX is an [open specification](https://onnx.ai/onnx/) based on Protocol
Buffers. An ONNX model contains:

- an extensible computation graph model
- standard data types
- built-in operators

The graph model and data types make up the ONNX Intermediate Representation
(IR). Built-in operators are defined by the OPSET specification.

![ONNX IR Hierarchy](./media/graph-surgery/ONNX_IR_Hierarchy.png)

An ONNX graph defines the model computation. It contains nodes that form a
directed acyclic graph through their inputs and outputs. This is equivalent to a
**network** or **graph** in other deep learning frameworks.

ONNX graph entities are referenced by name:

- Value names include graph inputs, graph outputs, node inputs, node outputs,
  and constants.
- Node names use a separate namespace.
- A graph edge exists when one node output and another node input reference the
  same value name.

## Access graph fields

After you load a model, access graph-level fields through:

- `model.graph.node`: nodes
- `model.graph.input`: graph inputs
- `model.graph.output`: graph outputs
- `model.graph.initializer`: constants

You can remove, modify, or add graph-level components.

Access node-level fields through:

- `node.name`: node name
- `node.op_type`: operator type
- `node.input`: node inputs
- `node.output`: node outputs
- `node.attribute`: node attributes

You can remove, modify, or add node-level components.

## Validate the modified model

An ONNX file is a protobuf message. You can inspect it with any tool that reads
or writes protobuf messages. To validate an ONNX model, use
`onnx.checker.check_model`.

The model checker validates:

- IR version compatibility
- OPSET compatibility
- model consistency

Always call the model checker after graph surgery and before you save the
modified model to disk.

Use this final validation workflow:

1. Load the ONNX model.
2. Perform graph surgery.
3. Remove existing inference shape information.
4. Validate the modified model with `onnx.checker.check_model`.
5. Save the modified model.
6. Verify the modified model's accuracy.
