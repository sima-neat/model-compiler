<a id="afe-apis-prerelease-v1"></a>
# `afe.apis.prerelease_v1`

Source: `afe/apis/prerelease_v1.py`

[Back to index](index.md)

This is the pre-release API for AFE.  It supports importing models, loading and storing AFE's internal format, quantizing, executing, and simulating.

Imports:
- [`afe.apis.defines.gen1_target`](afe-apis-defines.md#afe-apis-defines-gen1-target)
- `afe.ir.defines.Status`
- `afe.ir.tensor_type.ScalarType`
- `csv`
- `numpy as np`
- `os`
- `sima_utils.common.Platform`
- `sima_utils.data.data_generator.DataGenerator`
- `subprocess`
- `tempfile`
- `typing.Dict`
- `typing.List`
- `typing.Optional`
- `typing.Tuple`

Functions:
- <a id="afe-apis-prerelease-v1-load-onnx-model"></a>`load_onnx_model(model_path: str, shape_dict: Dict[str, Tuple[int, ...]], dtype_dict: Dict[str, ScalarType], layout: str = 'NCHW', is_quantized: bool = False) -> _AwesomeNet` (line 42): Loads an ONNX model into an _AwesomeNet format.
    Parameters:
    - `model_path`: Path to a .onnx file containing the onnx model
    - `shape_dict`: Dictionary of input names to input shapes eg. {'input', (1,224,224,3)}
    - `dtype_dict`: Dictionary of input names to input types eg. {'input', 'float32'}
    - `layout`: Input data layout. Default is 'NCHW'
    - `is_quantized`: Whether the model is pre-quantized. Default is False
    Returns: An _AwesomeNet
- <a id="afe-apis-prerelease-v1-load-pytorch-model"></a>`load_pytorch_model(model_path: str, input_names: List[str], input_shapes: List[Tuple[int, ...]], input_dtypes: Optional[List[ScalarType]] = None, layout: str = 'NCHW', is_quantized: bool = False) -> _AwesomeNet` (line 62): Loads a PyTorch model into an _AwesomeNet format.
    Parameters:
    - `model_path`: Path to a PyTorch file (.pt) that contains the entire model
    - `input_names`: List of input names. eg ['input']
    - `input_shapes`: List of input shapes corresponding to input names. eg. [(1, 224, 224, 3)]
    - `input_dtypes`: List of input datatypes corresponding to input names. eg ['float32']
    - `layout`: Input data layout. Default is 'NCHW'
    - `is_quantized`: Whether the model is pre-quantized. Default is False
    Returns: An _AwesomeNet
- <a id="afe-apis-prerelease-v1-load-tensorflow-model"></a>`load_tensorflow_model(model_path: str, shape_dict: Dict[str, Tuple[int, ...]], output_names: List[str], layout: str = 'NHWC', is_quantized: bool = False) -> _AwesomeNet` (line 84): Loads a TensorFlow model into an _AwesomeNet format
    Parameters:
    - `model_path`: Path to a .pb TensorFlow model
    - `shape_dict`: Dictionary of input names to input shapes eg. {'input', (1,224,224,3)}
    - `output_names`: List of output names of the network eg. ['output1', 'output2']
    - `layout`: any variation of the characters NHWC representing Batch Size, Height, Width, and Channels
    - `is_quantized`: Whether the model is pre-quantized. Default is False
    Returns: An _AwesomeNet
- <a id="afe-apis-prerelease-v1-load-tensorflow2-model"></a>`load_tensorflow2_model(model_path: str, shape_dict: Dict[str, Tuple[int, ...]], output_names: List[str], layout: str = 'NHWC', is_quantized: bool = False) -> _AwesomeNet` (line 104): Loads a TensorFlow model into an _AwesomeNet format
    Parameters:
    - `model_path`: Path to a SavedModel tensorflow model.
    - `shape_dict`: Dictionary of input names to input shapes eg. {'input', (1,224,224,3)}
    - `output_names`: List of output names of the network eg. ['output1', 'output2']
    - `layout`: any variation of the characters NHWC representing Batch Size, Height, Width, and Channels
    - `is_quantized`: Whether the model is pre-quantized. Default is False
    Returns: An _AwesomeNet
- <a id="afe-apis-prerelease-v1-load-tflite-model"></a>`load_tflite_model(model_path: str, shape_dict: Dict[str, Tuple[int, ...]], dtype_dict: Dict[str, ScalarType], layout: str = 'NHWC', is_quantized: bool = False) -> _AwesomeNet` (line 124): Loads a TensorFlow Lite model into an _AwesomeNet format.
    Parameters:
    - `model_path`: Path to a .tflite file containing the TensorFlow Lite model
    - `shape_dict`: Dictionary of input names to input shapes eg. {'input', (1,224,224,3)}
    - `dtype_dict`: Dictionary of input names to input types eg. {'input', 'float32'}
    - `layout`: Input data layout. Default is 'NHWC'
    - `is_quantized`: Whether the model is pre-quantized. Default is False
    Returns: An _AwesomeNet
- <a id="afe-apis-prerelease-v1-load-keras-model"></a>`load_keras_model(model_path: str, shape_dict: Dict[str, Tuple[int, ...]], layout: str = 'NCHW', is_quantized: bool = False) -> _AwesomeNet` (line 144): Loads a Keras model into an _AwesomeNet format.
    Parameters:
    - `model_path`: Path to a .h5 file containing the keras model
    - `shape_dict`: Dictionary of input names to input shapes eg. {'input', (1,224,224,3)}
    - `layout`: Input data layout. Default is 'NCHW'
    - `is_quantized`: Whether the model is pre-quantized. Default is False
    Returns: An _AwesomeNet
- <a id="afe-apis-prerelease-v1-load-caffe-model"></a>`load_caffe_model(prototxt_file_path: str, caffemodel_file_path: str, shape_dict: Dict[str, Tuple[int, ...]], dtype_dict: Dict[str, ScalarType], layout: str = 'NCHW', is_quantized: bool = False) -> _AwesomeNet` (line 162): Loads a caffe model into an _AwesomeNet format.
    Parameters:
    - `prototxt_file_path`: filepath to the caffe .prototxt file
    - `caffemodel_file_path`: filepath to the caffe .caffemodel file
    - `shape_dict`: Dictionary of input names to input shapes eg. {'input', (1,224,224,3)}
    - `dtype_dict`: Dictionary of input names to input types eg. {'input', 'float32'}
    - `layout`: Input data layout. Default is 'NCHW'
    - `is_quantized`: Whether the model is pre-quantized. Default is False
    Returns: An _AwesomeNet
- <a id="afe-apis-prerelease-v1-load-caffe2-model"></a>`load_caffe2_model(init_net_file_path: str, predict_net_file_path: str, shape_dict: Dict[str, Tuple[int, ...]], dtype_dict: Dict[str, ScalarType], layout: str = 'NCHW', is_quantized: bool = False) -> _AwesomeNet` (line 184): Loads a caffe2 model into an _AwesomeNet format.
    Parameters:
    - `init_net_file_path`: filepath to the caffe2 .pb init_net file
    - `predict_net_file_path`: filepath to the caffe2 .pb predict_net file
    - `shape_dict`: Dictionary of input names to input shapes eg. {'input', (1,224,224,3)}
    - `dtype_dict`: Dictionary of input names to input types eg. {'input', 'float32'}
    - `layout`: Input data layout. Default is 'NCHW'
    - `is_quantized`: Whether the model is pre-quantized. Default is False
    Returns: An _AwesomeNet
- <a id="afe-apis-prerelease-v1-quantize-net"></a>`quantize_net(net: _AwesomeNet, input_generator: DataGenerator, asymmetry: bool, per_channel: bool, max_calibration_samples: int)` (line 209): Quantizes a network.
    Parameters:
    - `net`: an _AwesomeNet
    - `input_generator`: a DataGenerator we use to feed inputs into the _AwesomeNet during calibration
    - `asymmetry`: If True this function performs asymmetric quantization. Otherwise, it performs symmetric quantization
    - `per_channel`: If True this function performs per_channel quantization.
    - `max_calibration_samples`: Maximum number of samples we use for calibration
- <a id="afe-apis-prerelease-v1-execute-net"></a>`execute_net(net: _AwesomeNet, inputs: Dict[str, np.ndarray], dequantize_outputs: bool = True) -> List[np.ndarray]` (line 238): Executes a network.
    Parameters:
    - `net`: an _AwesomeNet
    - `inputs`: Dictionary of placeholder node names (str) to the input data
    - `dequantize_outputs`: Whether to dequantize the output data to floating point :return The result of executing the output node
    Returns: List[np.ndarray]
- <a id="afe-apis-prerelease-v1-compile-net"></a>`compile_net(net: _AwesomeNet, output_elf_path: str, compress: bool = True)` (line 259): Compile a network using Product Compiler.
    Parameters:
    - `net`: an _AwesomeNet.
    - `output_elf_path`: Path in which elf files should be created.
    - `compress`: If True mlc file is compressed before generating .elf file.
- <a id="afe-apis-prerelease-v1-simulate-isim-module"></a>`simulate_isim_module(elf_file: str, output_path: str, output_kpi_file_name: Optional[str] = None, output_trace_file_name: Optional[str] = None, generate_csv_kpi: Optional[bool] = True, override_existing: Optional[bool] = False, target: Optional[Platform] = None)` (line 277): Wrapper to take elf file and generate summary KPI file, and trace file.
    Parameters:
    - `elf_file`: Path to the location of the elf file to simulate in ISIM.
    - `output_path`: Location of where to store all output files. If location does not exist, it will be created.
    - `output_kpi_file_name`: Name for output kpi file. Default: elf_file name without '.elf' extension and finishing with '_kpis.txt' postfix.
    - `output_trace_file_name`: Name for output trace file. Default: elf_file name without '.elf' extension and finishing with '_trace.mpack' postfix.
    - `generate_csv_kpi`: Whether to generate a CSV file with the KPIs in addition to the txt.
    - `override_existing`: Whether to override existing kpis and trace files from a previous run.
    - `target`: [Optional] platform target.
- <a id="afe-apis-prerelease-v1-isim-net"></a>`isim_net(elf_file: str, output_kpi_path: str, output_trace_path: Optional[str] = None, output_kpi_csv_path: Optional[str] = None, csv_format: Optional[bool] = False, target: Optional[Platform] = None)` (line 327): Take elf file and generate summary KPI file, and trace file.
    Parameters:
    - `elf_file`: a elf_file
    - `output_kpi_path`: Path in which kpi files should be created
    - `output_trace_path`: Optional Path in which trace files should be created. Only mla-isim supports --mpack.
    - `output_kpi_csv_path`: Path in which kpi files in csv format should be created
    - `csv_format`: Generate the Summary KPI in CVS format
    - `target`: [Optional] platform target.
