<a id="afe-apis-model"></a>
# `afe.apis.model`

Source: `afe/apis/model.py`

[Back to index](index.md)

Imports:
- [`afe.apis.compilation_job_base.GroundTruth`](afe-apis-compilation_job_base.md#afe-apis-compilation-job-base-groundtruth)
- [`afe.apis.defines.ExceptionFuncType`](afe-apis-defines.md#afe-apis-defines-exceptionfunctype)
- [`afe.apis.defines.InputValues`](afe-apis-defines.md#afe-apis-defines-inputvalues)
- [`afe.apis.defines.gen1_target`](afe-apis-defines.md#afe-apis-defines-gen1-target)
- [`afe.apis.release_v1.compose_awesomenets`](afe-apis-release_v1.md#afe-apis-release-v1-compose-awesomenets)
- [`afe.apis.release_v1.create_auxiliary_processing_network`](afe-apis-release_v1.md#afe-apis-release-v1-create-auxiliary-processing-network)
- `afe.apis.statistic.Statistic`
- [`afe.apis.transform.Transform`](afe-apis-transform.md#afe-apis-transform-transform)
- `afe.backends.mpk.interface.L2CachingMode`
- `afe.backends.mpk.interface.TessellateParameters`
- `afe.core.graph_analyzer.analyzed_results.AnalyzedResultDict`
- `afe.core.graph_analyzer.graph_analyzer.QuantizedGraphAnalyzer`
- `afe.core.graph_analyzer.utils.Metric`
- `afe.core.graph_analyzer.utils.QuantizedGraphAnalyzerMode`
- `afe.core.utils.LengthHintedIterable`
- `afe.devkit.devkit_context_manager.SetupConnection`
- `afe.ir.attributes as afe_attrs`
- `afe.ir.defines.InputName`
- `afe.ir.defines.LayerStats`
- `afe.ir.defines.NodeName`
- `afe.ir.defines.Status`
- `afe.ir.net.AwesomeNet`
- `afe.ir.node.node_is_awesomenet`
- `afe.ir.node.node_is_ev`
- `afe.ir.node.node_is_external`
- `afe.ir.node.node_is_subgraph`
- `afe.ir.node.node_is_tuple`
- `afe.ir.node.node_is_tuple_get_item`
- `afe.ir.sima_ir.SiMaIR`
- `afe.ir.tensor_type.TensorType`
- `copy`
- `devkit_inference_models.utils.connection_params as cp`
- `logging`
- `numpy as np`
- `os`
- `os.path`
- `pickle`
- `re`
- `sima_utils.common.Platform`
- `sima_utils.common.print_progressbar`
- `sima_utils.logging.sima_logger`
- `tempfile`
- `typing.Any`
- `typing.Dict`
- `typing.Iterable`
- `typing.List`
- `typing.Optional`
- `typing.Tuple`

Classes:
- <a id="afe-apis-model-model"></a>`Model` (line 200)
  - <a id="afe-apis-model-model-execute"></a>`execute(inputs: InputValues, *, fast_mode: bool = False, use_jax: bool = False, log_level: int | None = logging.NOTSET, keep_layer_outputs: list[NodeName] | str | None = None, output_file_path: str | None = None) -> List[np.ndarray]` (line 212): Run input data through the quantized model. Decorators: `_sanitize_exceptions(ExceptionFuncType.MODEL_EXECUTE)`.
    Parameters:
    - `inputs`: type `InputValues`
    - `fast_mode`: type `bool`, default `False`
    - `use_jax`: type `bool`, default `False`
    - `log_level`: type `int | None`, default `logging.NOTSET`
    - `keep_layer_outputs`: type `list[NodeName] | str | None`, default `None`
    - `output_file_path`: type `str | None`, default `None`
    Returns: List[np.ndarray]
  - <a id="afe-apis-model-model-save"></a>`save(model_name: str, output_directory: str = '', *, log_level: Optional[int] = logging.NOTSET, include_unquantized_net: bool = True) -> None` (line 282) Decorators: `_sanitize_exceptions(ExceptionFuncType.MODEL_SAVE)`.
    Parameters:
    - `model_name`: type `str`
    - `output_directory`: type `str`, default `''`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
    - `include_unquantized_net`: type `bool`, default `True`
    Returns: None
  - <a id="afe-apis-model-model-load"></a>`load(model_name: str, network_directory: str = '', *, log_level: Optional[int] = logging.NOTSET, include_unquantized_net: bool = True) -> Model` (line 299) Decorators: `staticmethod, _sanitize_exceptions(ExceptionFuncType.MODEL_LOAD)`.
    Parameters:
    - `model_name`: type `str`
    - `network_directory`: type `str`, default `''`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
    - `include_unquantized_net`: type `bool`, default `True`
    Returns: Model
  - <a id="afe-apis-model-model-compile"></a>`compile(output_path: str, batch_size: int = 1, compress: bool = True, log_level: Optional[int] = logging.NOTSET, tessellate_parameters: Optional[TessellateParameters] = None, l2_caching_mode: L2CachingMode = L2CachingMode.NONE, preserve: bool = True, **kwargs) -> None` (line 316): Compile the model and generate MPK JSON file. Decorators: `_sanitize_exceptions(ExceptionFuncType.MODEL_COMPILE)`.
    Parameters:
    - `output_path`: type `str`
    - `batch_size`: type `int`, default `1`
    - `compress`: type `bool`, default `True`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
    - `tessellate_parameters`: type `Optional[TessellateParameters]`, default `None`
    - `l2_caching_mode`: type `L2CachingMode`, default `L2CachingMode.NONE`
    - `preserve`: type `bool`, default `True`
    - `kwargs`: default `{}`
    Returns: None
  - <a id="afe-apis-model-model-create-auxiliary-network"></a>`create_auxiliary_network(transforms: List[Transform], input_types: Dict[InputName, TensorType], *, target: Platform = gen1_target, log_level: Optional[int] = logging.NOTSET) -> Model` (line 370) Decorators: `staticmethod, _sanitize_exceptions(ExceptionFuncType.MODEL_CREATE_AUXILIARY)`.
    Parameters:
    - `transforms`: type `List[Transform]`
    - `input_types`: type `Dict[InputName, TensorType]`
    - `target`: type `Platform`, default `gen1_target`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
    Returns: Model
  - <a id="afe-apis-model-model-compose"></a>`compose(nets: List[Model], combined_model_name: str = 'main', log_level: Optional[int] = logging.NOTSET) -> Model` (line 392) Decorators: `staticmethod, _sanitize_exceptions(ExceptionFuncType.MODEL_COMPOSE)`.
    Parameters:
    - `nets`: type `List[Model]`
    - `combined_model_name`: type `str`, default `'main'`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
    Returns: Model
  - <a id="afe-apis-model-model-evaluate"></a>`evaluate(evaluation_data: Iterable[Tuple[InputValues, GroundTruth]], criterion: Statistic[Tuple[List[np.ndarray], GroundTruth], str], *, fast_mode: bool = False, log_level: Optional[int] = logging.NOTSET) -> str` (line 410) Decorators: `_sanitize_exceptions(ExceptionFuncType.MODEL_EVALUATE)`.
    Parameters:
    - `evaluation_data`: type `Iterable[Tuple[InputValues, GroundTruth]]`
    - `criterion`: type `Statistic[Tuple[List[np.ndarray], GroundTruth], str]`
    - `fast_mode`: type `bool`, default `False`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
    Returns: str
  - <a id="afe-apis-model-model-analyze-quantization-error"></a>`analyze_quantization_error(evaluation_data: Iterable[InputValues], error_metric: Metric, *, local_feed: bool, log_level: Optional[int] = logging.NOTSET)` (line 428) Decorators: `_sanitize_exceptions(ExceptionFuncType.QUANTIZATION_ERROR_ANALYSIS)`.
    Parameters:
    - `evaluation_data`: type `Iterable[InputValues]`
    - `error_metric`: type `Metric`
    - `local_feed`: type `bool`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
  - <a id="afe-apis-model-model-get-performance-metrics"></a>`get_performance_metrics(output_kpi_path: str, *, log_level: Optional[int] = logging.NOTSET)` (line 453) Decorators: `_sanitize_exceptions(ExceptionFuncType.MODEL_PERFORMANCE)`.
    Parameters:
    - `output_kpi_path`: type `str`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
  - <a id="afe-apis-model-model-generate-elf-and-reference-files"></a>`generate_elf_and_reference_files(input_data: Iterable[InputValues], output_dir: str, *, batch_size: int = 1, compress: bool = True, tessellate_parameters: Optional[TessellateParameters] = None, log_level: Optional[int] = logging.NOTSET, l2_caching_mode: L2CachingMode = L2CachingMode.NONE) -> None` (line 473) Decorators: `_sanitize_exceptions(ExceptionFuncType.GENERATE_ELF_FILES)`.
    Parameters:
    - `input_data`: type `Iterable[InputValues]`
    - `output_dir`: type `str`
    - `batch_size`: type `int`, default `1`
    - `compress`: type `bool`, default `True`
    - `tessellate_parameters`: type `Optional[TessellateParameters]`, default `None`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
    - `l2_caching_mode`: type `L2CachingMode`, default `L2CachingMode.NONE`
    Returns: None
  - <a id="afe-apis-model-model-execute-in-accelerator-mode"></a>`execute_in_accelerator_mode(input_data: Iterable[InputValues], devkit: str, *, username: str = cp.DEFAULT_USERNAME, password: str = '', batch_size: int = 1, compress: bool = True, tessellate_parameters: Optional[TessellateParameters] = None, log_level: Optional[int] = logging.NOTSET, l2_caching_mode: L2CachingMode = L2CachingMode.NONE) -> List[np.ndarray]` (line 511) Decorators: `_sanitize_exceptions(ExceptionFuncType.GENERATE_ELF_FILES)`.
    Parameters:
    - `input_data`: type `Iterable[InputValues]`
    - `devkit`: type `str`
    - `username`: type `str`, default `cp.DEFAULT_USERNAME`
    - `password`: type `str`, default `''`
    - `batch_size`: type `int`, default `1`
    - `compress`: type `bool`, default `True`
    - `tessellate_parameters`: type `Optional[TessellateParameters]`, default `None`
    - `log_level`: type `Optional[int]`, default `logging.NOTSET`
    - `l2_caching_mode`: type `L2CachingMode`, default `L2CachingMode.NONE`
    Returns: List[np.ndarray]
