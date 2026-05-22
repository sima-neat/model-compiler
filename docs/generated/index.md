# AFE APIs Structure

Source directory: `afe/apis`
Extractor backend: `griffe`

## Package Tree

```text
afe/apis
  __init__.py
  _sanitize_errors.py
  compilation_job.py
  compilation_job_base.py
  compile.py
  defines.py
  error_handling_variables.py
  loaded_net.py
  model.py
  prerelease_v1.py
  release_v1.py
  simulate.py
  statistic.py
  transform.py
```

## API Pages

- [`afe.apis`](afe-apis.md)
- [`afe.apis._sanitize_errors`](afe-apis-_sanitize_errors.md) (3 functions)
- [`afe.apis.compilation_job`](afe-apis-compilation_job.md) (1 class, 1 function) - The API for controlling a compilation job.  This API is intended for use in a user-defined module that is passed to the command-line interface.
- [`afe.apis.compilation_job_base`](afe-apis-compilation_job_base.md) (3 constants) - Shared data type definitions related to compilation jobs.
- [`afe.apis.compile`](afe-apis-compile.md) (1 function) - Load a YAML file and use the JSON and npz file that are referred in the YAML to load the pre-calibrated AwesomeNet, quantize it, and generate MLC files.
- [`afe.apis.defines`](afe-apis-defines.md) (15 classes, 3 functions, 8 constants) - This file contains definitions of the types exposed by the development API for AFE.
- [`afe.apis.error_handling_variables`](afe-apis-error_handling_variables.md) (1 function, 2 constants)
- [`afe.apis.loaded_net`](afe-apis-loaded_net.md) (1 class, 1 function, 1 constant)
- [`afe.apis.model`](afe-apis-model.md) (1 class)
- [`afe.apis.prerelease_v1`](afe-apis-prerelease_v1.md) (13 functions) - This is the pre-release API for AFE.  It supports importing models, loading and storing AFE's internal format, quantizing, executing, and simulating.
- [`afe.apis.release_v1`](afe-apis-release_v1.md) (3 functions) - This is the development API for AFE.  It supports importing models, loading and storing AFE's internal format, quantizing, executing, and simulating.
- [`afe.apis.simulate`](afe-apis-simulate.md) (1 function) - Load a YAML file and use the MLC files referred in the YAML to generate the trace files.
- [`afe.apis.statistic`](afe-apis-statistic.md) (6 functions, 1 constant) - Analysis of statistics on tensors.
- [`afe.apis.transform`](afe-apis-transform.md) (1 class, 21 functions) - Tensor transformations that can be applied to a model's input or output.
