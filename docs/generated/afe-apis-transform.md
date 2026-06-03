<a id="afe-apis-transform"></a>
# `afe.apis.transform`

Source: `afe/apis/transform.py`

[Back to index](index.md)

Tensor transformations that can be applied to a model's input or output.

Imports:
- [`afe.apis.compilation_job_base.Tensor`](afe-apis-compilation_job_base.md#afe-apis-compilation-job-base-tensor)
- [`afe.apis.defines.ChromaSampling`](afe-apis-defines.md#afe-apis-defines-chromasampling)
- [`afe.apis.defines.ColorConversion`](afe-apis-defines.md#afe-apis-defines-colorconversion)
- [`afe.apis.defines.ColorSpaceStandard`](afe-apis-defines.md#afe-apis-defines-colorspacestandard)
- [`afe.apis.defines.ResizeDepositLocation`](afe-apis-defines.md#afe-apis-defines-resizedepositlocation)
- [`afe.apis.defines.ResizeMethod`](afe-apis-defines.md#afe-apis-defines-resizemethod)
- `afe.backends.Backend`
- `afe.core.configs.QuantizationConfigs`
- `afe.ir.defines.NodeName`
- `afe.ir.tensor_type.ScalarType`
- `afe.ir.tensor_type.TensorType`
- `afe.ir.tensor_type.TensorValue`
- `afe.ir.tensor_type.TupleValue`
- `afe.ir.tensor_type.data_byte_size`
- `afe.ir.tensor_type.scalar_type_to_dtype`
- `dataclasses`
- `ev_transforms.transforms as ev_transforms`
- `functools`
- `numpy as np`
- `typing.Callable`
- `typing.Sequence`

Classes:
- <a id="afe-apis-transform-transform"></a>`Transform` (line 54): A transformation on a tensor.
  - <a id="afe-apis-transform-transform-apply"></a>`apply(t: Tensor) -> Tensor` (line 58): Apply this transform to a tensor.  Raise an exception if the tensor's type is not suitable for this transform.
    Parameters:
    - `t`: type `Tensor`
    Returns: Tensor
  - <a id="afe-apis-transform-transform-get-result-type"></a>`get_result_type(parameter_type: TensorType) -> TensorType` (line 65): Get the type of this transform's output when it is applied to input of the given type.  Raise an exception if the transform cannot be applied to a tensor having the given type.
    Parameters:
    - `parameter_type`: type `TensorType`
    Returns: TensorType
  - <a id="afe-apis-transform-transform-extract-ir"></a>`extract_ir(input_type: TensorType, input_name: NodeName, output_base_name: NodeName) -> tuple[TensorType, list[_AwesomeNode]]` (line 73): Extract the internal representation of this transform.
    Parameters:
    - `input_type`: type `TensorType`
    - `input_name`: type `NodeName`
    - `output_base_name`: type `NodeName`
    Returns: tuple[TensorType, list[_AwesomeNode]]

Functions:
- <a id="afe-apis-transform-argmax"></a>`argmax(*, axis: int) -> Transform` (line 147): The argmax operation applied over a single axis of a tensor.
    Parameters:
    - `axis`: Axis to reduce
    Returns: The argmax transformation
- <a id="afe-apis-transform-reshape-transform"></a>`reshape_transform(*, newshape: list[int]) -> Transform` (line 179): The reshape_transform operation
    Parameters:
    - `newshape`: New shape after reshape transform
    Returns: The reshape transformation
- <a id="afe-apis-transform-layout-transform"></a>`layout_transform(*, src_layout: str, dst_layout: str) -> Transform` (line 227): The layout_transform operation.
    Parameters:
    - `src_layout`: Layout of the input tensor
    - `dst_layout`: Layout of the output tensor
    Returns: The layout_transform transformation
- <a id="afe-apis-transform-tessellation-transform"></a>`tessellation_transform(*, slice_shape: Sequence[int], align_c16: bool, cblock: bool) -> Transform` (line 314): The tessellation_transform operation.
    Parameters:
    - `slice_shape`: Shape of slice to tessellate.
    - `align_c16`: True to align channels to 16 in a tessellated slice
    - `cblock`: True to interleave the channel blocks in a tessellated slice.
    Returns: The tessellation_transform transformation
- <a id="afe-apis-transform-detessellation-transform"></a>`detessellation_transform(*, slice_shape: Sequence[int], align_c16: bool, cblock: bool, frame_type: TensorType) -> Transform` (line 395): The detessellation_transform operation.
    Parameters:
    - `slice_shape`: Shape of slice to detessellate
    - `align_c16`: True to indicate that slice channels are aligned to 16.
    - `cblock`: True to indicate that channel blocks are interleaved in a slice.
    - `frame_type`: Tensor type of de-tessellated frame
    Returns: The detessellation_transform transformation
- <a id="afe-apis-transform-pack-transform"></a>`pack_transform() -> _PackTransform` (line 460): The pack_transform operation.
    Returns: The pack_transform transformation
- <a id="afe-apis-transform-unpack-transform"></a>`unpack_transform(*, tensor_types: list[TensorType]) -> _UnpackTransform` (line 516): The unpack_transform operation.
    Parameters:
    - `tensor_types`: List of target tensor types after unpack
    Returns: The unpack_transform transformation
- <a id="afe-apis-transform-normalization-transform"></a>`normalization_transform(*, channel_params: list[tuple[float, float, float]]) -> Transform` (line 561): The normalization_transform operation.
    Parameters:
    - `channel_params`: The list of tuples for (divisor, mean, standard deviation)
    Returns: The normalization_transform transformation
- <a id="afe-apis-transform-quantization-transform"></a>`quantization_transform(*, channel_params: list[tuple[float, int]], num_bits: int, rounding: _RoundType = _RoundType.TONEAREST) -> Transform` (line 622): The quantization_transform operation.
    Parameters:
    - `channel_params`: The list of tuples for (quant_scale, zero_point)
    - `num_bits`: The number of bits used for quantization
    - `rounding`: The rounding type for quantization
    Returns: The quantization_transform transformation
- <a id="afe-apis-transform-dequantization-transform"></a>`dequantization_transform(*, channel_params: list[tuple[float, int]]) -> Transform` (line 678): The dequantization_transform operation.
    Parameters:
    - `channel_params`: The list of tuples for (quant_scale, zero_point)
    Returns: The dequantization_transform transformation
- <a id="afe-apis-transform-resize-transform"></a>`resize_transform(*, target_height: int, target_width: int, keep_aspect: bool, deposit_location: ResizeDepositLocation, method: ResizeMethod) -> Transform` (line 730): The resize_transform operation.
    Parameters:
    - `target_height`: Target height of resized tensor
    - `target_width`: Target width of resized tensor
    - `keep_aspect`: Boolean flag to keep aspect ratio
    - `deposit_location`: Enum to indicate deposit position of resized image
    - `method`: Enum to indicate supported interpolation methods
    Returns: The resize_transform transformation
- <a id="afe-apis-transform-chroma-upsample-transform"></a>`chroma_upsample_transform(*, frame_height: int, frame_width: int, yuv_sampling: ChromaSampling) -> Transform` (line 812): The chroma_upsample_transform operation.
    Parameters:
    - `frame_height`: Height of full sampling frame
    - `frame_width`: Width of full sampling frame
    - `yuv_sampling`: Chroma sampling Enum
    Returns: The chroma_upsample_transform transformation
- <a id="afe-apis-transform-yuv-rgb-conversion-transform"></a>`yuv_rgb_conversion_transform(*, conversion: ColorConversion, std: ColorSpaceStandard) -> Transform` (line 869): The yuv_rgb_conversion_transform operation.
    Parameters:
    - `conversion`: Direction of conversion between YUV and RGB
    - `std`: Standard for color space conversion
    Returns: The yuv_rgb_conversion_transform transformation
- <a id="afe-apis-transform-bgr-rgb-conversion-transform"></a>`bgr_rgb_conversion_transform(*, conversion: ColorConversion) -> Transform` (line 924): The bgr_rgb_conversion_transform operation.
    Parameters:
    - `conversion`: Direction of conversion between BGR and RGB
    Returns: The bgr_rgb_conversion_transform transformation
- <a id="afe-apis-transform-crop-transform"></a>`crop_transform(*, bounding_box: list[tuple[int, int]]) -> Transform` (line 1016): The crop_transform operation.
    Parameters:
    - `bounding_box`: Rectangle area to crop, as a list of 2 items. bounding_box[0] is the (x,y) position of the cropped area's origin within the input area. bounding_box[1] is the (x,y) past-the-end position of the cropped area within the input area.
    Returns: The crop_transform transformation
- <a id="afe-apis-transform-slice-transform"></a>`slice_transform(*, begin: list[int], end: list[int]) -> Transform` (line 1071): The slice_transform operation.
    Parameters:
    - `begin`: Begin indices for each dimension.
    - `end`: End indices for each dimension.
    Returns: The slice_transform transformation
- <a id="afe-apis-transform-sigmoid-transform"></a>`sigmoid_transform() -> Transform` (line 1115): The sigmoid_transform operation.
    Returns: The sigmoid_transform transformation
- <a id="afe-apis-transform-nms-maxpool-transform"></a>`nms_maxpool_transform(*, kernel: int) -> Transform` (line 1157): The nms_maxpool_transform operation.
    Parameters:
    - `kernel`: Size of pooling kernel
    Returns: The nms_maxpool_transform transformation
- <a id="afe-apis-transform-softmax-transform"></a>`softmax_transform(*, axis: int) -> Transform` (line 1192): The softmax transform operation.
    Parameters:
    - `axis`: Axis to sum over
    Returns: The softmax transform
- <a id="afe-apis-transform-compose"></a>`compose(transforms: list[Transform]) -> Transform` (line 1231): Make a transform that is the composition of the given transforms.
    Parameters:
    - `transforms`: Transforms to compose
    Returns: Their composition
- <a id="afe-apis-transform-identity"></a>`identity() -> Transform` (line 1272): An identity transformation on a tensor.
    Returns: Transform
