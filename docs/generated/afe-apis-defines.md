<a id="afe-apis-defines"></a>
# `afe.apis.defines`

Source: `afe/apis/defines.py`

[Back to index](index.md)

This file contains definitions of the types exposed by the development API for AFE.

Imports:
- [`afe.apis.error_handling_variables`](afe-apis-error_handling_variables.md)
- `afe.backends.mla.afe_to_n2a_compiler.defines.TensorDRAMLayout`
- `afe.backends.mla.afe_to_n2a_compiler.defines.TensorTessellateParameters`
- `afe.backends.mla.afe_to_n2a_compiler.defines.TessellateParameters`
- `afe.ir.defines.BiasCorrectionType`
- `afe.ir.defines.InputName`
- `afe.ir.defines.NodeName`
- `afe.ir.defines.RequantizationMode`
- `afe.ir.tensor_type.ScalarType`
- `afe.ir.tensor_type.TensorType`
- `afe.ir.tensor_type.scalar_type_from_dtype`
- `afe.ir.tensor_type.scalar_type_to_dtype`
- `afe.ir.utils.transpose_tensor_according_to_layout_strings`
- `dataclasses`
- `dataclasses.dataclass`
- `enum.Enum`
- `enum.auto`
- `numpy as np`
- `sima_utils.common.CustomPlatformParams`
- `sima_utils.common.Platform`
- `sima_utils.common.load_custom_config`
- `sima_utils.logging.sima_logger`
- `typing.Any`
- `typing.ContextManager`
- `typing.Dict`
- `typing.List`
- `typing.Optional`
- `typing.Set`

Constants:
- <a id="afe-apis-defines-inputvalues"></a>`InputValues` (line 35) [default/value `Dict[InputName, np.ndarray]`]
- <a id="afe-apis-defines-gen1-target"></a>`gen1_target` (line 38) [default/value `Platform.GEN1`]
- <a id="afe-apis-defines-gen2-target"></a>`gen2_target` (line 39) [default/value `Platform.GEN2`]
- <a id="afe-apis-defines-gen-custom-target"></a>`gen_custom_target` (line 40) [default/value `Platform.GEN_CUSTOM`]
- <a id="afe-apis-defines-bt-color-coeff"></a>`BT_COLOR_COEFF` (line 131) [type `Dict[ColorSpaceStandard, List[float]]` ; default/value `{ColorSpaceStandard.BT601: [0.299, 0.587, 0.114, 1.772, 1.402], ColorSpaceStandard.BT709: [0.2126, 0.7152, 0.0722, 1.8556, 1.5748], ColorSpaceStandard.BT2020: [0.2627, 0.678, 0.0593, 1.8814, 1.4747]}`]
- <a id="afe-apis-defines-yuv2rgb-full-range-constants"></a>`YUV2RGB_FULL_RANGE_CONSTANTS` (line 138) [type `Dict[str, List[float]]` ; default/value `{'offset': [16, 128, 128], 'scale': [255 / 219, 255 / 224, 255 / 224]}`]
- <a id="afe-apis-defines-default-quantization"></a>`default_quantization` (line 371) [type `QuantizationParams` ; default/value `QuantizationParams(calibration_method=(default_calibration()), activation_quantization_scheme=(quantization_scheme(True, False)), weight_quantization_scheme=(quantization_scheme(False, True)), requantization_mode=(RequantizationMode.sima), node_names={''}, custom_quantization_configs=None)`]
Classes:
- <a id="afe-apis-defines-exceptionfunctype"></a>`ExceptionFuncType(Enum)` (line 43)
  Enum Members:
  - <a id="afe-apis-defines-exceptionfunctype-loaded-net-load"></a>`LOADED_NET_LOAD` (line 44) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-loaded-net-execute"></a>`LOADED_NET_EXECUTE` (line 45) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-loaded-net-quantize"></a>`LOADED_NET_QUANTIZE` (line 46) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-loaded-net-convert"></a>`LOADED_NET_CONVERT` (line 47) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-model-execute"></a>`MODEL_EXECUTE` (line 48) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-model-save"></a>`MODEL_SAVE` (line 49) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-model-load"></a>`MODEL_LOAD` (line 50) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-model-compile"></a>`MODEL_COMPILE` (line 51) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-model-create-auxiliary"></a>`MODEL_CREATE_AUXILIARY` (line 52) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-model-compose"></a>`MODEL_COMPOSE` (line 53) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-model-evaluate"></a>`MODEL_EVALUATE` (line 54) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-model-performance"></a>`MODEL_PERFORMANCE` (line 55) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-generate-elf-files"></a>`GENERATE_ELF_FILES` (line 56) [default/value `auto()`]
  - <a id="afe-apis-defines-exceptionfunctype-quantization-error-analysis"></a>`QUANTIZATION_ERROR_ANALYSIS` (line 57) [default/value `auto()`]
