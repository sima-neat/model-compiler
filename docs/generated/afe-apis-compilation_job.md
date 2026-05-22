<a id="afe-apis-compilation-job"></a>
# `afe.apis.compilation_job`

Source: `afe/apis/compilation_job.py`

[Back to index](index.md)

The API for controlling a compilation job.  This API is intended for use in a user-defined module that is passed to the command-line interface.

Imports:
- [`afe.apis.compilation_job_base.GroundTruth`](afe-apis-compilation_job_base.md#afe-apis-compilation-job-base-groundtruth)
- [`afe.apis.compilation_job_base.Tensor`](afe-apis-compilation_job_base.md#afe-apis-compilation-job-base-tensor)
- [`afe.apis.compilation_job_base.Tensors`](afe-apis-compilation_job_base.md#afe-apis-compilation-job-base-tensors)
- `afe.apis.statistic.Statistic`
- [`afe.apis.transform.Transform`](afe-apis-transform.md#afe-apis-transform-transform)
- `dataclasses`
- `typing.Any`
- `typing.Generic`
- `typing.Iterable`
- `typing.List`
- `typing.Tuple`

Classes:
- <a id="afe-apis-compilation-job-compilationjob"></a>`CompilationJob(Generic[GroundTruth])` (line 31): A specification of how to calibrate, quantize, evaluate, and compile a model. Decorators: `dataclasses.dataclass(frozen=True)`.
  Attributes:
  - <a id="afe-apis-compilation-job-compilationjob-preprocess-transforms"></a>`preprocess_transforms` (line 38) [type `List[Transform]`]
  - <a id="afe-apis-compilation-job-compilationjob-postprocess-transforms"></a>`postprocess_transforms` (line 41) [type `List[Transform]`]
  - <a id="afe-apis-compilation-job-compilationjob-calibration-input"></a>`calibration_input` (line 44) [type `Iterable[Tensors]`]
  - <a id="afe-apis-compilation-job-compilationjob-evaluation-input"></a>`evaluation_input` (line 47) [type `Iterable[Tuple[Tensors, GroundTruth]]`]
  - <a id="afe-apis-compilation-job-compilationjob-evaluate-result"></a>`evaluate_result` (line 51) [type `Statistic[Tuple[Tensors, GroundTruth], str]`]

Functions:
- <a id="afe-apis-compilation-job-set-compilation-job"></a>`set_compilation_job(job: CompilationJob[Any]) -> None` (line 54): Use the given CompilationJob to control compilation.  If called multiple times, the job that is passed to the final call will be used.
    Parameters:
    - `job`: type `CompilationJob[Any]`
    Returns: None
