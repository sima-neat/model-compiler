<a id="afe-apis-loaded-net"></a>
# `afe.apis.loaded_net`

Source: `afe/apis/loaded_net.py`

[Back to index](index.md)

Imports:
- `afe._tvm._tvm_graph_partition.CompileMode`
- `afe._tvm._utils.create_ir_evaluator`
- `afe._tvm._utils.run_ir_evaluator`
- [`afe.apis.defines`](afe-apis-defines.md)
- [`afe.apis.defines.ExceptionFuncType`](afe-apis-defines.md#afe-apis-defines-exceptionfunctype)
- [`afe.apis.defines.HistogramEntropyMethod`](afe-apis-defines.md#afe-apis-defines-histogramentropymethod)
- [`afe.apis.defines.HistogramMSEMethod`](afe-apis-defines.md#afe-apis-defines-histogrammsemethod)
- [`afe.apis.defines.HistogramPercentileMethod`](afe-apis-defines.md#afe-apis-defines-histogrampercentilemethod)
- [`afe.apis.defines.InputValues`](afe-apis-defines.md#afe-apis-defines-inputvalues)
- [`afe.apis.defines.MinMaxMethod`](afe-apis-defines.md#afe-apis-defines-minmaxmethod)
- [`afe.apis.defines.MovingAverageMinMaxMethod`](afe-apis-defines.md#afe-apis-defines-movingaverageminmaxmethod)
- [`afe.apis.defines.QuantizationParams`](afe-apis-defines.md#afe-apis-defines-quantizationparams)
- [`afe.apis.defines.SkipCalibration`](afe-apis-defines.md#afe-apis-defines-skipcalibration)
- [`afe.apis.defines.gen1_target`](afe-apis-defines.md#afe-apis-defines-gen1-target)
- [`afe.apis.defines.gen2_target`](afe-apis-defines.md#afe-apis-defines-gen2-target)
- [`afe.apis.defines.gen_custom_target`](afe-apis-defines.md#afe-apis-defines-gen-custom-target)
- [`afe.apis.defines.quantization_scheme`](afe-apis-defines.md#afe-apis-defines-quantization-scheme)
- [`afe.apis.model.Model`](afe-apis-model.md#afe-apis-model-model)
- `afe.core.configs.AfeProcessingConfigs`
- `afe.core.configs.ModelConfigs`
- `afe.core.configs.OptimizationConfigs`
- `afe.core.configs.QuantizationPrecision`
- `afe.core.configs.TransformerConfigs`
- `afe.core.configs.api_calibration_configs`
- `afe.core.configs.create_quantization_configs`
- `afe.driver.statistic.Statistic`
- `afe.ir.defines.RequantizationMode`
- `afe.ir.defines.Status`
- `afe.ir.tensor_type.ScalarType`
- `afe.ir.tensor_type.scalar_type_from_dtype`
- `afe.ir.utils.transpose_tensor_according_to_layout_strings`
- `afe.load.importers.general_importer.ImporterParams`
- `afe.load.importers.general_importer.ModelFormat`
- `afe.load.importers.general_importer.default_layout`
- `afe.load.importers.general_importer.detect_format`
- `afe.load.importers.general_importer.keras_source`
- `afe.load.importers.general_importer.onnx_source`
- `afe.load.importers.general_importer.pytorch_source`
- `afe.load.importers.general_importer.tensorflow2_source`
- `afe.load.importers.general_importer.tensorflow_source`
- `afe.load.importers.general_importer.tflite_source`
- `copy`
- `dataclasses`
- `logging`
- `numpy as np`
- `os.path`
- `sima_utils.common.CustomPlatformParams`
- `sima_utils.common.Platform`
- `sima_utils.logging.sima_logger`
- `tempfile`
- `typing.Callable`
- `typing.Iterable`
- `typing.TypeVar`

Constants:
- <a id="afe-apis-loaded-net-groundtruth"></a>`GroundTruth` (line 54) [default/value `TypeVar('GroundTruth')`]

Classes:
- <a id="afe-apis-loaded-net-loadednet"></a>`LoadedNet` (line 252)
  - <a id="afe-apis-loaded-net-loadednet-execute"></a>`execute(inputs: InputValues, *, log_level: int = logging.NOTSET) -> list[np.ndarray]` (line 287) Decorators: `_sanitize_exceptions(ExceptionFuncType.LOADED_NET_EXECUTE)`.
    Parameters:
    - `inputs`: type `InputValues`
    - `log_level`: type `int`, default `logging.NOTSET`
    Returns: list[np.ndarray]
  - <a id="afe-apis-loaded-net-loadednet-quantize"></a>`quantize(calibration_data: Iterable[InputValues] | None, quantization_config: QuantizationParams, *, automatic_layout_conversion: bool = False, arm_only: bool = False, simulated_arm: bool = False, model_name: str | None = None, any_shape_on_mla: bool = False, log_level: int = logging.NOTSET) -> Model` (line 332) Decorators: `_sanitize_exceptions(ExceptionFuncType.LOADED_NET_QUANTIZE)`.
    Parameters:
    - `calibration_data`: type `Iterable[InputValues] | None`
    - `quantization_config`: type `QuantizationParams`
    - `automatic_layout_conversion`: type `bool`, default `False`
    - `arm_only`: type `bool`, default `False`
    - `simulated_arm`: type `bool`, default `False`
    - `model_name`: type `str | None`, default `None`
    - `any_shape_on_mla`: type `bool`, default `False`
    - `log_level`: type `int`, default `logging.NOTSET`
    Returns: Model
  - <a id="afe-apis-loaded-net-loadednet-quantize-with-accuracy-feedback"></a>`quantize_with_accuracy_feedback(calibration_data: Iterable[InputValues], evaluation_data: Iterable[tuple[InputValues, GroundTruth]], quantization_config: QuantizationParams, *, accuracy_score: Statistic[tuple[list[np.ndarray], GroundTruth], float], target_accuracy: float, automatic_layout_conversion: bool = False, max_optimization_steps: int | None = None, model_name: str | None = None, any_shape_on_mla: bool = False, log_level: int = logging.NOTSET) -> Model` (line 390) Decorators: `_sanitize_exceptions(ExceptionFuncType.LOADED_NET_QUANTIZE)`.
    Parameters:
    - `calibration_data`: type `Iterable[InputValues]`
    - `evaluation_data`: type `Iterable[tuple[InputValues, GroundTruth]]`
    - `quantization_config`: type `QuantizationParams`
    - `accuracy_score`: type `Statistic[tuple[list[np.ndarray], GroundTruth], float]`
    - `target_accuracy`: type `float`
    - `automatic_layout_conversion`: type `bool`, default `False`
    - `max_optimization_steps`: type `int | None`, default `None`
    - `model_name`: type `str | None`, default `None`
    - `any_shape_on_mla`: type `bool`, default `False`
    - `log_level`: type `int`, default `logging.NOTSET`
    Returns: Model
  - <a id="afe-apis-loaded-net-loadednet-convert-to-sima-quantization"></a>`convert_to_sima_quantization(*, requantization_mode: RequantizationMode = RequantizationMode.sima, model_name: str | None = None, any_shape_on_mla: bool = False, log_level: int = logging.NOTSET) -> Model` (line 448) Decorators: `_sanitize_exceptions(ExceptionFuncType.LOADED_NET_CONVERT)`.
    Parameters:
    - `requantization_mode`: type `RequantizationMode`, default `RequantizationMode.sima`
    - `model_name`: type `str | None`, default `None`
    - `any_shape_on_mla`: type `bool`, default `False`
    - `log_level`: type `int`, default `logging.NOTSET`
    Returns: Model

Functions:
- <a id="afe-apis-loaded-net-load-model"></a>`load_model(params: ImporterParams, *, target: Platform = gen1_target, custom_param_data: CustomPlatformParams | None = None, log_level: int = logging.NOTSET) -> LoadedNet` (line 487) Decorators: `_sanitize_exceptions(ExceptionFuncType.LOADED_NET_LOAD)`.
    Parameters:
    - `params`: type `ImporterParams`
    - `target`: type `Platform`, default `gen1_target`
    - `custom_param_data`: type `CustomPlatformParams | None`, default `None`
    - `log_level`: type `int`, default `logging.NOTSET`
    Returns: LoadedNet
