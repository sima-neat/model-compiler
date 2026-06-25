import argparse
import cv2
import numpy as np
import pickle as pkl

from afe.apis.defines import QuantizationParams, quantization_scheme, CalibrationMethod, gen1_target, gen2_target
from afe.apis.loaded_net import load_model
from afe.apis.release_v1 import get_model_sdk_version
from afe.ir.tensor_type import ScalarType
from afe.load.importers.general_importer import onnx_source
from afe.core.utils import convert_data_generator_to_iterable

from typing import Dict
from pathlib import Path
from afe import DataGenerator

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="Quantize and Compile ResNet50 for SiMa.ai boards.")
parser.add_argument(
    "--boardtype", 
    type=str, 
    choices=["mlsoc", "modalix"], 
    default="mlsoc",
    help="Specify the target board type: 'mlsoc' (Gen1) or 'modalix' (Gen2). Defaults to mlsoc."
)
args = parser.parse_args()

print("\n***** SiMa.ai Resnet50 Model Compilation Example *****")

sdk_version = get_model_sdk_version()
    

# Map boardtype string to the SDK target objects
target_map = {
    "mlsoc": gen1_target,
    "modalix": gen2_target
}
TARGET = target_map[args.boardtype]

# Print the board type and the target class name
print("-" * 40)
print(f"ModelSDK VERSION: {sdk_version}")
print(f"BOARD TYPE: {args.boardtype}")
print("-" * 40)
# ------------------------

np.random.seed(9)

# Constants
ROOT_PATH = Path(__file__).parent.resolve()
MODEL_INPUT_NAME = "input"
MAX_DATA_SAMPLES = 50
MODELS_PATH = ROOT_PATH/"../../models"
DATA_PATH = ROOT_PATH/"../../data/"
MODEL_PATH = MODELS_PATH/"resnet50_model.onnx"
LABELS_PATH = DATA_PATH/"imagenet_labels.txt"
CALIBRATION_SET_PATH = DATA_PATH/"openimages_v7_images_and_labels.pkl"

# Dataset and preprocessing #
def create_imagenet_dataset(num_samples: int = 1) -> Dict[str, DataGenerator]:
    dataset_path = CALIBRATION_SET_PATH
    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"Calibration dataset not found: {dataset_path}. "
            "Generate it with: python3 data/download_openimages_calibration.py --samples 50"
        )

    with open(dataset_path, 'rb') as f:
        dataset = pkl.load(f)

    images_and_labels = {'images': dataset['data'][:num_samples], 
                         'labels': dataset['target'][:num_samples]}
    
    return images_and_labels

def preprocess(image, skip_transpose=True, input_shape: tuple = (224, 224), scale_factor: tuple = 255.0):
    mean = [0.485, 0.456, 0.406]
    stddv = [0.229, 0.224, 0.225]
    
    if not skip_transpose:
        image = image.transpose(1, 2, 0)
    
    image = cv2.resize(image, input_shape)
    image = image / scale_factor
    image = (image - mean) / stddv
    
    return image

def postprocess_output(output: np.ndarray):
    probabilities = output[0][0]
    max_idx = np.argmax(probabilities)
    return max_idx, probabilities[max_idx]

input_name, input_shape, input_type = ("input", (1, 3, 224, 224), ScalarType.float32)
input_shapes_dict = {input_name: input_shape}
input_types_dict = {input_name: input_type}

importer_params = onnx_source(str(MODEL_PATH), input_shapes_dict, input_types_dict)
loaded_net = load_model(importer_params,target=TARGET)

images_and_labels = create_imagenet_dataset(num_samples=MAX_DATA_SAMPLES)
images_generator = DataGenerator({MODEL_INPUT_NAME: images_and_labels["images"]})
images_generator.map({MODEL_INPUT_NAME: preprocess})

quant_configs: QuantizationParams = QuantizationParams(calibration_method=CalibrationMethod.from_str('min_max'),
                                                       activation_quantization_scheme=quantization_scheme(asymmetric=True, per_channel=False, bits=8),
                                                       weight_quantization_scheme=quantization_scheme(asymmetric=False, per_channel=True, bits=8))

print("\n***** Quantization & Calibration *****")
sdk_net = loaded_net.quantize(convert_data_generator_to_iterable(images_generator),
                              quant_configs,
                              model_name="quantized_resnet50",
                              arm_only=False)

with open(LABELS_PATH, "r") as f:
        imagenet_labels = [line.strip() for line in f.readlines()]

for idx in range(6):
    sdk_net_output = sdk_net.execute(inputs={"input": images_generator[idx]["input"]})
    inference_label, inference_result = postprocess_output(sdk_net_output)
    reference_label = images_and_labels["labels"][idx]
    print(f"[{idx}] --> {imagenet_labels[inference_label]} / {reference_label} -> {inference_result:.2%}")
    
print("\n***** Test Inference on a Golden Retriever (Class 207) *****")
dog_image = cv2.imread(str(DATA_PATH/"golden_retriever_207.jpg"))
dog_image = cv2.cvtColor(dog_image, cv2.COLOR_BGR2RGB)
pp_dog_image = np.expand_dims(preprocess(dog_image), axis=0).astype(np.float32)
sdk_net_output = sdk_net.execute(inputs={"input": pp_dog_image})
inference_label, inference_result = postprocess_output(sdk_net_output)
print(f"[{idx}] --> {imagenet_labels[inference_label]} / 207  -> {inference_result:.2%}")

sdk_net.save(model_name="quantized_resnet50", output_directory=str(MODELS_PATH))

# Compile the quantized net using the dynamic target
print(f"\n***** Compiling Model for {args.boardtype} *****")
sdk_net.compile(output_path=str(MODELS_PATH/"compiled_resnet50"))
print(f"\n ***** Compiled Model at {str(MODELS_PATH/'compiled_resnet50')} ***** ")
