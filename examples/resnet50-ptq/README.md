# ResNet-50 PTQ Example

This example shows a ResNet-50 workflow for Model Compiler. It includes a
reference ONNX application, a model download/export helper, and Model Compiler
quantization and compilation scripts.

Run the scripts in a Neat SDK or Ubuntu host environment where Model Compiler is
installed and activated. Do not install a separate Python requirements file for
this example; the Model Compiler virtual environment already provides the needed
dependencies.

## Contents

- `compile.py`: standalone first-model script that accepts your own
  ONNX model and calibration image folder.
- `data/golden_retriever_207.jpg`: validation image used by the example.
- `data/imagenet_labels.txt`: ImageNet class labels used for postprocessing.
- `data/download_openimages_calibration.py`: downloads a small calibration set
  from the public Open Images validation split and writes
  `data/openimages_v7_images_and_labels.pkl`.
- `data/openimages_v7_images_and_labels.pkl`: generated calibration data used
  by quantization. This file is not tracked in git.
- `models/download_resnet50.py`: downloads a pretrained ResNet-50 model, adds
  Softmax, simplifies the graph, and saves `models/resnet50_model.onnx`.
- `src/modelsdk_quantize_model/resnet50_quant.py`: quantizes and compiles the
  generated ResNet-50 model with Model Compiler.
- `src/x86_reference_app/resnet50_reference_classification_app.py`: runs the
  ONNX model with ONNX Runtime as an x86 reference application.

## Typical Flow

```bash
cd resnet50-ptq
python3 models/download_resnet50.py
python3 src/x86_reference_app/resnet50_reference_classification_app.py
python3 data/download_openimages_calibration.py --samples 50
python3 src/modelsdk_quantize_model/resnet50_quant.py
```

For the shortest end-to-end Model Compiler flow, run from this directory:

```bash
python3 compile.py
```

This wrapper generates the ResNet-50 ONNX model and Open Images calibration
pickle if they are missing, then quantizes, validates, and compiles the model.
It defaults to INT8. Use `--precision bf16` only when explicitly testing BF16
compiler support.

The `resnet50_quant.py` script expects `data/openimages_v7_images_and_labels.pkl`
to contain a dictionary with `data` and `target` lists. `data` is used as the
representative calibration image set during quantization; `target` is printed as
reference labels for the sample calibration images.

The downloader uses the public Open Images validation metadata CSV:

```text
https://storage.googleapis.com/openimages/2018_04/validation/validation-images-with-rotation.csv
```

It downloads image objects from the public Open Images S3 bucket:

```text
https://open-images-dataset.s3.amazonaws.com/validation/<image-id>.jpg
```
