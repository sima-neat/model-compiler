import os
import onnx
import torch
import torch.nn as nn
import torchvision.models as models

from pathlib import Path
from onnxsim import simplify

# Constants
ROOT_PATH = Path(__file__).parent.resolve()

# Modify the model to add a Softmax layer at the end
class ResNet50WithSoftmax(nn.Module):
    def __init__(self, original_model):
        super(ResNet50WithSoftmax, self).__init__()
        self.resnet50 = original_model
        self.softmax = nn.Softmax(dim=1)  # Softmax over the class dimension

    def forward(self, x):
        x = self.resnet50(x)
        x = self.softmax(x)
        return x
    
    
def create_model_onnx(onnx_export_path=str(ROOT_PATH/"resnet50_model.onnx")):
    tmp_model_path=str(ROOT_PATH/"resnet50_export.onnx")
    
    # Load the pre-trained ResNet50 model
    resnet50 = models.resnet50(pretrained=True)
    resnet50.eval()  # Set the model to evaluation mode

    # Create the modified model with Softmax
    model_with_softmax = ResNet50WithSoftmax(resnet50)
    dummy_input = torch.randn(1, 3, 224, 224)

    # Export the model to ONNX format
    torch.onnx.export(
        model_with_softmax,        # The model to be exported
        dummy_input,               # The input tensor
        tmp_model_path,            # Where to save the ONNX file
        export_params=True,        # Store the trained parameters in the ONNX file
        opset_version=16,          # The ONNX version to export the model to (ensure compatibility)
        do_constant_folding=True,  # Whether to execute constant folding for optimization
        input_names=['input'],     # Input name(s)
        output_names=['output'],   # Output name(s)
    )

    print(f"Model exported successfully to {tmp_model_path}")
    
    # Simplify the model
    model = onnx.load(tmp_model_path)
    model_simplified, check = simplify(model)
    
    # Clean up temp model
    os.remove(tmp_model_path)

    # Check if simplification was successful
    if check:
        onnx.save(model_simplified, onnx_export_path)
        print(f"Simplified model saved to {onnx_export_path}")
    else:
        print("Simplification failed.")
        
    return model_simplified

if __name__ == "__main__":
    create_model_onnx()