- <a id="afe-apis-defines-colorspacestandard"></a>`ColorSpaceStandard(str, Enum)` (line 121): Color space standards for YUV and RGB conversion. BT601 is for SD video; BT709 is for HD video; BT2020 is for HDR.
  Enum Members:
  - <a id="afe-apis-defines-colorspacestandard-bt601"></a>`BT601` (line 126) [default/value `'BT601'`]
  - <a id="afe-apis-defines-colorspacestandard-bt709"></a>`BT709` (line 127) [default/value `'BT709'`]
  - <a id="afe-apis-defines-colorspacestandard-bt2020"></a>`BT2020` (line 128) [default/value `'BT2020'`]
- <a id="afe-apis-defines-colorconversion"></a>`ColorConversion(str, Enum)` (line 144): Color conversion direction.
  Enum Members:
  - <a id="afe-apis-defines-colorconversion-yuv2rgb"></a>`YUV2RGB` (line 148) [default/value `'YUV2RGB'`]
  - <a id="afe-apis-defines-colorconversion-rgb2yuv"></a>`RGB2YUV` (line 149) [default/value `'RGB2YUV'`]
  - <a id="afe-apis-defines-colorconversion-bgr2rgb"></a>`BGR2RGB` (line 150) [default/value `'BGR2RGB'`]
  - <a id="afe-apis-defines-colorconversion-rgb2bgr"></a>`RGB2BGR` (line 151) [default/value `'RGB2BGR'`]
- <a id="afe-apis-defines-chromasampling"></a>`ChromaSampling(str, Enum)` (line 154): Chroma sub-sampling representation.
  Enum Members:
  - <a id="afe-apis-defines-chromasampling-nv12"></a>`NV12` (line 158) [default/value `'NV12'`]
  - <a id="afe-apis-defines-chromasampling-yuv420"></a>`YUV420` (line 159) [default/value `'YUV420'`]
  - <a id="afe-apis-defines-chromasampling-yuv422"></a>`YUV422` (line 160) [default/value `'YUV422'`]
- <a id="afe-apis-defines-resizemethod"></a>`ResizeMethod(str, Enum)` (line 163): Interpolation method used in resize transform.
  Enum Members:
  - <a id="afe-apis-defines-resizemethod-linear"></a>`LINEAR` (line 167) [default/value `'linear'`]
  - <a id="afe-apis-defines-resizemethod-nearest"></a>`NEAREST` (line 168) [default/value `'nearest'`]
  - <a id="afe-apis-defines-resizemethod-area"></a>`AREA` (line 169) [default/value `'area'`]
  - <a id="afe-apis-defines-resizemethod-cubic"></a>`CUBIC` (line 170) [default/value `'cubic'`]
- <a id="afe-apis-defines-resizedepositlocation"></a>`ResizeDepositLocation(str, Enum)` (line 173): Deposit location of resized image in padded frame.
  Enum Members:
  - <a id="afe-apis-defines-resizedepositlocation-topleft"></a>`TOPLEFT` (line 177) [default/value `'topleft'`]
  - <a id="afe-apis-defines-resizedepositlocation-center"></a>`CENTER` (line 178) [default/value `'center'`]
  - <a id="afe-apis-defines-resizedepositlocation-bottomright"></a>`BOTTOMRIGHT` (line 179) [default/value `'bottomright'`]
