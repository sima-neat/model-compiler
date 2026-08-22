import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "quantize_compile" / "scripts" / "quantize_compile.py"


def load_manifest_builder():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "build_quantization_manifest"
    )
    namespace = {}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(SCRIPT), "exec"),
        namespace,
    )
    return namespace["build_quantization_manifest"]


class QuantizationManifestTests(unittest.TestCase):
    def test_bf16_weights_imply_bf16_activations(self):
        manifest = load_manifest_builder()(
            bf16_activations=False,
            bf16_weights=True,
            device="modalix",
        )

        self.assertEqual(manifest["activation_precision"], "bfloat16")
        self.assertEqual(manifest["weight_precision"], "bfloat16")

    def test_int8_configuration_remains_int8(self):
        manifest = load_manifest_builder()(
            bf16_activations=False,
            bf16_weights=False,
            device="modalix",
        )

        self.assertEqual(manifest["activation_precision"], "int8")
        self.assertEqual(manifest["weight_precision"], "int8")


if __name__ == "__main__":
    unittest.main()
