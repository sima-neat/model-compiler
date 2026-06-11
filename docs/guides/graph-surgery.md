---
title: Graph surgery
sidebar_position: 3
---

# Graph surgery

This section describes graph surgery and its use in optimizing Machine Learning/AI models to successfully compile and deploy on a targeted device (in this case a SiMa device).

## What is Graph Surgery

Graph surgery is the process of modifying the structure of a computational graph (Neural Network model) to meet specific objectives in machine/deep learning use cases (models).

## Why Do You Need to Perform Graph Surgery

Graph surgery is needed in the following scenarios:

- To customize a pre-trained model

- To optimize the model for a specific device (for example, edge devices)

- To enhance the efficiency of a model

## Graph Surgery Using SiMa Tools

While the Palette software (the Model Compiler component) is continuously updated to support new operators, it is sometimes required to perform graph surgery on certain models so that those models can be compiled to run entirely on the MLA.

For example, non-4D tensors are reshaped to 4D, non-supported operators are replaced by supported operators. This document describes an API and recommended practices to perform graph surgery on ONNX models using the Model Compiler component of the Palette software.

The sima-utils package is included in the Model Compiler component of the Palette software and can be invoked by importing the Python package as shown below. For a detailed list of functions refer to API references.

``` python
from sima_utils.onnx import onnx_helpers as oh
```

### Analyzing a Model

The Sima MLSoC contains MLA, CVU (EV74), and APU (A65) as backends. When a model is compiled by the Model Compiler, operators are assigned to the MLA with best effort; if this fails, they are mapped to the CVU or APU, producing multiple MLA segments represented by multiple .elf files. To achieve the best performance, it is desirable to modify the model so that it is assigned to the MLA in its entirety. When the model is completely assigned to the MLA, compilation will produce a single .elf file.

When multiple .elf files are generated after compiling a model using the Model Compiler, those operators between MLA segments may be modified or replaced by other operators so that the whole model may be assigned to MLA.

An analysis needs to be done to decide where and how a model can be modified. Identifying which nodes to perform graph surgery is one skill, which can be assisted by running Model Compiler. Knowing what operators to replace with is another skill, which requires knowledge of ML operators, DSP processing, and MLA support.

Follow the guideline below when performing graph surgery.

1.  Compile a model using the Model Compiler to identify layers not mapped to MLA. Those layers are mapped to CVU or APU; they can be identified by saving and viewing the SiMa IR graph in Netron or enabling verbose logging in the Model Compiler.

2.  Perform graph surgery on those identified layers. If those layers are throughout the whole model, a divide-and-conquer approach is recommended to split the model first.

3.  Save the modified model. Merge the modified sub-graphs if the original model has been split.

4.  Run inferencing with the original model and the modified model and compare the outputs. If a graph surgery only involves data reshuffling, like reshape, slice, concat, and transpose, expect to see an identical match numerically between the original output and the modified output. If a graph surgery changes any math processing order of tensors, there will be no identical match, but generally expect to see a maximum difference around 1e-6 numerically (1e-4 is seen with DETR modification).

5.  Compile the modified model with Model Compiler and confirm a single .elf file is generated.

For MLA supported operators, see [Model Compatibility Guide](./model-compatibility.md).

### ONNX Model

ONNX is an [open specification](https://onnx.ai/onnx/). The ONNX format is embedded in protobuf (specifically, the subset of protobuf that is compatible with both protobuf v2 and v3), and so it is built on the data model of Protocol Buffers.

Semantically, the ONNX specification consists of the following components:

- A definition of an extensible computation graph model;

- Definitions of standard data types;

- Definitions of built-in operators.

The first two items above make up the ONNX Intermediate Representation (IR). The built-in operators are covered by the OPSET specification. See figure below.

![ONNX IR Hierarchy](./media/graph-surgery/ONNX_IR_Hierarchy.png)

An ONNX graph defines the computational logic of a model and consists of a parameterized list of nodes that form a directed acyclic graph based on their inputs and outputs. This is the equivalent of a **network** or **graph** in other deep learning frameworks.

Entities in an ONNX graph are referenced by name. Names of values (graph or node inputs, graph or node outputs, and constants) inhabit a single namespace. Names of nodes inhabit another namespace. What we think of as a graph edge consists of two parts in the ONNX format: a reference to some value’s name in one node’s output list, and a reference to the same name in another node’s input list. That is, if one node’s output list contains the name “foo” and another node’s input list contains the same name “foo”, that represents a graph edge between the two nodes.

- **Graph Level Access**

Once a model is loaded, the graph can be accessed by the following data structures:

- List of nodes: model.graph.node

- List of inputs: model.graph.input

- List of outputs: model.graph.output

- List of constants: model.graph.initializer

Each component can be removed, modified, or added to the graph.

- **Node Level Access**

A node (model.graph.node) in the graph can be accessed by the following data structures:

- Name: node.name

- Operator: node.op_type

- List of inputs: node.input

- List of outputs: node.output

- List of attributes: node.attribute

Each component can be removed, modified, or added to a node.

- **Model Validation**

An ONNX file (or model) is just a proto message. Any tools that can read or write to proto messages can be used to explore an ONNX model. To validate an ONNX model, however, a validation tool (onnx.checker) is developed in C++ with a Python wrapper. The model checker, onnx.checker.check_model, validates an ONNX model by performing the following checks:

- IR version conflict

- Opset conflict: Operator in a graph follows its most recent definition below or equal the graph Opset version

- Consistency of a model

After a model is modified by graph surgery, the model checker should always be called to validate the modified model before saving it to disk.

Once a model is analyzed, follow the steps below to perform graph surgery.

1.  Load an ONNX model.

2.  Perform the surgery.

3.  Remove the existing inferencing shape information.

4.  Save the modified model.

5.  Verify the accuracy of the modified model.