- <a id="afe-apis-defines-calibrationmethod"></a>`CalibrationMethod` (line 182) Decorators: `dataclass`.
  Attributes:
  - <a id="afe-apis-defines-calibrationmethod-name"></a>`name` (line 187)
  - <a id="afe-apis-defines-calibrationmethod-from-str"></a>`from_str(method: str)` (line 190) Decorators: `staticmethod`.
    Parameters:
    - `method`: type `str`
- <a id="afe-apis-defines-minmaxmethod"></a>`MinMaxMethod(CalibrationMethod)` (line 210) Decorators: `dataclass`.
- <a id="afe-apis-defines-histogrammsemethod"></a>`HistogramMSEMethod(CalibrationMethod)` (line 216) Decorators: `dataclass`.
  Attributes:
  - <a id="afe-apis-defines-histogrammsemethod-num-bins"></a>`num_bins` (line 221) [type `int` ; default/value `num_bins`]
- <a id="afe-apis-defines-movingaverageminmaxmethod"></a>`MovingAverageMinMaxMethod(CalibrationMethod)` (line 225) Decorators: `dataclass`.
- <a id="afe-apis-defines-histogramentropymethod"></a>`HistogramEntropyMethod(CalibrationMethod)` (line 231) Decorators: `dataclass`.
  Attributes:
  - <a id="afe-apis-defines-histogramentropymethod-num-bins"></a>`num_bins` (line 236) [type `int` ; default/value `num_bins`]
- <a id="afe-apis-defines-histogrampercentilemethod"></a>`HistogramPercentileMethod(CalibrationMethod)` (line 240) Decorators: `dataclass`.
  Attributes:
  - <a id="afe-apis-defines-histogrampercentilemethod-percentile-value"></a>`percentile_value` (line 246) [type `float` ; default/value `percentile_value`]
  - <a id="afe-apis-defines-histogrampercentilemethod-num-bins"></a>`num_bins` (line 247) [type `int` ; default/value `num_bins`]
- <a id="afe-apis-defines-skipcalibration"></a>`SkipCalibration(CalibrationMethod)` (line 251): Directive to skip calibration. Decorators: `dataclass`.
- <a id="afe-apis-defines-quantizationscheme"></a>`QuantizationScheme` (line 264): Quantization scheme. Decorators: `dataclass`.
  Attributes:
  - <a id="afe-apis-defines-quantizationscheme-asymmetric"></a>`asymmetric` (line 274) [type `bool`]
  - <a id="afe-apis-defines-quantizationscheme-per-channel"></a>`per_channel` (line 275) [type `bool`]
  - <a id="afe-apis-defines-quantizationscheme-bits"></a>`bits` (line 276) [type `int` ; default/value `8`]
  - <a id="afe-apis-defines-quantizationscheme-bf16"></a>`bf16` (line 277) [type `bool` ; default/value `False`]
