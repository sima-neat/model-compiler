import cv2
import shutil
import argparse
import numpy as np
import onnxruntime as ort

from pathlib import Path
from typing import Union

# Constants
ROOT_PATH = Path(__file__).parent.resolve()
INPUT_IMAGES_PATH = str(Path(ROOT_PATH, "../../data/"))
IMAGENET_LABELS_PATH = str(Path(ROOT_PATH, "../../data/imagenet_labels.txt"))
MODEL_PATH = str(Path(ROOT_PATH, "../../models/resnet50_model.onnx"))
SAVE_OUTPUTS_FOR_DEBUG = True
OUTPUT_DEBUG_PATH = ROOT_PATH/"debug"

####################
# Helper Functions #
####################
    
def recreate_directory(dir_path: Union[Path, str]):
    # Ensure dir_path is a Path object if given a string
    dir_path = Path(dir_path)
    
    # Check if the directory exists
    if dir_path.exists():
        # Remove the directory and all its contents
        shutil.rmtree(dir_path)
        print(f"Deleted directory: {dir_path}")
    
    # Recreate the directory
    dir_path.mkdir(parents=True, exist_ok=True)
    print(f"Recreated directory: {dir_path}")

###################
# Setup Functions #
###################

def setup(model_path: str, labels_path: str):
    # Load labels and ONNX model
    with open(labels_path, "r") as f:
        labels = [line.strip() for line in f.readlines()]

    # Load the ONNX model
    session = ort.InferenceSession(model_path)
    input_name = session.get_inputs()[0].name

    return labels, session, input_name

######################
# Pipeline Functions #
######################

def read_image(image_path: str, dump_output: bool = False):
    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    image_name = Path(image_path).stem
    if dump_output:
        debug_image_name = image_name + "_rgb.bin"
        rgb_image.tofile(str(OUTPUT_DEBUG_PATH/debug_image_name))
        
    return rgb_image, image_name
        

# Function to preprocess the image
def preprocess_image(image: np.ndarray, input_shape: tuple = (224, 224), scale_factor: tuple = 255.0, 
                     dump_output_image_name: str = None, dump_output: bool = False):
    mean = [0.485, 0.456, 0.406]
    stddv = [0.229, 0.224, 0.225]
    
    resized_image = cv2.resize(image, input_shape)
    image_data = resized_image / scale_factor
    image_data = (image_data - mean) / stddv
    
    if dump_output:
        # Dump reference output before transposing because MLA uses NHWC format not NCHW
        assert dump_output_image_name is not None
        
        debug_image_path = OUTPUT_DEBUG_PATH/f"{dump_output_image_name}_preprocessed_rgb_nhwc_fp32.bin"
        image_data.tofile(debug_image_path)
    
    image_data = np.transpose(image_data.astype('float32'), (2, 0, 1))  # Change to (C, H, W)
    image_data = np.expand_dims(image_data, axis=0)  # Add batch dimension
    
    return image_data

# Function to post-process the output
def postprocess_output(output: np.ndarray, labels: dict, 
                       dump_output_image_name: str = None, dump_output: bool = False):
    probabilities = output[0][0]
    max_idx = np.argmax(probabilities)
    
    if dump_output:
        # Dump reference output before transposing because MLA uses NHWC format not NCHW
        assert dump_output_image_name is not None
        
        debug_image_path = OUTPUT_DEBUG_PATH/f"{dump_output_image_name}_inference_output_probabilities.bin"
        probabilities.tofile(debug_image_path)
    
    return labels[max_idx], probabilities[max_idx]

def main(images_path: str, model_path: str, labels_path: str = IMAGENET_LABELS_PATH):
    """ Runs an application pipeline composed of the following 5 stages:

        Load image -> Preprocess image -> Run ResNet50 (inference) -> Postprocess outputs -> Display results
    """

    # Initialization #
    labels, inference_session, input_name = setup(model_path=model_path, labels_path=labels_path)
    image_paths = list(Path(images_path).glob("*.jpg"))

    # 5 Stage application pipeline #
    print(f"\nProcessing all images in: {images_path}\n")
    
    for idx, image_path in enumerate(image_paths):
        print(f"Processing image [{idx}] --> ", end="")

        # Load image #
        image, image_name = read_image(str(image_path), dump_output=SAVE_OUTPUTS_FOR_DEBUG)

        # Preprocess #
        input_data = preprocess_image(image, dump_output_image_name=image_name, dump_output=SAVE_OUTPUTS_FOR_DEBUG)

        # Run inference #
        output = inference_session.run(None, {input_name: input_data})

        # Postprocess #
        class_name, confidence = postprocess_output(output, labels, dump_output_image_name=image_name, dump_output=SAVE_OUTPUTS_FOR_DEBUG)

        # Display results #
        print(f"Class: {class_name} Confidence: {confidence * 100.0:.2f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify an image using an ONNX ResNet50 model.")

    parser.add_argument("-i", "--images_path", type=str, required=False, default=INPUT_IMAGES_PATH, help="Path to the image file.")
    parser.add_argument("-m", "--model_path", type=str, required=False,  default=MODEL_PATH, help="Path to the image file.")
    args = parser.parse_args()

    # Setup output directory
    if SAVE_OUTPUTS_FOR_DEBUG:
        recreate_directory(OUTPUT_DEBUG_PATH)

    main(images_path=args.images_path, model_path=args.model_path)