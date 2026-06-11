---
title: Compilation
sidebar_position: 5
---

# Compilation

Use `Model.compile` to convert a **quantized** model into a binary format that
runs on the SiMa MLSoC.

```python
from afe.apis.model import Model

# Load a previously quantized model
quant_model = Model.load("<quant_model_name>", "<path to quantized model file>")
```

## Compile with default options

Specify the output folder:

```python
quant_model.compile(output_path="<output_folder_path>")
```

The output is a `.tar.gz` archive named after the quantized model file. It
contains:

| Contents | Purpose |
| --- | --- |
| `.elf` files | Executed on the MLA |
| `.so` files | Executed on the Cortex-A65 (only when needed) |
| `.yaml` file | Execution-statistics profiling |
| `_mpk.json` | Processor-plugin configuration / pipeline metadata |

## Tessellation

**Tessellation** controls how input and output tensors are laid out in DRAM for
the MLA. Driving tensors **directly to and from the MLA**, with inputs in `HWC`
layout and outputs in `HWC16`, bypasses the EV74 data-reorder unit and reduces
latency. This is the **recommended default** for models that feed the
accelerator directly. The [first-model example](./compile-your-first-model.md)
enables it by default.

Pass tessellation parameters per tensor when compiling:

```python
from afe.apis.defines import TensorTessellateParameters, TensorDRAMLayout

input_tess  = TensorTessellateParameters(tile_shape=(0, 0, 0, 0), enable_mla=True,
                                          dram_layout=TensorDRAMLayout.HWC)
output_tess = TensorTessellateParameters(tile_shape=(0, 0, 0, 0), enable_mla=True,
                                          dram_layout=TensorDRAMLayout.HWC16)

tess_params = {}
mla_node = quant_model._net.nodes["MLA_0"]
for name in mla_node.input_names:
    tess_params[name] = input_tess
# (resolve MLA output names and map them to output_tess — see the example script)

quant_model.compile(output_path="<output_folder_path>", tessellate_parameters=tess_params)
```

`examples/compile_first_model.py` wires this up automatically. Leave
tessellation unset (`tessellate_parameters=None`) only when the EV74 reorder path
is required for your pipeline.

## Compiling for batch sizes > 1

Set the **desired** batch size:

```python
quant_model.compile(output_path="<output_folder_path>", batch_size=16)
```

:::note
The compiler implements the largest batch size it can, up to the requested
value. It does not guarantee the exact requested size. To see what was
implemented, search the `_mpk.json` for `desired_batch_size` and
`actual_batch_size`:

```json
"name": "MLA_0",
"processor": "MLA",
"config_params": {
    "desired_batch_size": 16,
    "actual_batch_size": 12,
    "number_of_quads_to_user": 4
}
```
:::

## Inspecting the archive

The compiler does not print archive contents. List them with:

```python
import tarfile

with tarfile.open("<name_of_archive.tar.gz>") as f:
    for filename in f.getnames():
        print(filename)
```

## Per-layer runtime statistics

Each compiled archive includes a `*_mla_stats.yaml` file with the compiler's
estimated cycle count per MLA layer:

```yaml
4:
  name: MLA_0/conv2d_add_relu_3
  start_cycle: 63615
  end_cycle: 71558
5:
  name: MLA_0/conv2d_add_relu_4
  start_cycle: 71559
  end_cycle: 79502
```

These values are static-schedule start and end cycles. They do **not** include
stalls from instruction or memory fetches. For full runtime statistics,
including memory cycles, run the `.elf` model on hardware in Palette/Neat
accelerator mode.