- <a id="afe-apis-defines-quantizationparams"></a>`QuantizationParams` (line 295): Parameters controlling how to quantize a network. Decorators: `dataclass`.
  Attributes:
  - <a id="afe-apis-defines-quantizationparams-calibration-method"></a>`calibration_method` (line 312) [type `CalibrationMethod`]
  - <a id="afe-apis-defines-quantizationparams-activation-quantization-scheme"></a>`activation_quantization_scheme` (line 313) [type `QuantizationScheme`]
  - <a id="afe-apis-defines-quantizationparams-weight-quantization-scheme"></a>`weight_quantization_scheme` (line 314) [type `QuantizationScheme`]
  - <a id="afe-apis-defines-quantizationparams-requantization-mode"></a>`requantization_mode` (line 315) [type `RequantizationMode` ; default/value `RequantizationMode.sima`]
  - <a id="afe-apis-defines-quantizationparams-node-names"></a>`node_names` (line 316) [type `Set[str]` ; default/value `dataclasses.field(default_factory=set)`]
  - <a id="afe-apis-defines-quantizationparams-custom-quantization-configs"></a>`custom_quantization_configs` (line 317) [type `Optional[Dict[NodeName, Dict[str, Any]]]` ; default/value `None`]
  - <a id="afe-apis-defines-quantizationparams-biascorr-type"></a>`biascorr_type` (line 318) [type `BiasCorrectionType` ; default/value `BiasCorrectionType.NONE`]
  - <a id="afe-apis-defines-quantizationparams-channel-equalization"></a>`channel_equalization` (line 319) [type `bool` ; default/value `False`]
  - <a id="afe-apis-defines-quantizationparams-smooth-quant"></a>`smooth_quant` (line 320) [type `bool` ; default/value `False`]
  - <a id="afe-apis-defines-quantizationparams-prefer-int8-udf"></a>`prefer_int8_udf` (line 321) [type `bool` ; default/value `True`]
  - <a id="afe-apis-defines-quantizationparams-with-calibration"></a>`with_calibration(method: CalibrationMethod) -> QuantizationParams` (line 323)
    Parameters:
    - `method`: type `CalibrationMethod`
    Returns: QuantizationParams
  - <a id="afe-apis-defines-quantizationparams-with-activation-quantization"></a>`with_activation_quantization(scheme: QuantizationScheme) -> QuantizationParams` (line 327)
    Parameters:
    - `scheme`: type `QuantizationScheme`
    Returns: QuantizationParams
  - <a id="afe-apis-defines-quantizationparams-with-weight-quantization"></a>`with_weight_quantization(scheme: QuantizationScheme) -> QuantizationParams` (line 331)
    Parameters:
    - `scheme`: type `QuantizationScheme`
    Returns: QuantizationParams
  - <a id="afe-apis-defines-quantizationparams-with-requantization-mode"></a>`with_requantization_mode(requantization_mode: RequantizationMode)` (line 335)
    Parameters:
    - `requantization_mode`: type `RequantizationMode`
  - <a id="afe-apis-defines-quantizationparams-with-unquantized-nodes"></a>`with_unquantized_nodes(node_names: Set[str]) -> QuantizationParams` (line 339)
    Parameters:
    - `node_names`: type `Set[str]`
    Returns: QuantizationParams
  - <a id="afe-apis-defines-quantizationparams-with-custom-quantization-configs"></a>`with_custom_quantization_configs(custom_quantization_configs: Dict[NodeName, Dict[str, Any]])` (line 343)
    Parameters:
    - `custom_quantization_configs`: type `Dict[NodeName, Dict[str, Any]]`
  - <a id="afe-apis-defines-quantizationparams-with-bias-correction"></a>`with_bias_correction(enable: bool | BiasCorrectionType = True)` (line 347)
    Parameters:
    - `enable`: type `bool | BiasCorrectionType`, default `True`
  - <a id="afe-apis-defines-quantizationparams-with-channel-equalization"></a>`with_channel_equalization(enable: bool = True)` (line 358)
    Parameters:
    - `enable`: type `bool`, default `True`
  - <a id="afe-apis-defines-quantizationparams-with-smooth-quant"></a>`with_smooth_quant(enable: bool = True)` (line 362)
    Parameters:
    - `enable`: type `bool`, default `True`
  - <a id="afe-apis-defines-quantizationparams-with-prefer-int8-udf"></a>`with_prefer_int8_udf(mode: bool = True)` (line 366)
    Parameters:
    - `mode`: type `bool`, default `True`

Functions:
- <a id="afe-apis-defines-default-calibration"></a>`default_calibration() -> CalibrationMethod` (line 260)
    Returns: CalibrationMethod
- <a id="afe-apis-defines-quantization-scheme"></a>`quantization_scheme(asymmetric: bool, per_channel: bool, bits: int = 8) -> QuantizationScheme` (line 280): Constructs quantization scheme.
    Parameters:
    - `asymmetric`: type `bool`
    - `per_channel`: type `bool`
    - `bits`: type `int`, default `8`
    Returns: QuantizationScheme
- <a id="afe-apis-defines-bfloat16-scheme"></a>`bfloat16_scheme() -> QuantizationScheme` (line 287): Constructs a bfloat16 quantization scheme. It directs the compiler to use bfloat16 instead of integer quantization.
    Returns: QuantizationScheme
